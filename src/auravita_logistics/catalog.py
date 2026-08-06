from __future__ import annotations

from datetime import date

from auravita_logistics.config import SimulationConfig
from auravita_logistics.models import Collection, CollectionEvent
from auravita_logistics.utils import quarter_label, quarter_start_date


class CollectionCatalog:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.collections = self._build_collections()

    def _build_collections(self) -> dict[str, Collection]:
        collections: dict[str, Collection] = {}
        all_names = list(self.config.initial_collections)
        all_names.extend(self.config.future_collections)
        launch_schedule: list[tuple[str, int]] = []

        for name in self.config.initial_collections:
            launch_schedule.append((name, 1))

        remaining = iter(self.config.future_collections)
        launch_quarter = 5
        while True:
            batch = []
            for _ in range(self.config.collections_per_year):
                try:
                    batch.append(next(remaining))
                except StopIteration:
                    break
            if not batch:
                break
            for name in batch:
                launch_schedule.append((name, launch_quarter))
            launch_quarter += 4

        for name, quarter_index in launch_schedule:
            collection = Collection(
                name=name,
                launch_quarter_index=quarter_index,
                launch_quarter_label=quarter_label(self.config.start_year, quarter_index),
                lifespan_quarters=self.config.collection_lifespan_quarters,
            )
            collection.history.append(
                CollectionEvent(
                    quarter_index=quarter_index,
                    quarter_label=collection.launch_quarter_label,
                    event_date=quarter_start_date(self.config.start_year, quarter_index),
                    event_type="COLLECTION_LAUNCHED",
                    detail=f"Colección {name} disponible desde {collection.launch_quarter_label}.",
                )
            )
            collections[name] = collection

        for name in all_names:
            if name not in collections:
                raise ValueError(f"Collection {name} missing from launch schedule")
        return collections

    def active_collection_names(self, quarter_index: int) -> list[str]:
        return sorted(
            [
                collection.name
                for collection in self.collections.values()
                if collection.is_active_in(quarter_index)
            ],
            key=lambda name: (self.collections[name].launch_quarter_index, name),
        )

    def collections_retiring_in(self, quarter_index: int) -> list[str]:
        return sorted(
            [
                collection.name
                for collection in self.collections.values()
                if collection.retirement_quarter_index == quarter_index
            ]
        )

    def record_lot_purchase(self, collection_name: str, lot_id: str, quarter_index: int, event_date: date) -> None:
        collection = self.collections[collection_name]
        collection.lot_ids.append(lot_id)
        collection.history.append(
            CollectionEvent(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                event_date=event_date,
                event_type="LOT_PURCHASED",
                detail=f"Lote {lot_id} comprado para la colección {collection_name}.",
            )
        )

    def record_assignment(self, collection_name: str, client_id: str, lot_id: str, quarter_index: int, event_date: date) -> None:
        collection = self.collections[collection_name]
        collection.assignment_count += 1
        collection.history.append(
            CollectionEvent(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                event_date=event_date,
                event_type="LOT_ASSIGNED",
                detail=f"Lote {lot_id} asignado al cliente {client_id}.",
            )
        )

    def record_retirement(self, collection_name: str, lot_id: str, quarter_index: int, event_date: date, reason: str) -> None:
        collection = self.collections[collection_name]
        collection.retired_lot_ids.append(lot_id)
        collection.history.append(
            CollectionEvent(
                quarter_index=quarter_index,
                quarter_label=quarter_label(self.config.start_year, quarter_index),
                event_date=event_date,
                event_type="LOT_RETIRED",
                detail=f"Lote {lot_id} retirado. Motivo: {reason}",
            )
        )
