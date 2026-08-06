from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from auravita_logistics.catalog import CollectionCatalog
from auravita_logistics.config import SimulationConfig
from auravita_logistics.inventory import InventoryManager
from auravita_logistics.models import Client, Lot


@dataclass
class AssignmentDecision:
    lot: Lot
    purchased_new: bool
    forced_repeat: bool
    reason: str


class AssignmentEngine:
    def __init__(
        self,
        config: SimulationConfig,
        catalog: CollectionCatalog,
        inventory: InventoryManager,
    ):
        self.config = config
        self.catalog = catalog
        self.inventory = inventory

    def assign_lot(self, client: Client, quarter_index: int, event_date: date) -> AssignmentDecision:
        blocked_collections = set(client.recent_collections(self.config.assignment.lookback_rotations))
        active_collections = self.catalog.active_collection_names(quarter_index)
        compatible_stock = [
            lot
            for lot in self.inventory.sorted_stock_lots()
            if lot.collection_name not in blocked_collections
            and lot.collection_name in active_collections
        ]
        if compatible_stock:
            lot = compatible_stock[0]
            self.inventory.assign_to_client(
                lot=lot,
                client_id=client.id,
                event_date=event_date,
                quarter_index=quarter_index,
                note="Asignación desde stock compatible.",
            )
            return AssignmentDecision(lot=lot, purchased_new=False, forced_repeat=False, reason="stock_compatible")

        if not active_collections:
            raise RuntimeError(f"No active collections available in quarter {quarter_index}")
        compatible_collections = [name for name in active_collections if name not in blocked_collections]
        forced_repeat = False
        if not compatible_collections:
            if not self.config.assignment.allow_repeat_when_no_alternative:
                raise RuntimeError(f"No compatible collection found for client {client.id}")
            compatible_collections = active_collections
            forced_repeat = True

        selected_collection = self._select_collection_for_purchase(compatible_collections)
        lot = self.inventory.purchase_lot(
            collection_name=selected_collection,
            purchase_date=event_date,
            quarter_index=quarter_index,
            location=self.config.logistics.warehouse_location,
            note="Compra automática por ausencia de stock compatible.",
        )
        self.inventory.assign_to_client(
            lot=lot,
            client_id=client.id,
            event_date=event_date,
            quarter_index=quarter_index,
            note="Asignación tras compra automática.",
        )
        return AssignmentDecision(
            lot=lot,
            purchased_new=True,
            forced_repeat=forced_repeat,
            reason="new_purchase" if not forced_repeat else "forced_repeat_purchase",
        )

    def _select_collection_for_purchase(self, collection_names: list[str]) -> str:
        strategy = self.config.assignment.new_lot_collection_strategy
        if strategy == "oldest_active_then_name":
            return sorted(
                collection_names,
                key=lambda name: (self.catalog.collections[name].launch_quarter_index, name),
            )[0]
        raise ValueError(f"Unsupported new_lot_collection_strategy: {strategy}")
