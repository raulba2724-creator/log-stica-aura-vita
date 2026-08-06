from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from datetime import date
from html import escape

from auravita_logistics.simulation import SimulationResult
from auravita_logistics.utils import ensure_parent_directory, quarter_label, rotation_date_for_slot, serialize

MONTHLY_CLIENT_FEE_EX_VAT = 180.0
WEEKLY_RENTAL_VAN_COST = (850.0 * 12) / 52
WEEKLY_DRIVER_COST = (720.0 * 12) / 52
WEEKLY_FUEL_COST = 100.0
MONTHLY_COMMERCIAL_FIXED_COST = 2200.0
MONTHLY_COMMERCIAL_VARIABLE_COST = 400.0 / 3
MONTHLY_COMMON_EXPENSE_START = 300.0
MONTHLY_COMMON_EXPENSE_STEP = 50.0
MONTHLY_LOCAL_RENT_COST = 1300.0
MONTHLY_UTILITIES_COST = 120.0
LOCAL_RENT_START_QUARTER = 3
FULL_CAPACITY_WEEKS_PER_TEAM = 13


def month_index_for_date(start_year: int, value: date) -> int:
    return ((value.year - start_year) * 12) + value.month


def month_end_for_index(start_year: int, month_index: int) -> date:
    year = start_year + ((month_index - 1) // 12)
    month = ((month_index - 1) % 12) + 1
    return date(year, month, calendar.monthrange(year, month)[1])


def build_monthly_financials(result: SimulationResult, quarter_summaries: list[dict]) -> list[dict]:
    total_months = result.config.simulation_quarters * 3
    monthly_rows: list[dict] = []
    weekly_logistics_cost = WEEKLY_RENTAL_VAN_COST + WEEKLY_DRIVER_COST + WEEKLY_FUEL_COST
    monthly_commercial_cost = MONTHLY_COMMERCIAL_FIXED_COST + MONTHLY_COMMERCIAL_VARIABLE_COST

    for month_index in range(1, total_months + 1):
        quarter_index = ((month_index - 1) // 3) + 1
        month_in_quarter = ((month_index - 1) % 3) + 1
        monthly_common_expense = (
            MONTHLY_COMMON_EXPENSE_START
            + ((month_index - 1) * MONTHLY_COMMON_EXPENSE_STEP)
        )
        monthly_local_rent_cost = (
            MONTHLY_LOCAL_RENT_COST
            if quarter_index >= LOCAL_RENT_START_QUARTER
            else 0.0
        )
        monthly_utilities_cost = (
            MONTHLY_UTILITIES_COST
            if quarter_index >= LOCAL_RENT_START_QUARTER
            else 0.0
        )
        monthly_rows.append(
            {
                "month_index": month_index,
                "month_label": f"Mes {month_index}",
                "quarter_index": quarter_index,
                "quarter_label": quarter_label(result.config.start_year, quarter_index),
                "month_in_quarter": month_in_quarter,
                "active_clients": 0,
                "operational_weeks": 0,
                "monthly_revenue_ex_vat": 0.0,
                "monthly_lot_purchase_cost": 0.0,
                "monthly_logistics_cost": 0.0,
                "monthly_commercial_cost": monthly_commercial_cost,
                "monthly_common_expense": monthly_common_expense,
                "monthly_local_rent_cost": monthly_local_rent_cost,
                "monthly_utilities_cost": monthly_utilities_cost,
                "monthly_total_cost": 0.0,
                "monthly_margin_ex_vat": 0.0,
            }
        )

    for month_index in range(1, total_months + 1):
        month_end = month_end_for_index(result.config.start_year, month_index)
        monthly_rows[month_index - 1]["active_clients"] = sum(
            1
            for client in result.clients.values()
            if client.signup_date <= month_end
            and (client.end_date is None or client.end_date > month_end)
        )

    for quarter_index in range(1, result.config.simulation_quarters + 1):
        active_weeks = min(quarter_index, FULL_CAPACITY_WEEKS_PER_TEAM)
        for slot in range(active_weeks):
            # Each active cohort consumes one operative week in its assigned slot.
            week_date = rotation_date_for_slot(
                result.config.start_year,
                quarter_index,
                slot,
                result.config.logistics.cohort_gap_weeks,
            )
            month_index = month_index_for_date(result.config.start_year, week_date)
            if 1 <= month_index <= total_months:
                monthly_rows[month_index - 1]["operational_weeks"] += 1
                monthly_rows[month_index - 1]["monthly_logistics_cost"] += weekly_logistics_cost

    for lot in result.inventory.lots.values():
        month_index = month_index_for_date(result.config.start_year, lot.purchase_date)
        if 1 <= month_index <= total_months:
            monthly_rows[month_index - 1]["monthly_lot_purchase_cost"] += result.config.active_purchase_cost(
                lot.collection_name
            )

    for row in monthly_rows:
        row["monthly_revenue_ex_vat"] = row["active_clients"] * MONTHLY_CLIENT_FEE_EX_VAT
        row["monthly_total_cost"] = (
            row["monthly_lot_purchase_cost"]
            + row["monthly_logistics_cost"]
            + row["monthly_commercial_cost"]
            + row["monthly_common_expense"]
            + row["monthly_local_rent_cost"]
            + row["monthly_utilities_cost"]
        )
        row["monthly_margin_ex_vat"] = row["monthly_revenue_ex_vat"] - row["monthly_total_cost"]
        row["monthly_margin_pct"] = (
            (row["monthly_margin_ex_vat"] / row["monthly_revenue_ex_vat"]) * 100
            if row["monthly_revenue_ex_vat"] > 0
            else 0.0
        )

    running_cash_balance = 0.0
    for row in monthly_rows:
        running_cash_balance += row["monthly_margin_ex_vat"]
        row["cash_balance_ex_vat"] = running_cash_balance

    return monthly_rows


def build_report(result: SimulationResult) -> dict:
    lots = sorted(result.inventory.lots.values(), key=lambda lot: lot.id)
    clients = sorted(result.clients.values(), key=lambda client: client.id)
    collections = sorted(result.catalog.collections.values(), key=lambda collection: collection.name)
    quarter_summaries = serialize(result.quarter_summaries)
    same_quarter_reuse_by_quarter: dict[int, list[dict]] = defaultdict(list)
    for record in serialize(result.rotation_records):
        if record["same_quarter_stock_reuse"]:
            same_quarter_reuse_by_quarter[record["quarter_index"]].append(record)

    running_bridge_peak = 0
    bridge_fleet_purchase_cost = 0.0
    bridge_fleet_purchase_requirement = 0
    for row in quarter_summaries:
        row["monthly_revenue_ex_vat"] = row["active_clients"] * MONTHLY_CLIENT_FEE_EX_VAT
        row["quarterly_revenue_ex_vat"] = row["monthly_revenue_ex_vat"] * 3
        row["net_growth_clients"] = max(row["signups"] - row["churn"], 0)
        row["bridge_buffer_purchase_requirement"] = max(
            row["bridge_pool_required"] - running_bridge_peak,
            0,
        )
        quarter_bridge_records = same_quarter_reuse_by_quarter[row["quarter_index"]]
        row["bridge_buffer_purchase_cost"] = sum(
            result.config.active_purchase_cost(record["incoming_collection"])
            for record in quarter_bridge_records[: row["bridge_buffer_purchase_requirement"]]
        )
        running_bridge_peak = max(running_bridge_peak, row["bridge_pool_required"])
        bridge_fleet_purchase_requirement += row["bridge_buffer_purchase_requirement"]
        bridge_fleet_purchase_cost += row["bridge_buffer_purchase_cost"]
    active_clients = sum(1 for client in clients if client.state.value == "ACTIVO")
    stock_available = [lot for lot in lots if lot.state.value == "STOCK"]
    retired_lots = [lot for lot in lots if lot.state.value == "RETIRADO"]
    purchases = [
        movement
        for lot in lots
        for movement in lot.movement_history
        if movement.event_type == "PURCHASED"
    ]
    stock_by_collection = dict(
        sorted(Counter(lot.collection_name for lot in stock_available).items(), key=lambda item: (-item[1], item[0]))
    )
    monthly_revenue_ex_vat = active_clients * MONTHLY_CLIENT_FEE_EX_VAT
    quarterly_revenue_ex_vat = monthly_revenue_ex_vat * 3
    simulation_total_revenue_ex_vat = sum(
        row["active_clients"] * 3 * MONTHLY_CLIENT_FEE_EX_VAT for row in quarter_summaries
    )
    monthly_financials = build_monthly_financials(result, quarter_summaries)
    peak_bridge_pool_required = max((row["bridge_pool_required"] for row in quarter_summaries), default=0)
    total_reconditioning_inflow = sum(row["reconditioning_inflow"] for row in quarter_summaries)
    total_same_quarter_reuse = sum(row["bridge_pool_required"] for row in quarter_summaries)
    operational_total_estimated_cost = result.total_estimated_cost + bridge_fleet_purchase_cost
    closing_cost_per_active_client = (
        operational_total_estimated_cost / active_clients if active_clients else 0.0
    )
    simulation_total_logistics_cost = sum(row["monthly_logistics_cost"] for row in monthly_financials)
    simulation_total_commercial_cost = sum(row["monthly_commercial_cost"] for row in monthly_financials)
    simulation_total_common_expense = sum(row["monthly_common_expense"] for row in monthly_financials)
    simulation_total_local_rent_cost = sum(row["monthly_local_rent_cost"] for row in monthly_financials)
    simulation_total_utilities_cost = sum(row["monthly_utilities_cost"] for row in monthly_financials)
    simulation_total_operating_cost_ex_vat = sum(row["monthly_total_cost"] for row in monthly_financials)
    simulation_total_margin_ex_vat = sum(row["monthly_margin_ex_vat"] for row in monthly_financials)

    return {
        "metadata": {
            "simulation_name": result.config.simulation_name,
            "simulation_quarters": result.config.simulation_quarters,
            "start_year": result.config.start_year,
            "total_estimated_cost": result.total_estimated_cost,
        },
        "economics": {
            "monthly_client_fee_ex_vat": MONTHLY_CLIENT_FEE_EX_VAT,
            "active_clients_closing": active_clients,
            "monthly_revenue_ex_vat": monthly_revenue_ex_vat,
            "quarterly_revenue_ex_vat": quarterly_revenue_ex_vat,
            "simulation_total_revenue_ex_vat": simulation_total_revenue_ex_vat,
            "simulation_total_margin_ex_vat": simulation_total_margin_ex_vat,
        },
        "operations": {
            "delivery_before_pickup_model": True,
            "peak_bridge_pool_required": peak_bridge_pool_required,
            "total_same_quarter_reuse": total_same_quarter_reuse,
            "total_reconditioning_inflow": total_reconditioning_inflow,
            "bridge_fleet_purchase_requirement": bridge_fleet_purchase_requirement,
            "bridge_fleet_purchase_cost": bridge_fleet_purchase_cost,
            "operational_total_estimated_cost": operational_total_estimated_cost,
        },
        "costs": {
            "base_lot_purchase_cost": result.total_estimated_cost,
            "bridge_buffer_purchase_cost": bridge_fleet_purchase_cost,
            "operational_total_estimated_cost": operational_total_estimated_cost,
            "closing_cost_per_active_client": closing_cost_per_active_client,
            "simulation_total_logistics_cost": simulation_total_logistics_cost,
            "simulation_total_commercial_cost": simulation_total_commercial_cost,
            "simulation_total_common_expense": simulation_total_common_expense,
            "simulation_total_local_rent_cost": simulation_total_local_rent_cost,
            "simulation_total_utilities_cost": simulation_total_utilities_cost,
            "simulation_total_operating_cost_ex_vat": simulation_total_operating_cost_ex_vat,
        },
        "quarterly_summary": quarter_summaries,
        "monthly_financials": monthly_financials,
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
        "stock_available": serialize(stock_available),
        "stock_by_collection": stock_by_collection,
        "retired_lots": serialize(retired_lots),
        "purchases": serialize(purchases),
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
                f"altas={row['signups']}, bajas={row['churn']}, neto={row['net_growth_clients']}, compras={row['purchases']}, "
                f"retirados={row['retired_lots']}, stock_final={row['final_stock']}, "
                f"coste={row['estimated_cost']:.2f}, ingreso_trimestral={row['quarterly_revenue_ex_vat']:.2f}, "
                f"buffer_puente={row['bridge_pool_required']}, compra_buffer={row['bridge_buffer_purchase_requirement']}, "
                f"coste_buffer={row['bridge_buffer_purchase_cost']:.2f}"
            )
        )
    return "\n".join(lines)


def build_html_report(report: dict) -> str:
    quarterly_summary = report["quarterly_summary"]
    stock_available = report["stock_available"]
    stock_by_collection = report["stock_by_collection"]
    retired_lots = report["retired_lots"]
    purchases = report["purchases"]
    clients = report["clients"]
    lots = report["lots"]
    collections = report["collections"]
    economics = report["economics"]
    monthly_financials = report["monthly_financials"]
    max_active = max((row["active_clients"] for row in quarterly_summary), default=1) or 1
    max_stock = max((row["final_stock"] for row in quarterly_summary), default=1) or 1
    max_purchases = max((row["purchases"] for row in quarterly_summary), default=1) or 1

    chart_width = 920
    bar_group_width = chart_width / max(len(quarterly_summary), 1)
    active_scale = 180 / max_active
    stock_scale = 180 / max_stock
    purchases_scale = 180 / max_purchases

    chart_bars = []
    for index, row in enumerate(quarterly_summary):
        base_x = 40 + (index * bar_group_width)
        active_height = row["active_clients"] * active_scale
        stock_height = row["final_stock"] * stock_scale
        purchase_height = row["purchases"] * purchases_scale
        chart_bars.append(
            f"""
            <g>
              <rect x="{base_x:.2f}" y="{220 - active_height:.2f}" width="16" height="{active_height:.2f}" fill="#23577a" rx="3" />
              <rect x="{base_x + 20:.2f}" y="{220 - stock_height:.2f}" width="16" height="{stock_height:.2f}" fill="#49a078" rx="3" />
              <rect x="{base_x + 40:.2f}" y="{220 - purchase_height:.2f}" width="16" height="{purchase_height:.2f}" fill="#f2a65a" rx="3" />
              <text x="{base_x + 28:.2f}" y="242" text-anchor="middle" class="axis-label">{escape(row["quarter_label"])}</text>
            </g>
            """
        )

    summary_rows = "\n".join(
        [
            (
                "<tr>"
                f"<td>{escape(row['quarter_label'])}</td>"
                f"<td>{row['active_clients']}</td>"
                f"<td>{row['signups']}</td>"
                f"<td>{row['churn']}</td>"
                f"<td>{row['net_growth_clients']}</td>"
                f"<td>{row['purchases']}</td>"
                f"<td>{row['retired_lots']}</td>"
                f"<td>{row['final_stock']}</td>"
                f"<td>{row['estimated_cost']:.2f}</td>"
                f"<td>{row['quarterly_revenue_ex_vat']:.2f}</td>"
                "</tr>"
            )
            for row in quarterly_summary
        ]
    )
    monthly_rows = "\n".join(
        [
            (
                "<tr>"
                f"<td>{escape(row['month_label'])}</td>"
                f"<td>{escape(row['quarter_label'])}</td>"
                f"<td>{row['month_in_quarter']}</td>"
                f"<td>{row['operational_weeks']}</td>"
                f"<td>{row['active_clients']}</td>"
                f"<td>{row['monthly_revenue_ex_vat']:.2f}</td>"
                f"<td>{row['monthly_lot_purchase_cost']:.2f}</td>"
                f"<td>{row['monthly_logistics_cost']:.2f}</td>"
                f"<td>{row['monthly_commercial_cost']:.2f}</td>"
                f"<td>{row['monthly_common_expense']:.2f}</td>"
                f"<td>{row['monthly_local_rent_cost']:.2f}</td>"
                f"<td>{row['monthly_utilities_cost']:.2f}</td>"
                f"<td>{row['monthly_total_cost']:.2f}</td>"
                f"<td>{row['monthly_margin_ex_vat']:.2f}</td>"
                f"<td>{row['monthly_margin_pct']:.2f}%</td>"
                f"<td>{row['cash_balance_ex_vat']:.2f}</td>"
                "</tr>"
            )
            for row in monthly_financials
        ]
    )

    client_rows = "\n".join(
        [
            (
                "<tr>"
                f"<td>{escape(client['id'])}</td>"
                f"<td>{escape(client['state'])}</td>"
                f"<td>{escape(client['signup_quarter_label'])}</td>"
                f"<td>{escape(client['current_lot_id'] or '-')}</td>"
                f"<td>{escape(', '.join(client['received_collections']))}</td>"
                f"<td>{len(client['history'])}</td>"
                "</tr>"
            )
            for client in clients
        ]
    )

    lot_rows = "\n".join(
        [
            (
                "<tr>"
                f"<td>{escape(lot['id'])}</td>"
                f"<td>{escape(lot['collection_name'])}</td>"
                f"<td>{escape(lot['state'])}</td>"
                f"<td>{escape(lot['location'])}</td>"
                f"<td>{escape(lot['current_client_id'] or '-')}</td>"
                f"<td>{lot['usage_count']}</td>"
                "</tr>"
            )
            for lot in lots
        ]
    )

    collection_rows = "\n".join(
        [
            (
                "<tr>"
                f"<td>{escape(collection['name'])}</td>"
                f"<td>{escape(collection['launch_quarter_label'])}</td>"
                f"<td>{collection['assignment_count']}</td>"
                f"<td>{len(collection['lot_ids'])}</td>"
                f"<td>{len(collection['retired_lot_ids'])}</td>"
                "</tr>"
            )
            for collection in collections
        ]
    )

    stock_rows = "\n".join(
        [
            (
                "<tr>"
                f"<td>{escape(lot['id'])}</td>"
                f"<td>{escape(lot['collection_name'])}</td>"
                f"<td>{lot['usage_count']}</td>"
                f"<td>{lot['stock_since_quarter_index']}</td>"
                "</tr>"
            )
            for lot in stock_available
        ]
    )
    stock_summary_markup = ", ".join(
        f"{escape(collection_name)}: {quantity}"
        for collection_name, quantity in stock_by_collection.items()
    ) or "Sin stock final."

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AuraVita Logistics Dashboard</title>
  <style>
    :root {{
      --bg: #f6f1e8;
      --panel: #fffaf3;
      --panel-strong: #f0e6d8;
      --ink: #1f2933;
      --muted: #52606d;
      --line: #d7c8b2;
      --blue: #23577a;
      --green: #49a078;
      --orange: #f2a65a;
      --shadow: 0 16px 40px rgba(36, 45, 57, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(73, 160, 120, 0.12), transparent 30%),
        linear-gradient(180deg, #fbf7f0 0%, var(--bg) 100%);
    }}
    main {{
      width: min(1220px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, #1e3d59 0%, #2f5d62 55%, #4f772d 100%);
      color: white;
      border-radius: 28px;
      padding: 28px;
      box-shadow: var(--shadow);
    }}
    .hero h1 {{
      margin: 0 0 6px;
      font-size: clamp(2rem, 3vw, 3.4rem);
    }}
    .hero p {{
      margin: 0;
      color: rgba(255, 255, 255, 0.84);
      max-width: 760px;
      line-height: 1.5;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-top: 22px;
    }}
    .card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
    }}
    .card {{
      padding: 20px;
    }}
    .card .label {{
      color: var(--muted);
      font-size: 0.9rem;
      margin-bottom: 10px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .card .value {{
      font-size: 2rem;
      font-weight: 700;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 1.35fr 1fr;
      gap: 18px;
      margin-top: 22px;
    }}
    .panel {{
      padding: 20px;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 1.2rem;
    }}
    .legend {{
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.92rem;
      margin-bottom: 10px;
    }}
    .legend span::before {{
      content: "";
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 999px;
      margin-right: 8px;
      vertical-align: middle;
    }}
    .legend .active::before {{ background: var(--blue); }}
    .legend .stock::before {{ background: var(--green); }}
    .legend .purchases::before {{ background: var(--orange); }}
    svg {{
      width: 100%;
      height: auto;
      background: linear-gradient(180deg, rgba(255,255,255,0.45), rgba(240, 230, 216, 0.25));
      border-radius: 18px;
      border: 1px solid rgba(215, 200, 178, 0.7);
    }}
    .axis-label {{
      fill: var(--muted);
      font-size: 10px;
      transform: rotate(-35deg);
      transform-origin: center;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      font-size: 0.94rem;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      background: rgba(240, 230, 216, 0.55);
    }}
    details {{
      margin-top: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px 18px;
      box-shadow: var(--shadow);
    }}
    summary {{
      cursor: pointer;
      font-weight: 700;
      font-size: 1.02rem;
    }}
    .small-note {{
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    @media (max-width: 900px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      main {{
        width: min(100vw - 20px, 1220px);
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>{escape(report['metadata']['simulation_name'])}</h1>
      <p>
        Simulación logística de AuraVita desde {report['metadata']['start_year']} durante
        {report['metadata']['simulation_quarters']} trimestres.
      </p>
    </section>

    <section class="grid">
      <article class="card">
        <div class="label">Coste Estimado</div>
        <div class="value">{report['metadata']['total_estimated_cost']:.2f}</div>
      </article>
      <article class="card">
        <div class="label">Clientes</div>
        <div class="value">{len(clients)}</div>
      </article>
      <article class="card">
        <div class="label">Lotes Totales</div>
        <div class="value">{len(lots)}</div>
      </article>
      <article class="card">
        <div class="label">Stock Disponible</div>
        <div class="value">{len(stock_available)}</div>
      </article>
      <article class="card">
        <div class="label">Lotes Retirados</div>
        <div class="value">{len(retired_lots)}</div>
      </article>
      <article class="card">
        <div class="label">Compras</div>
        <div class="value">{len(purchases)}</div>
      </article>
      <article class="card">
        <div class="label">Ingreso Mensual</div>
        <div class="value">{economics['monthly_revenue_ex_vat']:.2f}</div>
      </article>
      <article class="card">
        <div class="label">Ingreso Simulación</div>
        <div class="value">{economics['simulation_total_revenue_ex_vat']:.2f}</div>
      </article>
      <article class="card">
        <div class="label">Margen Simulación</div>
        <div class="value">{economics['simulation_total_margin_ex_vat']:.2f}</div>
      </article>
    </section>

    <section class="layout">
      <article class="panel">
        <h2>Evolución Trimestral</h2>
        <div class="legend">
          <span class="active">Clientes activos</span>
          <span class="stock">Stock final</span>
          <span class="purchases">Compras</span>
        </div>
        <svg viewBox="0 0 980 260" role="img" aria-label="Resumen trimestral">
          <line x1="30" y1="220" x2="950" y2="220" stroke="#c2b59b" stroke-width="1" />
          <line x1="30" y1="20" x2="30" y2="220" stroke="#c2b59b" stroke-width="1" />
          {''.join(chart_bars)}
        </svg>
      </article>
      <article class="panel">
        <h2>Notas</h2>
        <p class="small-note">
          Este dashboard se genera directamente desde la simulación y sirve para validar
          crecimiento, compras, rotaciones, stock y retirada de lotes sin revisar el JSON bruto.
        </p>
        <p class="small-note">
          Ingreso estimado sin IVA al cierre: {economics['active_clients_closing']} clientes activos x
          {economics['monthly_client_fee_ex_vat']:.2f} EUR/mes = {economics['monthly_revenue_ex_vat']:.2f} EUR/mes.
        </p>
        <p class="small-note">
          Ingreso trimestral equivalente: {economics['quarterly_revenue_ex_vat']:.2f} EUR.
        </p>
      </article>
    </section>

    <section class="panel" style="margin-top: 18px;">
      <h2>Resumen Mensual</h2>
      <p class="small-note">
        Esta vista ya tiene en cuenta el desfase semanal acumulado de las cohortes:
        cada trimestre nuevo entra una semana mas tarde y la carga logistica se desplaza
        por los meses del trimestre real, incluyendo alquiler de furgoneta, repartidor y gasoil.
      </p>
      <table>
        <thead>
          <tr>
            <th>Mes</th>
            <th>Trimestre</th>
            <th>Mes T</th>
            <th>Semanas Log.</th>
            <th>Clientes</th>
            <th>Ingresos</th>
            <th>Coste lotes</th>
            <th>Logística</th>
            <th>Comercial</th>
            <th>Gastos comunes</th>
            <th>Alquiler local</th>
            <th>Suministros</th>
            <th>Coste total</th>
            <th>Margen</th>
            <th>Margen %</th>
            <th>Balance caja</th>
          </tr>
        </thead>
        <tbody>
          {monthly_rows}
        </tbody>
      </table>
    </section>

    <section class="panel" style="margin-top: 18px;">
      <h2>Resumen Trimestral Agregado</h2>
      <table>
        <thead>
          <tr>
            <th>Trimestre</th>
            <th>Activos</th>
            <th>Altas brutas</th>
            <th>Bajas</th>
            <th>Crec. neto</th>
            <th>Compras</th>
            <th>Retirados</th>
            <th>Stock Final</th>
            <th>Coste</th>
            <th>Ingreso Trimestral</th>
          </tr>
        </thead>
        <tbody>
          {summary_rows}
        </tbody>
      </table>
    </section>

    <details open>
      <summary>Clientes</summary>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Estado</th>
            <th>Alta</th>
            <th>Lote Actual</th>
            <th>Colecciones Recibidas</th>
            <th>Eventos</th>
          </tr>
        </thead>
        <tbody>
          {client_rows}
        </tbody>
      </table>
    </details>

    <details>
      <summary>Stock Final</summary>
      <p class="small-note">Distribución por colección: {stock_summary_markup}</p>
      <table>
        <thead>
          <tr>
            <th>Lote</th>
            <th>Colección</th>
            <th>Usos</th>
            <th>En stock desde trimestre</th>
          </tr>
        </thead>
        <tbody>
          {stock_rows}
        </tbody>
      </table>
    </details>

    <details>
      <summary>Lotes</summary>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Colección</th>
            <th>Estado</th>
            <th>Ubicación</th>
            <th>Cliente Actual</th>
            <th>Usos</th>
          </tr>
        </thead>
        <tbody>
          {lot_rows}
        </tbody>
      </table>
    </details>

    <details>
      <summary>Colecciones</summary>
      <table>
        <thead>
          <tr>
            <th>Colección</th>
            <th>Lanzamiento</th>
            <th>Asignaciones</th>
            <th>Lotes</th>
            <th>Retirados</th>
          </tr>
        </thead>
        <tbody>
          {collection_rows}
        </tbody>
      </table>
    </details>
  </main>
</body>
</html>
"""


def write_html_report(report: dict, output_path: str) -> None:
    ensure_parent_directory(output_path)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(build_html_report(report))
