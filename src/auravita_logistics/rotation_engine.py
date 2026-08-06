from __future__ import annotations

from datetime import date
from random import Random

from auravita_logistics.assignment_engine import AssignmentDecision, AssignmentEngine
from auravita_logistics.catalog import CollectionCatalog
from auravita_logistics.config import SimulationConfig
from auravita_logistics.inventory import InventoryManager
from auravita_logistics.models import Client, ClientEvent, ClientState, LotState, QuarterSummary, RotationRecord
from auravita_logistics.utils import quarter_label, rotation_date_for_slot

FULL_CAPACITY_COHORTS = 13


class RotationEngine:
    def __init__(
        self,
        config: SimulationConfig,
        catalog: CollectionCatalog,
        inventory: InventoryManager,
        assignment_engine: AssignmentEngine,
        clients: dict[str, Client],
        rng: Random,
    ):
        self.config = config
        self.catalog = catalog
        self.inventory = inventory
        self.assignment_engine = assignment_engine
        self.clients = clients
        self.rng = rng
        self.rotation_records: list[RotationRecord] = []
        self.client_sequence = 1
        self.purchase_cost_accumulator = 0.0
        self._last_churn_returns = 0
        self._last_churn_replacements: list[dict[str, object]] = []
        self._pending_growth_backlog: list[dict[str, int]] = []

    def preload_inventory(self) -> int:
        created = 0
        for collection_name, quantity in self.config.preloaded_stock_by_collection.items():
            if collection_name not in self.catalog.collections:
                raise ValueError(f"Unknown collection in preloaded_stock_by_collection: {collection_name}")
            for _ in range(quantity):
                preload_date = rotation_date_for_slot(
                    self.config.start_year,
                    1,
                    0,
                    self.config.logistics.cohort_gap_weeks,
                )
                lot = self.inventory.purchase_lot(
                    collection_name=collection_name,
                    purchase_date=preload_date,
                    quarter_index=1,
                    location=self.config.logistics.warehouse_location,
                    note="Carga inicial de stock.",
                )
                self.catalog.record_lot_purchase(collection_name, lot.id, 1, preload_date)
                self.purchase_cost_accumulator += self.config.active_purchase_cost(collection_name)
                created += 1
        return created

    def process_quarter(self, quarter_index: int, signups: int) -> QuarterSummary:
        quarter_name = quarter_label(self.config.start_year, quarter_index)
        retired_lot_count = self._retire_expired_collections(quarter_index)
        ready_pool_start = len(self.inventory.stock_lots())
        reconditioning_inflow = 0
        bridge_pool_required = 0
        churn_count = self._process_churn(quarter_index)
        reconditioning_inflow += self._last_churn_returns
        effective_signups = self.config.signup_policy.resolve_signups(signups, churn_count)
        planned_growth_signups = max(effective_signups - churn_count, 0)
        fixed_purchase_target = self.config.purchase_policy.fixed_new_lots_per_quarter
        purchase_target = fixed_purchase_target or planned_growth_signups
        purchase_budget = purchase_target
        launch_purchase_budget = purchase_target
        launched_collections = self.catalog.launched_collection_names(quarter_index)
        purchase_cost_start = self.purchase_cost_accumulator

        for replacement in sorted(
            self._last_churn_replacements,
            key=lambda item: (item["event_date"], item["client_id"]),
        ):
            client = self._create_client(
                quarter_index,
                cohort_slot=int(replacement["cohort_slot"]),
                signup_date=replacement["event_date"],
            )
            self.clients[client.id] = client
            self._assign_specific_lot(
                client=client,
                lot=self.inventory.lots[str(replacement["lot_id"])],
                quarter_index=quarter_index,
                event_date=replacement["event_date"],
                is_new_client=True,
                reason="replacement_signup_from_churn",
            )
            bridge_pool_required += 1

        backlog_fill_signups = max(planned_growth_signups - purchase_target, 0)
        current_quarter_signups = min(planned_growth_signups, purchase_target)
        backlog_fills_completed = 0
        while backlog_fill_signups > 0 and self._pending_growth_backlog:
            backlog_entry = self._pending_growth_backlog[0]
            client = self._create_client(
                quarter_index,
                cohort_slot=backlog_entry["cohort_slot"],
                signup_date=rotation_date_for_slot(
                    self.config.start_year,
                    quarter_index,
                    backlog_entry["cohort_slot"],
                    self.config.logistics.cohort_gap_weeks,
                ),
            )
            self.clients[client.id] = client
            decision = self._rotate_client(
                client,
                quarter_index,
                is_new_client=True,
                purchase_allowed=False,
            )
            bridge_pool_required += 1 if decision.same_quarter_stock_reuse else 0
            backlog_fill_signups -= 1
            backlog_fills_completed += 1
            backlog_entry["quantity"] -= 1
            if backlog_entry["quantity"] == 0:
                self._pending_growth_backlog.pop(0)

        actual_signups = (
            current_quarter_signups
            + backlog_fills_completed
            + len(self._last_churn_replacements)
        )
        active_clients = self._current_active_clients()
        for client in active_clients:
            if client.signup_quarter_index == quarter_index:
                continue
            had_outgoing_lot = client.current_lot_id is not None
            decision = self._rotate_client(
                client,
                quarter_index,
                is_new_client=False,
                preferred_collections=launched_collections,
                allow_proactive_purchase=launch_purchase_budget > 0,
                purchase_allowed=purchase_budget > 0,
            )
            reconditioning_inflow += 1 if had_outgoing_lot else 0
            bridge_pool_required += 1 if decision.same_quarter_stock_reuse else 0
            if decision.reason == "preferred_collection_purchase":
                launch_purchase_budget -= 1
            if decision.purchased_new:
                purchase_budget -= 1

        for _ in range(current_quarter_signups):
            client = self._create_client(quarter_index)
            self.clients[client.id] = client
            decision = self._rotate_client(
                client,
                quarter_index,
                is_new_client=True,
                purchase_allowed=purchase_budget > 0,
            )
            bridge_pool_required += 1 if decision.same_quarter_stock_reuse else 0
            if decision.purchased_new:
                purchase_budget -= 1

        missing_current_quarter_signups = max(purchase_target - current_quarter_signups, 0)
        if missing_current_quarter_signups > 0:
            self._pending_growth_backlog.append(
                {
                    "origin_quarter_index": quarter_index,
                    "cohort_slot": (quarter_index - 1) % FULL_CAPACITY_COHORTS,
                    "quantity": missing_current_quarter_signups,
                }
            )

        purchases = len(
            [lot for lot in self.inventory.lots.values() if lot.purchase_quarter_index == quarter_index]
        )
        self._top_up_quarter_inventory(quarter_index, purchase_target - purchases)
        purchases = len(
            [lot for lot in self.inventory.lots.values() if lot.purchase_quarter_index == quarter_index]
        )
        final_stock = len(self.inventory.stock_lots())
        active_clients_count = len(self._current_active_clients())
        estimated_cost = self.purchase_cost_accumulator - purchase_cost_start

        return QuarterSummary(
            quarter_index=quarter_index,
            quarter_label=quarter_name,
            active_clients=active_clients_count,
            signups=actual_signups,
            churn=churn_count,
            purchases=purchases,
            retired_lots=retired_lot_count,
            final_stock=final_stock,
            estimated_cost=estimated_cost,
            ready_pool_start=ready_pool_start,
            reconditioning_inflow=reconditioning_inflow,
            bridge_pool_required=bridge_pool_required,
        )

    def _current_active_clients(self) -> list[Client]:
        return sorted(
            [client for client in self.clients.values() if client.state == ClientState.ACTIVE],
            key=lambda client: (client.signup_quarter_index, client.signup_date, client.id),
        )

    def _create_client(
        self,
        quarter_index: int,
        *,
        cohort_slot: int | None = None,
        signup_date: date | None = None,
    ) -> Client:
        client_id = (
            f"{self.config.naming.client_prefix}"
            f"{self.client_sequence:0{self.config.naming.client_pad}d}"
        )
        self.client_sequence += 1
        slot_count = FULL_CAPACITY_COHORTS
        resolved_cohort_slot = (quarter_index - 1) % slot_count if cohort_slot is None else cohort_slot
        event_date = signup_date or rotation_date_for_slot(
            self.config.start_year,
            quarter_index,
            resolved_cohort_slot,
            self.config.logistics.cohort_gap_weeks,
        )
        client = Client(
            id=client_id,
            signup_date=event_date,
            signup_quarter_index=quarter_index,
            signup_quarter_label=quarter_label(self.config.start_year, quarter_index),
            cohort_slot=resolved_cohort_slot,
        )
        client.history.append(
            ClientEvent(
                quarter_index=quarter_index,
                quarter_label=client.signup_quarter_label,
                event_date=event_date,
                event_type="CLIENT_SIGNUP",
                detail=f"Alta del cliente {client_id}.",
            )
        )
        return client

    def _assign_specific_lot(
        self,
        *,
        client: Client,
        lot,
        quarter_index: int,
        event_date: date,
        is_new_client: bool,
        reason: str,
    ) -> AssignmentDecision:
        self.inventory.assign_to_client(
            lot=lot,
            client_id=client.id,
            event_date=event_date,
            quarter_index=quarter_index,
            note="Asignación de sustitución inmediata por baja en el mismo hueco operativo.",
        )
        self.catalog.record_assignment(lot.collection_name, client.id, lot.id, quarter_index, event_date)
        client.received_collections.append(lot.collection_name)
        client.received_lots.append(lot.id)
        client.current_lot_id = lot.id
        client.history.append(
            ClientEvent(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                event_date=event_date,
                event_type="INITIAL_ASSIGNMENT" if is_new_client else "ROTATION_COMPLETED",
                detail=f"Asignado lote {lot.id} como sustitución directa tras una baja.",
            )
        )
        decision = AssignmentDecision(
            lot=lot,
            purchased_new=False,
            forced_repeat=False,
            reason=reason,
            same_quarter_stock_reuse=True,
        )
        self.rotation_records.append(
            RotationRecord(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                rotation_date=event_date,
                client_id=client.id,
                outgoing_lot_id=None,
                outgoing_collection=None,
                incoming_lot_id=lot.id,
                incoming_collection=lot.collection_name,
                purchased_new=False,
                forced_repeat=False,
                reason=reason,
                same_quarter_stock_reuse=True,
            )
        )
        return decision

    def _top_up_quarter_inventory(self, quarter_index: int, missing_purchases: int) -> None:
        if missing_purchases <= 0:
            return

        candidate_collections = self.catalog.active_collection_names(quarter_index)
        if not candidate_collections:
            return

        for _ in range(missing_purchases):
            selected_collection = self.assignment_engine._select_collection_for_purchase(candidate_collections)
            purchase_date = rotation_date_for_slot(
                self.config.start_year,
                quarter_index,
                min((quarter_index - 1) % FULL_CAPACITY_COHORTS, FULL_CAPACITY_COHORTS - 1),
                self.config.logistics.cohort_gap_weeks,
            )
            lot = self.inventory.purchase_lot(
                collection_name=selected_collection,
                purchase_date=purchase_date,
                quarter_index=quarter_index,
                location=self.config.logistics.warehouse_location,
                note="Compra fija trimestral sin cliente asignado; se guarda en stock para cubrir deficit comercial.",
            )
            self.catalog.record_lot_purchase(selected_collection, lot.id, quarter_index, purchase_date)
            self.purchase_cost_accumulator += self.config.active_purchase_cost(selected_collection)

    def _rotate_client(
        self,
        client: Client,
        quarter_index: int,
        is_new_client: bool,
        *,
        preferred_collections: list[str] | None = None,
        allow_proactive_purchase: bool = False,
        purchase_allowed: bool = True,
    ) -> AssignmentDecision:
        event_date = rotation_date_for_slot(
            self.config.start_year,
            quarter_index,
            client.cohort_slot,
            self.config.logistics.cohort_gap_weeks,
        )
        outgoing_lot_id = client.current_lot_id
        outgoing_collection = None

        if client.current_lot_id:
            outgoing_lot = self.inventory.lots[client.current_lot_id]
            outgoing_collection = outgoing_lot.collection_name
            self.inventory.return_to_stock(
                lot=outgoing_lot,
                event_date=event_date,
                quarter_index=quarter_index,
                note="Rotación trimestral.",
            )
            client.current_lot_id = None

        decision = self.assignment_engine.assign_lot(
            client,
            quarter_index,
            event_date,
            preferred_collections=preferred_collections,
            allow_proactive_purchase=allow_proactive_purchase,
            purchase_allowed=purchase_allowed,
        )
        if decision.purchased_new:
            self.catalog.record_lot_purchase(decision.lot.collection_name, decision.lot.id, quarter_index, event_date)
            self.purchase_cost_accumulator += self.config.active_purchase_cost(decision.lot.collection_name)
        self.catalog.record_assignment(decision.lot.collection_name, client.id, decision.lot.id, quarter_index, event_date)

        client.received_collections.append(decision.lot.collection_name)
        client.received_lots.append(decision.lot.id)
        client.current_lot_id = decision.lot.id
        client.history.append(
            ClientEvent(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                event_date=event_date,
                event_type="INITIAL_ASSIGNMENT" if is_new_client else "ROTATION_COMPLETED",
                detail=(
                    f"Asignado lote {decision.lot.id} de la colección {decision.lot.collection_name}."
                    if not decision.forced_repeat
                    else f"Asignado lote {decision.lot.id} repitiendo colección por falta de alternativas."
                ),
            )
        )
        self.rotation_records.append(
            RotationRecord(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                rotation_date=event_date,
                client_id=client.id,
                outgoing_lot_id=outgoing_lot_id,
                outgoing_collection=outgoing_collection,
                incoming_lot_id=decision.lot.id,
                incoming_collection=decision.lot.collection_name,
                purchased_new=decision.purchased_new,
                forced_repeat=decision.forced_repeat,
                reason=decision.reason,
                same_quarter_stock_reuse=decision.same_quarter_stock_reuse,
            )
        )
        return decision

    def _process_churn(self, quarter_index: int) -> int:
        active_clients = self._current_active_clients()
        churn_count = self.config.churn.draw_count(len(active_clients), quarter_index, self.rng)
        self._last_churn_returns = 0
        self._last_churn_replacements = []
        if churn_count == 0:
            return 0

        departing_clients = self.rng.sample(active_clients, churn_count)
        for client in departing_clients:
            event_date = rotation_date_for_slot(
                self.config.start_year,
                quarter_index,
                client.cohort_slot,
                self.config.logistics.cohort_gap_weeks,
            )
            if client.current_lot_id:
                lot = self.inventory.lots[client.current_lot_id]
                self.inventory.return_to_stock(
                    lot=lot,
                    event_date=event_date,
                    quarter_index=quarter_index,
                    note="Devolución por baja del cliente.",
                )
                self._last_churn_returns += 1
                self._last_churn_replacements.append(
                    {
                        "client_id": client.id,
                        "cohort_slot": client.cohort_slot,
                        "event_date": event_date,
                        "lot_id": lot.id,
                    }
                )
                client.current_lot_id = None
            client.state = ClientState.INACTIVE
            client.end_date = event_date
            client.end_quarter_index = quarter_index
            client.history.append(
                ClientEvent(
                    quarter_index=quarter_index,
                    quarter_label=quarter_label(self.config.start_year, quarter_index),
                    event_date=event_date,
                    event_type="CLIENT_CHURN",
                    detail=f"Baja del cliente {client.id}.",
                )
            )
        return churn_count

    def _retire_expired_collections(self, quarter_index: int) -> int:
        retiring = self.catalog.collections_retiring_in(quarter_index)
        retired_lots = 0
        if not retiring:
            return retired_lots

        retirement_date = rotation_date_for_slot(
            self.config.start_year,
            quarter_index,
            0,
            self.config.logistics.cohort_gap_weeks,
        )

        for collection_name in retiring:
            lots = self.inventory.lots_in_collection(collection_name)
            for lot in lots:
                if lot.state == LotState.RETIRED:
                    continue
                if lot.current_client_id:
                    client = self.clients[lot.current_client_id]
                    client.current_lot_id = None
                    client.history.append(
                        ClientEvent(
                            quarter_index=quarter_index,
                            quarter_label=quarter_label(self.config.start_year, quarter_index),
                            event_date=retirement_date,
                            event_type="FORCED_RETURN_BY_RETIREMENT",
                            detail=(
                                f"Retirada automática del lote {lot.id} "
                                f"por fin de vida de la colección {collection_name}."
                            ),
                        )
                    )
                reason = f"Colección {collection_name} fuera de vida útil."
                self.inventory.retire_lot(lot, retirement_date, quarter_index, reason)
                self.catalog.record_retirement(collection_name, lot.id, quarter_index, retirement_date, reason)
                retired_lots += 1
        return retired_lots
