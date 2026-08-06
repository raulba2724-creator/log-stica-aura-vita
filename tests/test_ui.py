from __future__ import annotations

import unittest

from auravita_logistics.ui import (
    render_page,
    config_to_form_values,
    flatten_post_data,
    form_values_to_config,
    parse_int_list,
    parse_mapping,
    parse_string_list,
)
from auravita_logistics.reporting import build_report
from auravita_logistics.simulation import LogisticsSimulation


class UITests(unittest.TestCase):
    def test_parse_string_list_accepts_commas_and_lines(self) -> None:
        self.assertEqual(
            parse_string_list("Aura, Natura\nEsencia"),
            ["Aura", "Natura", "Esencia"],
        )

    def test_parse_int_list_parses_multiple_values(self) -> None:
        self.assertEqual(parse_int_list("20\n30,15"), [20, 30, 15])

    def test_parse_mapping_requires_equals_separator(self) -> None:
        with self.assertRaises(ValueError):
            parse_mapping("Aura:450", float)

    def test_flatten_post_data_returns_last_value(self) -> None:
        payload = b"simulation_name=demo&simulation_name=demo2&start_year=2026"
        self.assertEqual(
            flatten_post_data(payload),
            {"simulation_name": "demo2", "start_year": "2026"},
        )

    def test_form_values_round_trip_to_config(self) -> None:
        form_values = {
            "simulation_name": "demo",
            "start_year": "2026",
            "simulation_quarters": "4",
            "quarterly_signups": "10\n12\n8\n9",
            "initial_collections": "Aura, Natura, Esencia, Horizonte",
            "future_collections": "Origen\nBruma",
            "collections_per_year": "2",
            "collection_lifespan_quarters": "12",
            "default_purchase_cost": "100",
            "purchase_cost_by_collection": "Aura=100\nNatura=110",
            "preloaded_stock_by_collection": "Aura=3",
            "fixed_new_lots_per_quarter": "10",
            "churn_starts_from_quarter": "3",
            "churn_min_per_quarter": "1",
            "churn_max_per_quarter": "2",
            "churn_random_seed": "7",
            "signup_policy_mode": "base_plus_churn",
            "base_signups_per_quarter": "10",
            "client_prefix": "C",
            "lot_prefix": "L",
            "client_pad": "5",
            "lot_pad": "5",
            "lookback_rotations": "4",
            "allow_repeat_when_no_alternative": "on",
            "new_lot_collection_strategy": "oldest_active_then_name",
            "warehouse_location": "ALMACEN",
            "retired_location": "RETIRADO",
            "repair_location": "REPARACION",
            "cohort_gap_weeks": "2",
        }

        config = form_values_to_config(form_values)
        round_trip = config_to_form_values(config)

        self.assertEqual(config.simulation_name, "demo")
        self.assertEqual(config.quarterly_signups, [10, 12, 8, 9])
        self.assertEqual(config.preloaded_stock_by_collection["Aura"], 3)
        self.assertEqual(config.purchase_policy.fixed_new_lots_per_quarter, 10)
        self.assertEqual(config.signup_policy.mode, "base_plus_churn")
        self.assertEqual(round_trip["simulation_name"], "demo")

    def test_render_page_shows_monthly_cost_table(self) -> None:
        config = form_values_to_config(
            {
                "simulation_name": "demo",
                "start_year": "2026",
                "simulation_quarters": "1",
                "quarterly_signups": "10",
                "initial_collections": "Aura, Natura, Esencia, Horizonte",
                "future_collections": "",
                "collections_per_year": "2",
                "collection_lifespan_quarters": "12",
                "default_purchase_cost": "100",
                "purchase_cost_by_collection": "",
                "preloaded_stock_by_collection": "",
                "fixed_new_lots_per_quarter": "10",
                "churn_starts_from_quarter": "20",
                "churn_min_per_quarter": "1",
                "churn_max_per_quarter": "1",
                "churn_random_seed": "7",
                "signup_policy_mode": "fixed_schedule",
                "base_signups_per_quarter": "10",
                "client_prefix": "C",
                "lot_prefix": "L",
                "client_pad": "5",
                "lot_pad": "5",
                "lookback_rotations": "4",
                "allow_repeat_when_no_alternative": "on",
                "new_lot_collection_strategy": "oldest_active_then_name",
                "warehouse_location": "ALMACEN",
                "retired_location": "RETIRADO",
                "repair_location": "REPARACION",
                "cohort_gap_weeks": "2",
            }
        )
        report = build_report(LogisticsSimulation(config).run())
        html = render_page(config_to_form_values(config), report=report)

        self.assertIn("Resumen mensual", html)
        self.assertIn("Gastos comunes", html)
        self.assertIn("Alquiler local", html)
        self.assertIn("Suministros", html)
        self.assertIn("Semanas log.", html)
        self.assertIn("Balance caja", html)
        self.assertIn("Margen %", html)
        self.assertIn("300.00", html)


if __name__ == "__main__":
    unittest.main()
