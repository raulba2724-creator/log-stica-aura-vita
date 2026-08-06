from __future__ import annotations

import unittest

from auravita_logistics.config import SimulationConfig
from auravita_logistics.reporting import build_html_report, build_report
from auravita_logistics.simulation import LogisticsSimulation


class ReportingTests(unittest.TestCase):
    def test_html_report_contains_core_sections(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "html",
                "start_year": 2026,
                "simulation_quarters": 1,
                "quarterly_signups": [1],
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
                }
            }
        )

        report = build_report(LogisticsSimulation(config).run())
        html = build_html_report(report)

        self.assertIn("AuraVita Logistics Dashboard", html)
        self.assertIn("Resumen Trimestral", html)
        self.assertIn("Clientes", html)
        self.assertIn("Ingreso Mensual", html)
        self.assertIn("Stock Final", html)
        self.assertIn("Resumen Mensual", html)
        self.assertIn("Gastos comunes", html)
        self.assertIn("Alquiler local", html)
        self.assertIn("Suministros", html)
        self.assertIn("Semanas Log.", html)
        self.assertIn("Balance caja", html)
        self.assertIn("Margen %", html)
        self.assertIn("html", html)

    def test_monthly_financials_include_escalating_common_expense(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "monthly",
                "start_year": 2026,
                "simulation_quarters": 2,
                "quarterly_signups": [1, 1],
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
                }
            }
        )

        report = build_report(LogisticsSimulation(config).run())
        monthly_financials = report["monthly_financials"]

        self.assertEqual(len(monthly_financials), 6)
        self.assertEqual(monthly_financials[0]["monthly_common_expense"], 300.0)
        self.assertEqual(monthly_financials[1]["monthly_common_expense"], 350.0)
        self.assertEqual(monthly_financials[2]["monthly_common_expense"], 400.0)
        self.assertEqual(monthly_financials[5]["monthly_common_expense"], 550.0)

    def test_local_rent_starts_in_third_quarter(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "rent",
                "start_year": 2026,
                "simulation_quarters": 3,
                "quarterly_signups": [1, 1, 1],
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
                }
            }
        )

        report = build_report(LogisticsSimulation(config).run())
        monthly_financials = report["monthly_financials"]

        self.assertEqual(monthly_financials[5]["monthly_local_rent_cost"], 0.0)
        self.assertEqual(monthly_financials[6]["monthly_local_rent_cost"], 1300.0)
        self.assertEqual(monthly_financials[8]["monthly_local_rent_cost"], 1300.0)

    def test_utilities_start_with_local_in_third_quarter(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "utilities",
                "start_year": 2026,
                "simulation_quarters": 3,
                "quarterly_signups": [1, 1, 1],
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
                }
            }
        )

        report = build_report(LogisticsSimulation(config).run())
        monthly_financials = report["monthly_financials"]

        self.assertEqual(monthly_financials[5]["monthly_utilities_cost"], 0.0)
        self.assertEqual(monthly_financials[6]["monthly_utilities_cost"], 120.0)
        self.assertEqual(monthly_financials[8]["monthly_utilities_cost"], 120.0)

    def test_monthly_financials_reflect_weekly_cohort_delay(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "weekly-delay",
                "start_year": 2026,
                "simulation_quarters": 5,
                "quarterly_signups": [1, 1, 1, 1, 1],
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

        report = build_report(LogisticsSimulation(config).run())
        monthly_financials = report["monthly_financials"]

        self.assertEqual(monthly_financials[0]["operational_weeks"], 1)
        self.assertEqual(monthly_financials[3]["operational_weeks"], 2)
        self.assertEqual(monthly_financials[6]["operational_weeks"], 3)
        self.assertEqual(monthly_financials[12]["operational_weeks"], 5)
        self.assertEqual(monthly_financials[13]["operational_weeks"], 0)

    def test_monthly_financials_include_running_cash_balance(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "cash-balance",
                "start_year": 2026,
                "simulation_quarters": 1,
                "quarterly_signups": [1],
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
                }
            }
        )

        report = build_report(LogisticsSimulation(config).run())
        monthly_financials = report["monthly_financials"]

        self.assertEqual(
            monthly_financials[0]["cash_balance_ex_vat"],
            monthly_financials[0]["monthly_margin_ex_vat"],
        )
        self.assertEqual(
            monthly_financials[1]["cash_balance_ex_vat"],
            monthly_financials[0]["monthly_margin_ex_vat"] + monthly_financials[1]["monthly_margin_ex_vat"],
        )

    def test_monthly_financials_include_margin_percentage(self) -> None:
        config = SimulationConfig.from_dict(
            {
                "simulation_name": "margin-pct",
                "start_year": 2026,
                "simulation_quarters": 1,
                "quarterly_signups": [1],
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
                }
            }
        )

        report = build_report(LogisticsSimulation(config).run())
        first_row = report["monthly_financials"][0]

        expected_pct = (first_row["monthly_margin_ex_vat"] / first_row["monthly_revenue_ex_vat"]) * 100
        self.assertAlmostEqual(first_row["monthly_margin_pct"], expected_pct)


if __name__ == "__main__":
    unittest.main()
