from __future__ import annotations

from datetime import date

from auravita_logistics.config import SimulationConfig
from auravita_logistics.models import Lot, LotMovement, LotState
from auravita_logistics.utils import parse_numeric_suffix, quarter_label


class InventoryManager:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.lots: dict[str, Lot] = {}
        self._next_lot_number = 1

    def create_lot_id(self) -> str:
        prefix = self.config.naming.lot_prefix
        padding = self.config.naming.lot_pad
        lot_id = f"{prefix}{self._next_lot_number:0{padding}d}"
        self._next_lot_number += 1
        return lot_id

    def purchase_lot(
        self,
        collection_name: str,
        purchase_date: date,
        quarter_index: int,
        location: str,
        note: str,
    ) -> Lot:
        lot = Lot(
            id=self.create_lot_id(),
            collection_name=collection_name,
            purchase_date=purchase_date,
            purchase_quarter_index=quarter_index,
            purchase_quarter_label=quarter_label(self.config.start_year, quarter_index),
            state=LotState.STOCK,
            location=location,
            stock_since_quarter_index=quarter_index,
        )
        lot.movement_history.append(
            LotMovement(
                quarter_index=quarter_index,
                quarter_label=lot.purchase_quarter_label,
                event_date=purchase_date,
                event_type="PURCHASED",
                location=location,
                note=note,
            )
        )
        self.lots[lot.id] = lot
        return lot

    def assign_to_client(self, lot: Lot, client_id: str, event_date: date, quarter_index: int, note: str) -> None:
        lot.state = LotState.CLIENT
        lot.location = client_id
        lot.current_client_id = client_id
        lot.usage_count += 1
        lot.client_history.append(client_id)
        lot.movement_history.append(
            LotMovement(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                event_date=event_date,
                event_type="ASSIGNED_TO_CLIENT",
                location=client_id,
                client_id=client_id,
                note=note,
            )
        )

    def return_to_stock(self, lot: Lot, event_date: date, quarter_index: int, note: str) -> None:
        lot.state = LotState.STOCK
        lot.location = self.config.logistics.warehouse_location
        lot.current_client_id = None
        lot.last_return_date = event_date
        lot.last_return_quarter_index = quarter_index
        lot.stock_since_quarter_index = quarter_index
        lot.movement_history.append(
            LotMovement(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                event_date=event_date,
                event_type="RETURNED_TO_STOCK",
                location=lot.location,
                note=note,
            )
        )

    def retire_lot(self, lot: Lot, event_date: date, quarter_index: int, reason: str) -> None:
        lot.state = LotState.RETIRED
        lot.location = self.config.logistics.retired_location
        lot.current_client_id = None
        lot.retired_date = event_date
        lot.retired_quarter_index = quarter_index
        lot.retirement_reason = reason
        lot.movement_history.append(
            LotMovement(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                event_date=event_date,
                event_type="RETIRED",
                location=lot.location,
                note=reason,
            )
        )

    def stock_lots(self) -> list[Lot]:
        return [lot for lot in self.lots.values() if lot.state == LotState.STOCK]

    def lots_in_collection(self, collection_name: str) -> list[Lot]:
        return [lot for lot in self.lots.values() if lot.collection_name == collection_name]

    def sorted_stock_lots(self) -> list[Lot]:
        return sorted(
            self.stock_lots(),
            key=lambda lot: (lot.stock_since_quarter_index, parse_numeric_suffix(lot.id)),
        )
