from __future__ import annotations

import unittest

from auravita_logistics.config import SimulationConfig
from auravita_logistics.simulation import LogisticsSimulation


class SimulationTests(unittest.TestCase):
    def test_collections_retire_after_twelve_quarters(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "retirement",
                "start_year": 2026,
                "simulation_quarters": 13,
                "quarterly_signups": [1] + [0] * 12,
                "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
                "future_collections": ["Origen", "Bruma"],
                "collections_per_year": 2,
                "collection_lifespan_quarters": 12,
                "default_purchase_cost": 100.0,
                "churn": {
                    "starts_from_quarter": 20,
                    "min_per_quarter": 1,
                    "max_per_quarter": 1,
                    "random_seed": 1
                }
            }
        )

        result = LogisticsSimulation(config).run()

        retired_aura_lots = [
            lot for lot in result.inventory.lots.values()
            if lot.collection_name == "Aura" and lot.state.value == "RETIRADO"
        ]
        self.assertTrue(retired_aura_lots)
        self.assertTrue(any(summary.retired_lots > 0 for summary in result.quarter_summaries if summary.quarter_index == 13))

    def test_simulation_returns_lot_to_stock_after_churn(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "churn",
                "start_year": 2026,
                "simulation_quarters": 3,
                "quarterly_signups": [2, 0, 0],
                "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
                "future_collections": [],
                "collections_per_year": 2,
                "collection_lifespan_quarters": 12,
                "default_purchase_cost": 100.0,
                "churn": {
                    "starts_from_quarter": 3,
                    "min_per_quarter": 1,
                    "max_per_quarter": 1,
                    "random_seed": 1
                }
            }
        )

        result = LogisticsSimulation(config).run()

        self.assertEqual(result.quarter_summaries[2].churn, 1)
        self.assertGreaterEqual(len(result.inventory.stock_lots()), 1)


if __name__ == "__main__":
    unittest.main()
