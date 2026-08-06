from __future__ import annotations

from datetime import date
import unittest

from auravita_logistics.assignment_engine import AssignmentEngine
from auravita_logistics.catalog import CollectionCatalog
from auravita_logistics.config import SimulationConfig
from auravita_logistics.inventory import InventoryManager
from auravita_logistics.models import Client


def build_config() -> SimulationConfig:
    return SimulationConfig.from_dict(
        {
            "simulation_name": "test",
            "start_year": 2026,
            "simulation_quarters": 4,
            "quarterly_signups": [0, 0, 0, 0],
            "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
            "future_collections": [],
            "collections_per_year": 2,
            "collection_lifespan_quarters": 12,
            "default_purchase_cost": 100.0
        }
    )


class AssignmentEngineTests(unittest.TestCase):
    def test_prefers_lot_that_has_been_in_stock_longest(self) -> None:
        config = build_config()
        catalog = CollectionCatalog(config)
        inventory = InventoryManager(config)
        engine = AssignmentEngine(config, catalog, inventory)
        lot_1 = inventory.purchase_lot("Aura", date(2026, 1, 1), 1, "ALMACEN", "stock 1")
        lot_2 = inventory.purchase_lot("Aura", date(2026, 4, 1), 2, "ALMACEN", "stock 2")
        client = Client(
            id="C00001",
            signup_date=date(2026, 4, 1),
            signup_quarter_index=2,
            signup_quarter_label="2026-T2",
            cohort_slot=0,
        )

        decision = engine.assign_lot(client, 2, date(2026, 4, 1))

        self.assertEqual(decision.lot.id, lot_1.id)
        self.assertFalse(decision.purchased_new)
        self.assertEqual(lot_2.state.value, "STOCK")

    def test_buys_new_lot_when_recent_history_blocks_all_stock(self) -> None:
        config = build_config()
        catalog = CollectionCatalog(config)
        inventory = InventoryManager(config)
        engine = AssignmentEngine(config, catalog, inventory)
        inventory.purchase_lot("Aura", date(2026, 1, 1), 1, "ALMACEN", "stock 1")
        client = Client(
            id="C00001",
            signup_date=date(2026, 4, 1),
            signup_quarter_index=2,
            signup_quarter_label="2026-T2",
            cohort_slot=0,
            received_collections=["Aura", "Natura", "Esencia", "Horizonte"],
        )

        decision = engine.assign_lot(client, 2, date(2026, 4, 1))

        self.assertTrue(decision.purchased_new)
        self.assertTrue(decision.forced_repeat)
        self.assertEqual(decision.lot.collection_name, "Aura")


if __name__ == "__main__":
    unittest.main()
