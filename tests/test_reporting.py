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
        self.assertIn("html", html)


if __name__ == "__main__":
    unittest.main()
