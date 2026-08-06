from __future__ import annotations

from html import escape

from auravita_logistics.simulation import SimulationResult
from auravita_logistics.utils import ensure_parent_directory, serialize


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


def build_html_report(report: dict) -> str:
    quarterly_summary = report["quarterly_summary"]
    stock_available = report["stock_available"]
    retired_lots = report["retired_lots"]
    purchases = report["purchases"]
    clients = report["clients"]
    lots = report["lots"]
    collections = report["collections"]

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
                f"<td>{row['purchases']}</td>"
                f"<td>{row['retired_lots']}</td>"
                f"<td>{row['final_stock']}</td>"
                f"<td>{row['estimated_cost']:.2f}</td>"
                "</tr>"
            )
            for row in quarterly_summary
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
          Para probar otros escenarios basta con editar el archivo de configuración y volver a ejecutar
          el motor con salida HTML.
        </p>
      </article>
    </section>

    <section class="panel" style="margin-top: 18px;">
      <h2>Resumen Trimestral</h2>
      <table>
        <thead>
          <tr>
            <th>Trimestre</th>
            <th>Activos</th>
            <th>Altas</th>
            <th>Bajas</th>
            <th>Compras</th>
            <th>Retirados</th>
            <th>Stock Final</th>
            <th>Coste</th>
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
