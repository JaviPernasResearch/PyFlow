# Propuesta: paridad funcional PyFlow ↔ SimuLean 2.1

> Fecha: 2026-10-05 · Rama base: `MCP-Server` (6fac2b7) · Referencia: `TheSimuLeanProject_2.1/Assets/SimuLean.Net`
>
> Alcance: el motor de eventos discretos sin interfaz (headless). Se excluye todo lo que depende de Unity: render, A* o NavMesh, HUD, inspectores y los agentes que se mueven en tiempo real.

---

## 0. Resumen

| Área | SimuLean 2.1 | PyFlow hoy | Hueco |
|---|---|---|---|
| Reloj | `SimClock` por modelo + `SimContext`, desempate FIFO, `EventHandle.Cancel()`, avanza hasta `t` | Singleton, heap propio con un bug, sin desempate ni cancelación, no avanza hasta `t` | **Crítico** |
| Aleatoriedad | Semilla por modelo, un flujo por sampler (`CreateRandomStream`), 14 distribuciones, `SamplerSpec` `"Tipo~p1~p2"` | `scipy.rvs()` sobre el RNG global, sin semilla | **Crítico** |
| Estados | `ElementStateTracker` (IDLE, PROCESSING, BLOCKED, SETUP, BREAKDOWN, OFF_SHIFT…), log de transiciones y tiempo en cada estado | Solo los tiene el Combiner, y sin estadística | Alto |
| Paradas | `Stop/Resume` (Immediate/AfterCurrent), `WorkHandle` con pausa y reanudación, generadores MTBF/MTTR, por horario y por turnos, `DowntimeTable` | No existe | Alto |
| Calendario | `SimCalendar` (tiempo de simulación ↔ fecha), `WeeklyShiftPattern` con festivos | No existe | Alto |
| Estadísticas | WIP ponderado en el tiempo, log de estados, resumen por elemento | Media de contenido **no** ponderada, sin reset ni calentamiento | Alto |
| Elementos | Queue, GateQueue, LengthLimitedQueue, MultiServer (con OperatorPool), Combiner, AssemblyStation, PickingStation, SkuStockPort, Stacker, ReleaseSource, ProviderSource, CustomerSink… | Queue, MultiServer, Combiner, MultiAssembler, 4 fuentes, Sink | Alto |
| Estrategias | Entrada: 8 variantes, con compuestas AND/OR. Salida: 8 variantes (shortest queue, parametrizada, por prioridad, por etiqueta, delegada…) | Entrada: 3. Salida: 4 | Medio |
| Recursos | `OperatorPool` (semáforo con cola FIFO) | No existe | Alto |
| Almacén | `StorageSystem`, `StorageLane` (Direct/LIFO/FIFO), presets de estanterías, políticas de ubicación, recolocación de bloqueadores | No existe | Medio |
| Transporte | Red en grafo (Dijkstra), `DelayTransportSystem`, `VehicleTransportSystem` (flota y despacho), `TransferPoint` | No existe | Medio |
| Experimentación | Escenarios × réplicas, semilla = base + i, informe en xlsx | Scripts sueltos (`Mains/DOE.py`) | Medio |
| Optimización | Algoritmo genético con cromosoma mixto secuencia + binario + numérico | `SeqOptTools` y un PSO ad hoc | Medio |
| Especificación | `SimulationConfig` (DTO) + registro de handlers por tipo | Esquemas Pydantic para el MCP (solo 4 tipos) | Medio (es la base del YAML) |
| Tests | Programas de consola con aserciones exactas: Feeder/Collector, `At(t, acción)` y semillas fijas | `unittest` sin semillas y con rangos amplios | Alto |

PyFlow ya tiene una ventaja que conviene conservar: los esquemas Pydantic y el servidor MCP. SimuLean no tiene un formato persistible de verdad, porque `JsonUtility` no serializa diccionarios. La especificación declarativa de PyFlow puede acabar siendo **mejor** que la de SimuLean.

---

## 1. Principios de diseño (uso por agentes)

1. **Sin estado global.** Un objeto `Model` (equivalente a `SimContext`) contiene el reloj, el registro de elementos, el RNG, el calendario y los parámetros. Se eliminan el singleton `SimClock`, `Item.ITEM_NUMBER` y la variable de clase `GeneralLink.pending_requests`. Esto permite varios modelos en paralelo en un mismo proceso (MCP multisesión, réplicas con `concurrent.futures`).
2. **Determinismo.** Con `Model(seed=…)` se usa `numpy.random.SeedSequence(seed).spawn()` para dar un `Generator` a cada sampler. Así se obtienen números aleatorios comunes (CRN) entre escenarios. Misma semilla ⇒ mismos resultados, bit a bit.
3. **Especificación como fuente única de verdad.** Cada tipo de elemento se declara una sola vez, con su modelo Pydantic y su constructor, en un registro (`@register_element("MultiServer", spec=MultiServerSpec)`). De ahí se derivan el MCP (`get_supported_types`), la validación, el futuro lector YAML y la documentación. Es el patrón `IElementHandler`/`ElementHandlerRegistry` de SimuLean, pero con esquemas tipados en lugar de bolsas de parámetros con prefijos, que provocan colisiones.
4. **API con argumentos de palabra clave y nombres coherentes.** Se unifican `name`, `model`, `capacity`, `service_time` y `interarrival`, eliminando la mezcla de `sim_clock`/`clock`/`delay_strategy`/`random_times`. Los argumentos van después de `*`.
5. **Salidas estructuradas.** Nada de `print`: se usa `logging`. `model.results()` devuelve dicts o DataFrames serializables a JSON. Los errores llevan un código estable (`E_UNCONNECTED_OUTPUT`, `E_INVALID_DIST`…) y un mensaje accionable.
6. **Validación previa a la ejecución.** `model.validate()` detecta salidas sin conectar, fuentes sin destino, ciclos sin capacidad y distribuciones que pueden dar valores negativos.
7. **Sin `eval`.** Las expresiones sobre etiquetas usan `simpleeval` o un pequeño parser propio sobre `ast` con una lista blanca de operaciones.
8. **Empaquetado.** `pyproject.toml` y Python ≥ 3.11, que ya exigen pandas 3 y numpy 2.4. Los módulos pasan a snake_case. Se mantiene durante una versión una capa de compatibilidad (`SimClock.get_instance()` → `Model` por defecto) para no romper `Mains/` ni el caso CEMI.

### Librerías externas propuestas

| Necesidad | Librería | Motivo |
|---|---|---|
| Cola de eventos | `heapq` (stdlib) | Sustituye a `doubleMinBinaryHeat.py`. Se ordena por `(t, seq)`, con borrado diferido para cancelar eventos. |
| Aleatoriedad | `numpy.random.Generator` + distribuciones congeladas de `scipy.stats` con `random_state` | Ya son dependencias. Admiten flujos independientes. |
| Especificación y validación | `pydantic` v2 | Ya se usa en el MCP. Genera JSON Schema para los agentes. |
| YAML (más adelante) | `ruamel.yaml` o `PyYAML` | El YAML se carga en el mismo modelo Pydantic, sin código específico. |
| Grafo de transporte | `networkx` | Dijkstra con caché, distancias, nodo más cercano. Muy mantenido. |
| Expresiones seguras | `simpleeval` | Sustituye a `eval` en `ExpressionDelayStrategy`. |
| Entrada/salida de datos | `pandas` + `openpyxl`, `sqlite3` (stdlib) | Ya están. `sqlite3` sustituye a `ProjectDatabase`. |
| Intervalos de confianza | `scipy.stats.t` | Ya está. |
| Optimización | `optuna` (numérica o mixta) y `pymoo` (permutaciones, multiobjetivo) | Ambas activas y mantenidas. Sustituyen al GA hecho a mano o con GeneticSharp. |
| Tests | `pytest`, `hypothesis` (propiedades e invariantes), `pytest-xdist` | Estándar. |

**¿Por qué no rehacer el motor sobre SimPy, salabim o Ciw?** SimPy está muy mantenido, pero se basa en procesos (generadores), mientras que la semántica de PyFlow/SimuLean es push/pull con bloqueo (`send` / `unblock` / `notify_available`) y paradas que pausan trabajo. Reimplementarla sobre SimPy costaría más que mantener un núcleo de unas 200 líneas, y se perdería la correspondencia 1:1 con SimuLean, que permite tests de paridad. Recomendación: **núcleo propio pequeño** y librerías externas solo para lo periférico (grafo, RNG, optimización y validación).

---

## 2. Funcionalidades a añadir, por fases

Tamaño orientativo: **S** = menos de 1 día, **M** = 1–3 días, **L** = más de 3 días, con Claude Code.

### Fase 0 — Saneamiento del núcleo (requisito para todo lo demás)

| # | Tarea | Tamaño |
|---|---|---|
| 0.1 | `Model`/contexto sin singleton, con un registro de elementos por modelo y un contador de ítems por modelo. Capa de compatibilidad para el código existente. | M |
| 0.2 | Cola de eventos con `heapq`, desempate `(t, seq)`, `EventHandle` con `cancel()`, y `advance_clock(t)` que deja el reloj exactamente en `t`. | S |
| 0.3 | RNG con semilla por modelo y un flujo por sampler. Un `Sampler` unificado (constante, distribución scipy, expresión), parseo de `"Exponential~0.2"` para paridad con `SamplerSpec` y rechazo de muestras negativas, o truncado explícito. | M |
| 0.4 | Corregir bugs: `swap(i2,1)` en el heap; `MultiServer.unblock` pierde el proceso si falla el envío; `InterArrivalBufferingSource` se detiene y despacha en orden LIFO; `batch_mode` llama a un `Item.add_item` que no existe; `ItemsQueue` con `deque(maxlen)` descarta ítems en silencio y su `unblock` devuelve `None`; `QueueSizeStrategy` no prueba alternativas. | M |
| 0.5 | Estadísticas: `StatTimeWeightedVariable` para el WIP, `reset(t)` y `warmup`. Las proporciones de estado se calculan desde el último reset, no desde t = 0 (SimuLean tiene ese fallo; no hay que copiarlo). | S |
| 0.6 | `pyproject.toml`, eliminar los `sys.path.append("C:/Users/Uxia…")`, `logging` en vez de `print`, y arreglar el patrón de tests de `CLAUDE.md`, que no encuentra ningún fichero. | S |

### Fase 1 — Estados, paradas, calendario

| # | Funcionalidad SimuLean | Diseño en PyFlow | Tamaño |
|---|---|---|---|
| 1.1 | `ElementState` abierto + `ElementStateTracker` | `State` como `str` internado con constantes predefinidas. `element.state`, `time_in_state(s)`, `state_ratio(s)`, `state_log`. El tracker se alimenta solo a través de `_set_state`. | M |
| 1.2 | `ScheduleWork` / `WorkHandle` | `element.schedule_work(fn, delay)` devuelve un handle con `pause()`, `resume()` y `remaining`. Todos los servidores pasan a usarlo. | M |
| 1.3 | `Stop(StopRequest)` / `Resume(token)` | `element.stop(state=BREAKDOWN, mode="immediate"\|"after_current", block_input=True, block_output=None, reason=…)` devuelve un token. Admite paradas solapadas. `GeneralLink` respeta `is_input_blocked` e `is_output_blocked`. | M |
| 1.4 | `MtbfMttrDowntime` (base calendario o tiempo productivo), `TimetableDowntime` (con política de solape), `ShiftDowntime` | Clases `DowntimeGenerator` que se arrancan después de los elementos. | M |
| 1.5 | `SimCalendar`, `WeeklyShiftPattern.parse("Mon-Fri 06:00-14:00; Sat 06:00-14:00")` y festivos | `datetime` de la stdlib. El parser de turnos produce el mismo formato de texto que SimuLean, así que es portable. | S |
| 1.6 | `DowntimeTable` (desde filas, CSV o SQLite) | Función `downtimes_from_table(df, mapping)` que devuelve `{target: [DowntimeInterval]}`. | S |
| 1.7 | Eventos `StateChanged`, `ItemEntered`, `ItemExited`, `Stopped`, `Resumed` | Callbacks muy simples (`element.on("state_changed", fn)`). Sirven para trazas y para medir MTBF sobre tiempo productivo. | S |
| 1.8 | Tiempos de cambio de referencia (setup) | SimuLean tiene el estado `SETUP` pero no lo usa. **Propuesta original:** `MultiServer(setup_time=Sampler \| matriz por tipo)`, que se aplica cuando cambia `item.type`. | S |

### Fase 2 — Ítems, estrategias y elementos de flujo

| # | Elemento o función | Notas de diseño | Tamaño |
|---|---|---|---|
| 2.1 | `Item` | `type`, `priority`, `labels` (numéricas y texto en un solo dict), `sub_items` con `add_item()` y `copy_labels_from()`, y `id` único por modelo. | S |
| 2.2 | Estrategias de entrada | Añadir `OriginType`, `OriginName`, `MaxQueue`, `CompositeAnd` y `CompositeOr`. Se generalizan a **todos** los elementos (`element.input_strategy`), como en `INPUT_STRATEGY_UNIVERSAL.md`. | S |
| 2.3 | Estrategias de salida | Añadir `ShortestQueue`, `MostAvailableCapacity`, `Parameterized(key)` (lee `model.parameters`, útil para DOE), `PriorityRouting`, `LabelRouting(label, mapa, default)` y `Delegate(fn)`. Cada estrategia recibe un `OutputContext`. | S |
| 2.4 | `OperatorPool` | Semáforo con cola FIFO: `request(on_granted, holder)` y `release(holder)`. Se integra en `MultiServer`, `Combiner` y `PickingStation`, con el estado `WAITING_FOR_OPERATOR`. **No copiar el bug de doble liberación de SimuLean.** Más adelante: habilidades y prioridad de petición. | M |
| 2.5 | `GateQueue` | FIFO cuya salida se libera con `release(n)` tokens (órdenes de fabricación, CONWIP). | S |
| 2.6 | `ReleaseSource` | Fuente que se alimenta desde fuera con `enqueue(items)` y libera en FIFO. Útil para agentes ("lanza estas 20 órdenes"). | S |
| 2.7 | `LengthLimitedQueue` | Admisión por longitud (etiqueta `length`, más un `gap`) en varios carriles, con `accept_oversize_on_empty_lane`. | S |
| 2.8 | `Combiner` | Revisar la paridad (`COMBINER_PYTHON_PARITY.md`). Implementar de verdad el `batch_mode`: en SimuLean se guarda pero no se usa, y en PyFlow falla. | S |
| 2.9 | `Stacker` (paletizador) | N posiciones, tiempo de ciclo, reglas FirstNotFull / RoundRobin / ByLabelIndex / ByKey, límite de altura por etiqueta, `release_partial_when_blocked`. La salida es un ítem compuesto. | M |
| 2.10 | `SkuStockPort` | Colas FIFO por SKU con `has(needs)`, `draw(sku, qty)` y `drain_all()`. Es la base de 2.11 y 2.12. | S |
| 2.11 | `PickingStation` + `IPickListSource` | Fuentes de lista de picking estática, por etiqueta (`pick_*`), compuesta y desde SQLite. Incluye `ReturnsPort` para el sobrante. | M |
| 2.12 | `AssemblyStation` | Grafo de precedencias de tareas (validado con `graphlib.TopologicalSorter` de la stdlib), materiales por tarea y `worker_count`. | M |
| 2.13 | `ProviderSource` (aprovisionamiento con plazo de entrega) | Pedido `order(q)` con lead time aleatorio. Se quita la peculiaridad de pedir 1 unidad en `unblock`. | S |
| 2.14 | `Sink` | Contar retrasos usando la etiqueta `due_date` o `deadline`. | S |
| — | **No portar:** `Forklift` y `Operator` heredados (dependen de Unity para el viaje), `CustomerSink.ShipTruck` (ligado a la interfaz), `Timer`, `VElement` | `CustomerSink` puede volver más adelante como `DemandSink` genérico. | — |

### Fase 3 — Almacén y transporte (ver §4 para el diseño de desplazamientos)

| # | Funcionalidad | Tamaño |
|---|---|---|
| 3.1 | `TransportNetwork` sobre `networkx` (nodos con xyz, arcos con longitud, `bidirectional` y `max_speed`) | S |
| 3.2 | `DelayTransportSystem` (carga + distancia/velocidad + descarga, sin flota) | S |
| 3.3 | `VehicleTransportSystem` + `TransportVehicle` (flota como recurso; despacho de la petición más antigua al vehículo libre más cercano; tramos TravelEmpty/Load/TravelLoaded/Unload con traza `VehicleLeg`) | L |
| 3.4 | `TransferPoint` (puente entre flujo y transporte, con reserva de hueco en destino) | M |
| 3.5 | `StorageSystem` + `StorageLane` (Direct/LIFO/FIFO, SingleSku/Mixed), presets (Selective, DriveIn, PushBack, FlowRack…), políticas de ubicación (FirstAvailable, Closest, Random con semilla, DedicatedBySku) y recuperación con filtros y ordenación (FIFO/LIFO/FEFO/ByLabel) que recoloca los bloqueadores | L |
| 3.6 | Mejoras sobre SimuLean: los vehículos se pueden parar con `schedule_work`, vuelta a la base o aparcamiento, uso de `max_speed` | S |

### Fase 4 — Experimentación y optimización

| # | Funcionalidad | Diseño | Tamaño |
|---|---|---|---|
| 4.1 | Escenarios × réplicas | `Experiment(spec, factors={...}, replications=n, warmup=…, horizon=…, base_seed=…)`. Además de la lista explícita de SimuLean, admite **rejilla factorial** y LHS (con `scipy.stats.qmc`). | M |
| 4.2 | Ejecución en paralelo | `ProcessPoolExecutor`. Solo es posible sin estado global (Fase 0). | S |
| 4.3 | Informe | DataFrame largo (escenario, réplica, métrica, valor) más un resumen con media, desviación e **IC t al 95 %**, exportable a CSV, xlsx o JSON. SimuLean no calcula intervalos de confianza. | S |
| 4.4 | Optimización | Adaptador `objective(params) -> métricas`. Backends: `optuna` (numérico o categórico) y `pymoo` (permutaciones y binario, el equivalente al cromosoma Sequence + BinaryPerItem). La aptitud se puede **promediar sobre k réplicas**, algo que SimuLean no hace. | M |
| 4.5 | `DataDictTransformer` | Reordenar o marcar filas del `arrivals_table` de `ScheduleSource` a partir de los genes. Generaliza `SeqOptTools`. | S |
| 4.6 | Corrección de diseño | Pasar la semilla **explícitamente** al `Model` de cada réplica. En SimuLean, `ScenarioEvaluator` solo fija la semilla global y probablemente no controla los samplers en modo headless. | — |

### Fase 5 — Especificación, MCP y YAML

| # | Tarea | Tamaño |
|---|---|---|
| 5.1 | Registro de tipos: `ElementSpec` (Pydantic, unión discriminada por `type`) + `build()` + `wire()`, con construcción en varias pasadas como `HeadlessModelFactory`: calendario → elementos → enlaces → transporte → hooks → paradas | M |
| 5.2 | `ModelSpec` completo: `elements`, `connections` (con puertos `combiner_input`, `stock_input`, `returns_output` y `transport`), `downtimes`, `operator_pools`, `calendar`, `parameters`, `seed` y `horizon` | M |
| 5.3 | `ModelSpec` ↔ JSON ida y vuelta, con tests de round-trip. El YAML es luego solo `yaml.safe_load` → `ModelSpec.model_validate`. | S |
| 5.4 | MCP: exponer todos los tipos registrados de forma automática y añadir `seed`, `warmup`, `run_replications`, `get_state_breakdown`, `validate_model`, `export_spec` y `load_spec`. Sesiones por cliente en lugar de una global, y transporte stdio además de SSE. | M |
| 5.5 | Traza de eventos opcional (JSONL: t, elemento, evento, ítem). Sirve para depurar con agentes y para **reproducir la ejecución en Unity con SimuLean** como visor. | S |

---

## 3. Testing

### 3.1 Estructura

```
tests/
  conftest.py            # fixtures: model(seed), Feeder, Collector, at(t, fn)
  unit/                  # un fichero por elemento/estrategia; deterministas, exactos
  analytical/            # validación frente a teoría de colas (estocásticos, con tolerancia estadística)
  properties/            # hypothesis: invariantes sobre topologías aleatorias
  parity/                # mismos modelos deterministas que SimuLean StandaloneTests → mismos números
  regression/            # golden JSON de modelos de referencia (Mains/, CEMI)
  spec/                  # round-trip ModelSpec, errores de validación, registro
  mcp/                   # cliente MCP real (fastmcp.Client in-memory) además de SimulationSession
```

Los ficheros `test_*.py` de la raíz y `Tests.py` se migran a `tests/` con pytest.

### 3.2 Arnés (copiado del patrón de `StandaloneTests`)

- **`Feeder(interval, items=…)`**: emite a intervalos fijos y, si un ítem es rechazado, lo retiene y reintenta en `unblock`.
- **`Collector()`**: sumidero que registra `(t, item)` y se puede cerrar con `close()` para forzar bloqueos.
- **`at(model, t, fn)`**: programa una intervención, por ejemplo parar en t = 5 y reanudar en t = 10.
- Samplers **constantes** y `Model(seed=1)`, de modo que los valores esperados se calculan a mano y se comparan con `==` o `pytest.approx(abs=1e-9)`.

### 3.3 Tests por funcionalidad nueva (mínimos)

| Funcionalidad | Casos clave |
|---|---|
| Núcleo | Eventos simultáneos en orden FIFO; un evento cancelado no se ejecuta; `advance_clock(t)` deja `now == t`; dos modelos en el mismo proceso no interfieren; misma semilla ⇒ resultados idénticos y semillas distintas ⇒ resultados distintos. |
| Estadísticas | WIP ponderado en el tiempo con un patrón conocido (1 ítem durante 5 s y 0 durante 5 s ⇒ media 0,5); `reset` en el calentamiento; proporción de estados posterior al reset que suma 1. |
| Estados | Secuencia exacta del `state_log` en un servidor bloqueado (IDLE → PROCESSING → BLOCKED → IDLE); suma de `time_in_state` igual al tiempo total. |
| Paradas | Parada inmediata en t = 5, reanudación en t = 10 con trabajo de 10 s ⇒ salida en t = 15 y 5 s en BREAKDOWN; AfterCurrent termina la pieza en curso; paradas solapadas (solo se reanuda al cerrarse todas); bloqueo de entrada y de salida; MTBF/MTTR con base productiva (no cuenta el tiempo en IDLE). |
| Turnos y calendario | Ventana que cruza la medianoche; festivo; `next_change`; OFF_SHIFT con AfterCurrent. |
| Estrategias | Cada estrategia de salida con 3 destinos y estados preparados; las compuestas AND/OR; `Parameterized` cambiando `model.parameters`. |
| OperatorPool | Cola FIFO de peticiones; **sin doble liberación** al bloquearse la salida; WAITING_FOR_OPERATOR medido. |
| GateQueue / ReleaseSource | `release(3)` deja salir exactamente 3. |
| LengthLimitedQueue | Ocupación por longitud y huecos; ítem demasiado largo en un carril vacío. |
| Stacker | Identificadores exactos por pila; cierre por altura; liberación parcial cuando hay bloqueo; las estadísticas cuentan los sub-ítems. |
| Picking / Assembly | Lista de picking cubierta o no cubierta; sobrante hacia `ReturnsPort`; precedencias (ciclo ⇒ error); `worker_count` en paralelo. |
| Transporte | Dijkstra con desempates deterministas; tiempos de los tramos `VehicleLeg` exactos; despacho al vehículo más cercano; `TransferPoint` no envía nada si el destino está lleno. |
| Almacén | Orden LIFO/FIFO por carril; recolocación atómica (si un bloqueador no cabe, no cambia nada); FEFO. |
| Experimentos | Réplicas reproducibles; un IC conocido sobre datos sintéticos; la ejecución en paralelo da lo mismo que en serie. |

### 3.4 Validación analítica (lo que SimuLean no tiene automatizado)

Se usan varias réplicas con semilla, con calentamiento, y la aserción es que el valor teórico cae dentro del **intervalo de confianza al 99 %** de la media. No se usan rangos fijos.

- **M/M/1**: utilización = ρ, Lq = ρ²/(1−ρ), W = 1/(μ−λ).
- **M/M/c**: Erlang C para Wq.
- **M/D/1**: Pollaczek-Khinchine.
- **Ley de Little** en cada elemento: L = λ·W (WIP ponderado frente a throughput × tiempo de estancia).
- **Disponibilidad**: tiempo en BREAKDOWN ≈ MTTR/(MTBF+MTTR).
- **Línea en serie con buffers infinitos**: throughput = min(capacidad de cada etapa).

### 3.5 Propiedades con hypothesis

Sobre topologías aleatorias (fuente → k colas o servidores → sumidero, con estrategias y capacidades aleatorias):
- Conservación: `creados = salidos + WIP` en todo momento.
- El contenido nunca es negativo ni supera la capacidad.
- El reloj es monótono.
- La serialización `ModelSpec` → modelo → `ModelSpec` es idempotente.

### 3.6 Tests de paridad con SimuLean

Los modelos con tiempos constantes no dependen del RNG, así que sus resultados deben coincidir **exactamente** con SimuLean:
1. Se portan los casos de `StandaloneTests/stackertests/Program.cs`, las 89 aserciones.
2. Se exportan como `ModelSpec` algunas escenas de muestra de SimuLean y se comparan contadores y tiempos de estancia ejecutadas con distribuciones constantes.

Esto confirma que la semántica push/pull y de bloqueo es la misma.

---

## 4. Brainstorming: modelado de desplazamientos

De más simple a más rico. Todas las opciones son puramente de eventos discretos, sin pasos de tiempo fijos.

1. **Retardo puro.** `t = carga + d/v + descarga`, sin recursos (`DelayTransportSystem`). Es suficiente cuando el transporte no es el cuello de botella. Un `MultiServer` con capacidad infinita y un sampler de distancia ya lo resuelve.
2. **Red en grafo + flota como recurso.** `networkx` para las rutas; los vehículos se modelan como un pool con posición. Reglas de despacho intercambiables (FIFO, vehículo más cercano, prioridad, por zona) como `DispatchStrategy`, igual que las `OutputStrategy`. Aparcamiento o vuelta a la base configurables.
3. **Perfil cinemático trapezoidal.** `t(d, v_max, a)` analítico (aceleración, crucero, frenado) en vez de `d/v`. Es barato y mejora mucho el realismo en distancias cortas, como las de las carretillas.
4. **Grúas y AS/RS.** Tiempo de Chebyshev `max(dx/vx, dy/vy)` con perfil trapezoidal por eje; doble ciclo almacenar + recuperar. Encaja con `StorageLane` (coordenadas xyz).
5. **Transportador acumulativo con mínimos eventos.** Cada segmento tiene longitud, velocidad y paso mínimo entre ítems. La llegada se calcula como `max(t_entrada + L/v, t_llegada_anterior + paso/v)`, y la capacidad es `L / (longitud + gap)`. Solo hay eventos de entrada y salida, sin ticks. Es el diseño que SimuLean dejó aplazado.
6. **Congestión sin colisiones.** Cada arco o zona se trata como un recurso de capacidad N (un pasillo de un solo sentido, un cruce). Al entrar en el arco se pide el recurso y al salir se libera, lo que da bloqueos realistas sin física. La reserva de tramos se puede extender más adelante (estilo AGV).
7. **Operarios que se desplazan.** El `OperatorPool` con ubicación: la concesión de una petición añade el tiempo de viaje desde la última posición. Así se capta el efecto del recorrido de los operarios entre máquinas sin un sistema de transporte completo. Se puede añadir más adelante con habilidades y prioridad.
8. **Traza de tramos para visualizar después.** Se emite `VehicleLeg(t0, t1, ruta)` en JSONL. Se puede animar con plotly o matplotlib, o **reproducir en Unity con SimuLean** como visor 3D, sin añadir 3D a PyFlow.

**Recomendación:** implementar primero 1 + 2 + 3 (paridad con SimuLean y cinemática barata) y la 8 (la traza). Después, la 5 (transportadores) y la 6 (congestión) si los casos de uso lo piden. La 4 cuando llegue el almacén automático.

---

## 5. Orden de trabajo sugerido

1. **Fase 0** completa, con sus tests. Sin esto, todo lo demás hereda los bugs y el estado global.
2. **Fase 1** (estados y paradas) junto con la parte de estadísticas, porque cambian la base de `Element`.
3. **Fase 5.1–5.3** (registro + `ModelSpec`) **antes** de añadir muchos elementos, para que cada elemento nuevo nazca con su especificación, su soporte en el MCP y sus tests de round-trip.
4. **Fase 2**, empezando por lo de más valor: `OperatorPool`, estrategias, GateQueue/ReleaseSource, setup. Después Stacker/Picking/Assembly.
5. **Fase 4** (experimentos: réplicas, IC, paralelo).
6. **Fase 3** (transporte y almacén).
7. Lector YAML (trivial una vez hecha la 5.3).

---

## 7. Estado (actualizado 2026-10-06, rama `fase-1`)

| Fase | Estado | Notas |
|---|---|---|
| 0 — Núcleo | ✅ Hecha (93d278e) | `Model` sin singleton, `heapq` con `(t, seq)` y `EventHandle`, `sampling.py` (semillas por flujo y `"Tipo~p1~p2"`), `expressions.py` (`ast` con lista blanca, sin `eval`), WIP ponderado, `run(until, warmup=)`, `pyproject.toml`, tests en `tests/` y `standard_lines.py` |
| 1 — Estados, paradas, calendario | ✅ Hecha (758518c) | `states.py`, `stops.py`, `work.py`, `downtime.py`, `simcalendar.py`, estrategias de entrada y salida ampliadas, `setup_time` en `MultiServer` |
| 2 — Elementos | 🔄 En curso | ✅ Recursos compartidos: `ResourcePool` genérico (operarios, robots, herramientas…) con habilidades, cantidad, fase (setup/proceso), asignación todo o nada, prioridad y política de liberación; integrado en MultiServer, Combiner y MultiAssembler, en la spec y en el MCP. Sustituye al OperatorPool de SimuLean sin su bug de doble liberación. Faltan GateQueue, ReleaseSource, LengthLimitedQueue, Stacker, SkuStockPort, Picking, Assembly, ProviderSource |
| 3 — Transporte y almacén | ⏳ Pendiente | |
| 4 — Experimentación y optimización | ⏳ Pendiente | La rama `origin/PyFlow-MCP-Server-I3M` (d5aad2f) tiene tests de experimentos y modelos de referencia sin integrar en `fase-1` |
| 5 — Especificación, MCP y YAML | ✅ 5.1–5.4 hechas · ⏳ 5.5 | `PyFlow/spec/`: registro de tipos (`register_element`), `ModelSpec` (JSON, YAML opcional con PyYAML), validación con códigos `E_*`/`W_*` y `path`, `ModelBuilder` incremental y `BuiltModel`. MCP: sesión por cliente, `load_model_spec`, `export_model_spec`, `validate_model`, `add_downtimes_batch`, `set_parameters`, `new_model(seed, calendar, parameters)`, `run_experiment(warmup)`, stdio. Pendiente: traza de eventos JSONL (5.5) y `run_replications` (con la Fase 4) |

Decisión posterior a la propuesta (ver `CLAUDE.md`): **preferir la stdlib o código propio antes que añadir dependencias**. Por eso `simpleeval` se sustituyó por un evaluador propio. Para `networkx`, `optuna` y `pymoo` habrá que decidirlo cuando se llegue a las Fases 3 y 4.

Tests: 387 pasan (Python 3.12, `python -m pytest`).

Notas de la Fase 5:
- `pydantic` pasa a ser dependencia del núcleo y `mcp` se fija a `<2`, porque mcp 2.x renombra FastMCP.
- Arreglado un bug de la Fase 1: tras repetir `initialize()`, el reloj contaba mal los eventos pendientes y el MCP cortaba con `network_idle`.
- Siguiente paso: Fase 2. Cada elemento nuevo debe nacer con su clase de spec registrada, sus tests y su soporte en el MCP.

## 6. Avisos detectados durante el análisis

- **Seguridad:** `langflow/Flexsim MCP Agent.json` está versionado en git y contiene una API key de OpenRouter (`sk-or-v1-…`). Hay que rotarla y eliminarla del historial.
- `ExpressionDelayStrategy` ejecuta `eval()` sobre cadenas arbitrarias.
- `CLAUDE.md` indica `-p "*_test.py"`, pero los ficheros se llaman `test_*.py`, así que el comando no encuentra ningún test.
- `requirements.txt` es un `pip freeze` que incluye `pywin32` y no incluye `parameterized`, que necesita `test_CEMIPreviasModel`.
- `DOCUMENTATION.md` §15 afirma que las estadísticas se resetean en `initialize()`, pero no es así.
