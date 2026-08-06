from __future__ import annotations

import unittest
from datetime import date

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
        self.assertEqual(result.quarter_summaries[2].signups, 1)
        self.assertEqual(result.quarter_summaries[2].purchases, 0)

    def test_replacement_signup_reuses_same_slot_and_same_month_as_churn(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "replacement-slot",
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

        churn_records = [
            record for record in result.rotation_records
            if record.quarter_index == 3 and record.reason == "replacement_signup_from_churn"
        ]
        self.assertEqual(len(churn_records), 1)
        replacement_record = churn_records[0]
        replacement_client = result.clients[replacement_record.client_id]

        self.assertEqual(replacement_client.signup_date, replacement_record.rotation_date)
        self.assertEqual(replacement_client.cohort_slot, 0)
        self.assertFalse(replacement_record.purchased_new)

    def test_fixed_quarter_purchase_target_keeps_buying_ten_and_carries_stock(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "fixed-ten",
                "start_year": 2026,
                "simulation_quarters": 2,
                "quarterly_signups": [8, 12],
                "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
                "future_collections": [],
                "collections_per_year": 2,
                "collection_lifespan_quarters": 12,
                "default_purchase_cost": 100.0,
                "purchase_policy": {
                    "fixed_new_lots_per_quarter": 10,
                },
                "churn": {
                    "starts_from_quarter": 20,
                    "min_per_quarter": 1,
                    "max_per_quarter": 1,
                    "random_seed": 1
                }
            }
        )

        result = LogisticsSimulation(config).run()

        self.assertEqual(result.quarter_summaries[0].signups, 8)
        self.assertEqual(result.quarter_summaries[0].purchases, 10)
        self.assertEqual(result.quarter_summaries[0].final_stock, 2)
        self.assertEqual(result.quarter_summaries[1].signups, 12)
        self.assertEqual(result.quarter_summaries[1].purchases, 10)
        self.assertEqual(result.quarter_summaries[1].final_stock, 0)

    def test_new_launch_purchase_goes_to_oldest_active_client_first(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "launch-priority",
                "start_year": 2026,
                "simulation_quarters": 9,
                "quarterly_signups": [0, 0, 0, 0, 0, 1, 1, 0, 1],
                "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
                "future_collections": ["Origen", "Bruma"],
                "collections_per_year": 1,
                "collection_lifespan_quarters": 12,
                "default_purchase_cost": 100.0,
                "churn": {
                    "starts_from_quarter": 20,
                    "min_per_quarter": 1,
                    "max_per_quarter": 1,
                    "random_seed": 1,
                },
            }
        )

        result = LogisticsSimulation(config).run()

        quarter_nine_records = [
            record for record in result.rotation_records if record.quarter_index == 9
        ]
        oldest_client_record = next(record for record in quarter_nine_records if record.client_id == "C00001")
        newer_client_record = next(record for record in quarter_nine_records if record.client_id == "C00002")

        self.assertEqual(oldest_client_record.incoming_collection, "Bruma")
        self.assertEqual(oldest_client_record.reason, "preferred_collection_purchase")
        self.assertNotEqual(newer_client_record.incoming_collection, "Bruma")

    def test_churn_cancels_launch_purchase_budget_when_matching_signups(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "launch-budget",
                "start_year": 2026,
                "simulation_quarters": 9,
                "quarterly_signups": [0, 0, 0, 0, 0, 1, 1, 0, 1],
                "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
                "future_collections": ["Origen", "Bruma"],
                "collections_per_year": 1,
                "collection_lifespan_quarters": 12,
                "default_purchase_cost": 100.0,
                "churn": {
                    "starts_from_quarter": 9,
                    "min_per_quarter": 1,
                    "max_per_quarter": 1,
                    "random_seed": 1,
                },
            }
        )

        result = LogisticsSimulation(config).run()

        quarter_nine_records = [
            record for record in result.rotation_records if record.quarter_index == 9
        ]
        self.assertFalse(
            any(record.reason == "preferred_collection_purchase" for record in quarter_nine_records)
        )
        self.assertFalse(
            any(record.incoming_collection == "Bruma" for record in quarter_nine_records)
        )

    def test_signup_policy_adds_one_signup_per_churn(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "base-plus-churn",
                "start_year": 2026,
                "simulation_quarters": 4,
                "quarterly_signups": [10, 10, 10, 10],
                "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
                "future_collections": [],
                "collections_per_year": 2,
                "collection_lifespan_quarters": 12,
                "default_purchase_cost": 100.0,
                "churn": {
                    "starts_from_quarter": 3,
                    "min_per_quarter": 1,
                    "max_per_quarter": 1,
                    "random_seed": 1,
                },
                "signup_policy": {
                    "mode": "base_plus_churn",
                    "base_signups_per_quarter": 10,
                },
            }
        )

        result = LogisticsSimulation(config).run()

        self.assertEqual(result.quarter_summaries[0].signups, 10)
        self.assertEqual(result.quarter_summaries[1].signups, 10)
        self.assertEqual(result.quarter_summaries[2].churn, 1)
        self.assertEqual(result.quarter_summaries[2].signups, 11)
        self.assertEqual(result.quarter_summaries[3].churn, 1)
        self.assertEqual(result.quarter_summaries[3].signups, 11)

    def test_operational_bridge_buffer_detects_same_quarter_reuse(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "bridge-buffer",
                "start_year": 2026,
                "simulation_quarters": 2,
                "quarterly_signups": [2, 1],
                "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
                "future_collections": [],
                "collections_per_year": 2,
                "collection_lifespan_quarters": 12,
                "default_purchase_cost": 100.0,
                "churn": {
                    "starts_from_quarter": 20,
                    "min_per_quarter": 1,
                    "max_per_quarter": 1,
                    "random_seed": 1,
                },
            }
        )

        result = LogisticsSimulation(config).run()

        self.assertEqual(result.quarter_summaries[1].ready_pool_start, 0)
        self.assertEqual(result.quarter_summaries[1].reconditioning_inflow, 2)
        self.assertEqual(result.quarter_summaries[1].bridge_pool_required, 2)

    def test_new_cohort_enters_one_week_later_each_quarter(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "weekly-cohorts",
                "start_year": 2026,
                "simulation_quarters": 7,
                "quarterly_signups": [0, 0, 0, 0, 0, 0, 1],
                "initial_collections": ["Aura", "Natura", "Esencia", "Horizonte"],
                "future_collections": [],
                "collections_per_year": 2,
                "collection_lifespan_quarters": 12,
                "default_purchase_cost": 100.0,
                "churn": {
                    "starts_from_quarter": 20,
                    "min_per_quarter": 1,
                    "max_per_quarter": 1,
                    "random_seed": 1
                },
                "logistics": {
                    "cohort_gap_weeks": 1
                }
            }
        )

        result = LogisticsSimulation(config).run()

        client = next(iter(result.clients.values()))
        self.assertEqual(client.cohort_slot, 6)
        self.assertEqual(client.signup_date, date(2027, 8, 12))


if __name__ == "__main__":
    unittest.main()
