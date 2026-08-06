from __future__ import annotations

from datetime import date
from random import Random

from auravita_logistics.assignment_engine import AssignmentEngine
from auravita_logistics.catalog import CollectionCatalog
from auravita_logistics.config import SimulationConfig
from auravita_logistics.inventory import InventoryManager
from auravita_logistics.models import Client, ClientEvent, ClientState, LotState, QuarterSummary, RotationRecord
from auravita_logistics.utils import quarter_label, rotation_date_for_slot


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
        churn_count = self._process_churn(quarter_index)
        purchase_cost_start = self.purchase_cost_accumulator

        active_clients = self._current_active_clients()
        for client in active_clients:
            if client.signup_quarter_index == quarter_index:
                continue
            self._rotate_client(client, quarter_index, is_new_client=False)

        for _ in range(signups):
            client = self._create_client(quarter_index)
            self.clients[client.id] = client
            self._rotate_client(client, quarter_index, is_new_client=True)

        purchases = len(
            [
                record
                for record in self.rotation_records
                if record.quarter_index == quarter_index and record.purchased_new
            ]
        )
        final_stock = len(self.inventory.stock_lots())
        active_clients_count = len(self._current_active_clients())
        estimated_cost = self.purchase_cost_accumulator - purchase_cost_start

        return QuarterSummary(
            quarter_index=quarter_index,
            quarter_label=quarter_name,
            active_clients=active_clients_count,
            signups=signups,
            churn=churn_count,
            purchases=purchases,
            retired_lots=retired_lot_count,
            final_stock=final_stock,
            estimated_cost=estimated_cost,
        )

    def _current_active_clients(self) -> list[Client]:
        return sorted(
            [client for client in self.clients.values() if client.state == ClientState.ACTIVE],
            key=lambda client: (client.cohort_slot, client.id),
        )

    def _create_client(self, quarter_index: int) -> Client:
        client_id = (
            f"{self.config.naming.client_prefix}"
            f"{self.client_sequence:0{self.config.naming.client_pad}d}"
        )
        self.client_sequence += 1
        slot_count = 6
        cohort_slot = (quarter_index - 1) % slot_count
        event_date = rotation_date_for_slot(
            self.config.start_year,
            quarter_index,
            cohort_slot,
            self.config.logistics.cohort_gap_weeks,
        )
        client = Client(
            id=client_id,
            signup_date=event_date,
            signup_quarter_index=quarter_index,
            signup_quarter_label=quarter_label(self.config.start_year, quarter_index),
            cohort_slot=cohort_slot,
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

    def _rotate_client(self, client: Client, quarter_index: int, is_new_client: bool) -> None:
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

        decision = self.assignment_engine.assign_lot(client, quarter_index, event_date)
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
            )
        )

    def _process_churn(self, quarter_index: int) -> int:
        active_clients = self._current_active_clients()
        churn_count = self.config.churn.draw_count(len(active_clients), quarter_index, self.rng)
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
