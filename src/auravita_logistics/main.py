from __future__ import annotations

from argparse import ArgumentParser
import json

from auravita_logistics.config import load_config
from auravita_logistics.reporting import build_console_summary, build_report, write_html_report
from auravita_logistics.simulation import LogisticsSimulation
from auravita_logistics.utils import dump_json, serialize


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Motor logístico de AuraVita Espacios")
    parser.add_argument("--config", required=True, help="Ruta al archivo JSON de configuración")
    parser.add_argument("--json-output", help="Ruta para guardar el reporte JSON")
    parser.add_argument("--html-output", help="Ruta para guardar un dashboard HTML")
    parser.add_argument("--print-json", action="store_true", help="Imprimir el reporte JSON por stdout")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    result = LogisticsSimulation(config).run()
    report = build_report(result)

    print(build_console_summary(report))
    if args.json_output:
        dump_json(report, args.json_output)
    if args.html_output:
        write_html_report(report, args.html_output)
    if args.print_json:
        print(json.dumps(serialize(report), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
