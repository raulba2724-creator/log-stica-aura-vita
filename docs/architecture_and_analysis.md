# Arquitectura y análisis del motor logístico

## Decisiones de arquitectura

- El proyecto está separado por responsabilidad: dominio (`models`), configuración (`config.py`), catálogo de colecciones (`catalog.py`), inventario (`inventory.py`), asignación (`assignment_engine.py`), rotación (`rotation_engine.py`), simulación (`simulation.py`) y reporting (`reporting.py`).
- Todas las reglas variables están en `config/default_config.json`, evitando constantes dispersas en el código.
- La salida se genera como datos estructurados, para que más adelante pueda integrarse en otro sistema o exponerse por API.
- La lógica de asignación no usa scoring ni IA: aplica reglas deterministas y trazables.

## Reglas implementadas

- Un cliente no repite colección dentro de sus últimas 4 rotaciones, salvo imposibilidad absoluta.
- La asignación toma primero stock compatible, luego el lote que más tiempo lleva en stock y, en empate, el de menor numeración.
- Las colecciones recién lanzadas se introducen primero en clientes activos más antiguos, siempre que el trimestre tenga crecimiento neto suficiente para justificar compras de lanzamiento.
- Si no existe lote compatible, se compra automáticamente un lote nuevo de una colección activa compatible.
- Las colecciones viven 12 trimestres exactos y se retiran automáticamente en el trimestre 13.
- Las bajas aleatorias se aplican desde el trimestre configurado y devuelven el lote al stock de inmediato.
- Las bajas del trimestre descuentan presupuesto de compra para lanzamientos, de forma que un volumen equivalente de altas no dispare compras adicionales y no se genere stock evitable.
- El reporting incorpora un gemelo operativo: detecta cuántas reutilizaciones se apoyan en retornos del mismo trimestre y las traduce a `buffer puente` para un modelo real de entrega antes de recogida.

## Supuestos explícitos de esta primera versión

- La simulación opera por trimestre como unidad de negocio principal.
- Las nuevas colecciones entran en el primer trimestre de cada año adicional: `T5`, `T9`, `T13`, etc.
- El stock inicial parte vacío salvo que se configure `preloaded_stock_by_collection`.
- El calendario logístico usa slots de cohorte separados por 2 semanas; en esta primera versión el slot se asigna de forma determinista según el trimestre de alta.
- Cuando hay que comprar un lote nuevo y hay varias colecciones compatibles, se elige la colección activa más antigua y, en empate, la primera por nombre.
- La prioridad por antigüedad se resuelve por fecha real de alta del cliente, no por slot logístico.
- El gemelo operativo asume que un lote devuelto dentro del trimestre no está disponible de inmediato para la misma ola y, por tanto, exige un lote puente equivalente.

## Cuellos de botella potenciales

- La selección de stock recorre la lista completa de lotes en cada asignación. Con decenas de miles de lotes convendrá indexar por `estado` y `colección`.
- Los historiales completos viven en memoria. Para simulaciones largas o integración productiva, habrá que persistir eventos en base de datos o streaming.
- El motor de reporting serializa toda la simulación de una vez. Si el volumen crece mucho, será mejor paginar o exportar por bloques.

## Casos límite a vigilar

- Simulaciones tan largas que consuman todas las colecciones previstas en configuración.
- Trimestres con muy pocos clientes activos, donde la banda de bajas aleatorias podría exceder la población si no se recorta.
- Retirada de una colección mientras sus lotes están en cliente: el sistema hoy los fuerza a retirada y deja al cliente listo para reasignación.
- Escenarios con muchas restricciones históricas y pocas colecciones activas, donde aumentarán las compras o las repeticiones forzadas.

## Mejoras recomendadas

- Añadir una política configurable para decidir qué colección comprar cuando no hay stock: por balance de inventario, cobertura futura o coste.
- Incorporar un módulo de forecasting para estimar déficit de stock varios trimestres por delante, sin romper la regla de decisión determinista.
- Modelar reparaciones y cuarentena de lotes para evitar que todo retorno vuelva a stock utilizable de inmediato.
- Persistir `movements`, `clients`, `lots` y `collections` en una capa repositorio para preparar la integración real con el software principal.
- Añadir tests de regresión para rotaciones forzadas por retirada, reentrada de stock antiguo y escenarios de alta presión de crecimiento.

## Mejoras para reducir compras

- Crear stock de seguridad mínimo por colección activa y trimestre, configurable.
- Reservar lotes escasos para clientes con historial más restrictivo.
- Separar el stock libre del stock comprometido para la siguiente ventana logística.
- Incorporar una política de precompra trimestral basada en cohortes futuras y churn esperado.
