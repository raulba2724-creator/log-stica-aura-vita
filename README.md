# AuraVita Logistics Engine

Motor logístico modular para simular altas, bajas, rotaciones trimestrales, reutilización de lotes y retirada automática de colecciones.

## Estructura

- `src/auravita_logistics/config.py`: configuración centralizada y validación.
- `src/auravita_logistics/models/`: entidades de dominio.
- `src/auravita_logistics/catalog.py`: ciclo de vida de colecciones.
- `src/auravita_logistics/inventory.py`: compras, stock, asignaciones y retiradas.
- `src/auravita_logistics/assignment_engine.py`: reglas de selección de lotes.
- `src/auravita_logistics/rotation_engine.py`: procesamiento trimestral.
- `src/auravita_logistics/simulation.py`: orquestación completa.
- `src/auravita_logistics/reporting.py`: exportación de reportes.
- `src/auravita_logistics/main.py`: CLI.

## Uso

```bash
python -m auravita_logistics.main --config config/default_config.json --json-output outputs/report.json
```

O bien:

```bash
PYTHONPATH=src python -m auravita_logistics.main --config config/default_config.json --html-output outputs/report.html
```

El dashboard HTML permite revisar la simulación visualmente en el navegador.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
