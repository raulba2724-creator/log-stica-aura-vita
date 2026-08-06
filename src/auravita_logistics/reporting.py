from __future__ import annotations

from auravita_logistics.simulation import SimulationResult
from auravita_logistics.utils import serialize


def build_report(result: SimulationResult) -> dict:
    lots = sorted(result.inventory.lots.values(), key=lambda lot: lot.id)
    clients = sorted(result.clients.values(), key=lambda client: client.id)
    collections = sorted(result.catalog.collections.values(), key=lambda collection: collection.name)

    return {
        "metadata": {
            "simulation_name": result.config.simulation_name,
            "simulation_quarters": result.config.simulation_quarters,
            "start_year": result.config.start_year,
            "total_estimated_cost": result.total_estimated_cost,
        },
        "quarterly_summary": serialize(result.quarter_summaries),
        "clients": serialize(clients),
        "lots": serialize(lots),
        "collections": serialize(collections),
        "movements": serialize(
            [
                movement
                for lot in lots
                for movement in lot.movement_history
            ]
        ),
        "rotation_calendar": serialize(result.rotation_records),
        "stock_available": serialize([lot for lot in lots if lot.state.value == "STOCK"]),
        "retired_lots": serialize([lot for lot in lots if lot.state.value == "RETIRADO"]),
        "purchases": serialize(
            [
                movement
                for lot in lots
                for movement in lot.movement_history
                if movement.event_type == "PURCHASED"
            ]
        ),
    }


def build_console_summary(report: dict) -> str:
    lines = []
    lines.append(f"Simulación: {report['metadata']['simulation_name']}")
    lines.append(f"Coste estimado total: {report['metadata']['total_estimated_cost']:.2f}")
    lines.append("")
    lines.append("Resumen trimestral")
    for row in report["quarterly_summary"]:
        lines.append(
            (
                f"- {row['quarter_label']}: activos={row['active_clients']}, "
                f"altas={row['signups']}, bajas={row['churn']}, compras={row['purchases']}, "
                f"retirados={row['retired_lots']}, stock_final={row['final_stock']}, "
                f"coste={row['estimated_cost']:.2f}"
            )
        )
    return "\n".join(lines)
