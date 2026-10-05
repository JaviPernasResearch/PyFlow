# Informe de bugs de SimuLean 2.1 para corregir

> Origen: análisis de paridad PyFlow ↔ SimuLean (2026-10-05). Todos los bugs se han verificado leyendo el código.
> Rutas relativas a `TheSimuLeanProject_2.1/Assets/`. Los números de línea corresponden al estado del repo en esa fecha.
>
> **Instrucciones para la IA:**
> - Corrige cada bug con el cambio mínimo indicado.
> - Añade un test de regresión en `StandaloneTests`, con el patrón Feeder/Collector y `AdvanceClock`, que falle antes del arreglo y pase después.
> - No cambies APIs públicas salvo donde se indica.
> - Prioridad: **P1** da resultados de simulación incorrectos, **P2** corrompe el estado en casos concretos, **P3** son robustez o UX.

---

## P1 — Resultados incorrectos

### 1. Las réplicas y los escenarios no usan su semilla
- **Dónde:**
  - `SimuLean.Experimentation/Runner/ScenarioEvaluator.cs:81` solo hace `RandomEngineManager.SetGlobalSeed(seed)`.
  - `SimuLean.Optimization/Evaluator/GenericParameterEvaluator.cs:85` crea `new SimClock(localConfig.UseFixedSeed ? (int?)localConfig.Seed : null)`.
- **Problema:** los samplers sacan sus flujos de `clock.Context` (`SimuLean.Net/Serialization/ElementBuildHelpers.cs:27-32`), no del motor global.
  - Con `UseFixedSeed=true`, todas las réplicas y escenarios usan la misma semilla y salen idénticos.
  - Con `false`, la semilla sale de `TickCount` y no se puede reproducir.
  - Además, `SetGlobalSeed` provoca una condición de carrera con réplicas en paralelo (`Experimenter.cs:266-269`).
- **Arreglo:**
  - Pasar la semilla de la réplica a `RunSimulation(..., int seed)` y crear `new SimClock(seed)`.
  - Eliminar `SetGlobalSeed`.
  - Convención: semilla = `baseSeed + índice de réplica`.
- **Test:** dos réplicas con semillas distintas dan resultados distintos; la misma semilla da resultados idénticos, también en paralelo.

### 2. Doble liberación del operario cuando la salida está bloqueada
- **Dónde:**
  - `SimuLean.Net/SimElements/Combiner.cs:319` libera antes de `SendItem`, y `:165` (`Unblock`) vuelve a liberar.
  - `Multiserver.cs:163` y `:108` repiten el mismo patrón.
  - `OperatorPool.cs:73-97` (`Release`) no tiene ninguna protección. En la línea 80, si no encuentra al titular borra el último, que puede pertenecer a otra estación. `AvailableOperators` llega a superar el total.
- **Arreglo:** una sola política en todos los elementos. Recomendada: retener el operario mientras el elemento está BLOCKED (como dice el comentario de `Combiner.cs:339`).
  - Quitar la liberación en `CompleteServerProcess` (Combiner:319, MultiServer:163).
  - Liberar solo cuando el envío tenga éxito, tanto en `CompleteServerProcess` como en `Unblock`.
  - En `OperatorPool.Release`: si el titular no existe o `BusyOperators == 0`, no hacer nada y registrar un aviso.
  - `PickingStation.cs:219` libera antes de enviar (sin doble liberación). Hay que alinearlo con la política elegida.
- **Test:** pool de 1 operario y 2 estaciones con la salida cerrada: `AvailableOperators` nunca pasa de 1 y no se concede ningún operario inexistente.

### 3. La estrategia de entrada se comprueba después de elegir destino
- **Dónde:**
  - `SimLink/GeneralLink.cs:54-68`: la estrategia de salida elige el índice y solo después se llama a `target.ValidateInput(item, source)`.
  - `SimElements/ElementDowntime.cs:225`: `CanAccept(item) => !IsInputBlocked && CheckAvaliability(item)` no incluye la estrategia de entrada.
- **Problema:** si el destino elegido rechaza el ítem por su estrategia de entrada, el ítem espera aunque otro destino lo aceptaría. Por ejemplo, FirstAvailable con Q0 filtrando por origen y Q1 libre.
- **Arreglo:**
  - `CanAccept(Item item, Element origin = null) => !IsInputBlocked && CheckAvaliability(item) && ValidateInput(item, origin)`.
  - Pasar `context.Source` como origen en todas las estrategias de `OutputStrategy.cs`.
  - En `SendItem`, volver a comprobar `CanAccept(item, source)` del destino elegido, por si alguna estrategia propia no lo hace.

### 4. `MaxQueueInputStrategy` no tiene efecto
- **Dónde:** `SimElements/InputStrategy.cs:248` (`CanAccept`). El motor nunca llama a `InputStrategy.CanAccept` (solo lo hacen las propias compuestas, en las líneas 295 y 351), y `MaxQueueInputStrategy.IsValid` devuelve siempre `true`.
- **Arreglo:** dentro del arreglo 3, que `ValidateInput` (o `Element.CanAccept`) llame a `inputStrategy.CanAccept(this, item, origin)`.
- **Test:** con `MaxQueue(2)` en Q0, el tercer ítem va a Q1.

### 5. Reenvío duplicado por reentrada (Source → CombinerInput)
- **Dónde:**
  - `SimElements/CombinerInput.cs:132-135`: `Receive` llama a `GetInput().NotifyAvaliable(this)` *dentro* de `Receive`.
  - `Source.cs:502-505` (`Unblock`) envía `lastItem` y lo pone a `null` *después* de que `SendItem` devuelva el control.
  - `Source.cs:315-318` usa `Peek()` y luego `Dequeue()`, con el mismo problema.
- **Problema:** `NotifyAvaliable` vuelve a llamar a `Source.Unblock`, que aún tiene el mismo ítem pendiente y lo envía otra vez. El mismo ítem entra dos veces en la entrada del Combiner. En PyFlow se ha reproducido con una fuente conectada directamente a la entrada de un Combiner.
- **Arreglo:** retirar el ítem del hueco pendiente **antes** de `SendItem` y devolverlo si el envío falla. Revisar todos los `Unblock` que usan `Peek`/`lastItem` antes de enviar.
- **Test:** fuente conectada directamente a la entrada de un Combiner con requisito 2: cada unidad lleva componentes distintos y no hay ningún id repetido.

### 6. `ParameterizedRoutingStrategy` con "round_robin" no rota
- **Dónde:** `SimLink/OutputStrategy.cs:162, 175-176`. `GetStrategyFromMode` crea un `new RoundRobinStrategy()` en cada llamada, así que siempre empieza en el índice 0.
- **Arreglo:** cachear una instancia por modo en campos de la clase.

### 7. Las estadísticas no se resetean al reiniciar
- **Dónde:** las sobrecargas de `Start()` que no llaman a `base.Start()` ni a `StatsCollector.Reset()`:
  - `Multiserver.cs:58-78`, `ItemsQueue.cs:33-38`, `Combiner.cs:81-92`
  - `Forklift.cs:44`, `LengthLimitedQueue.cs:150`, `CustomerSink.cs:68`, `ProviderSource.cs:48`
  - `GateQueue.cs:36`, `Sink.cs:54`, `Operator.cs:37`, `Source.cs:305/489`
- **Problema:** al ejecutar dos veces la misma instancia del modelo, se acumulan las entradas y salidas, el contenido y las estancias de la ejecución anterior.
- **Arreglo:** llamar a `base.Start()` (o a `ResetStateTracker(); StatsCollector.Reset();`) en cada una.

### 8. `AssemblyStation` puede dejar un trabajo atascado
- **Dónde:** `SimElements/AssemblyStation.cs:297`: `if (job == null || CurrentState != ElementState.BLOCKED) return false;`
- **Problema:** `CurrentState` es el estado *visible*. Durante una parada se muestra el estado de la parada, aunque la salida no esté bloqueada (AfterCurrent o paradas solapadas). `Unblock` entonces devuelve `false` y el trabajo se queda atascado.
- **Arreglo:** usar `UnderlyingState` o un flag privado `blocked`.

### 9. Fechas de `DowntimeTable` con día y mes intercambiados
- **Dónde:** `Downtime/DowntimeTable.cs:102` hace `Convert.ToString(v, InvariantCulture)` sobre un `DateTime` y produce `MM/dd/yyyy`. Después, `SimCalendar.TryParseDate` (`SimClock/SimCalendar.cs:34-38`) prueba primero `dd/MM/yyyy`.
- **Problema:** las fechas con día ≤ 12 salen con día y mes intercambiados sin ningún aviso.
- **Arreglo:** en `TryTime`, `if (v is DateTime dt) { t = cal.ToSimTime(dt); return true; }`, y lo mismo para `DateTimeOffset`, antes de convertir a texto.

---

## P2 — Estado corrupto en casos concretos

### 10. Los contadores de parada se pueden corromper
- **Dónde:** `SimElements/ElementDowntime.cs`:
  - `Stop` (líneas 245-247) y `Resume` (líneas 266-268) leen `BlockInput`, `BlocksOutput` y `Mode` de un `StopRequest` mutable y reutilizable (líneas 19-33).
  - `RefreshDownState` (línea 345) lee `Mode` en el momento.
- **Problema:** si se modifica la petición entre `Stop` y `Resume`, `_inputBlocks`, `_outputBlocks` e `_immediateStops` quedan mal o incluso negativos, y el elemento se queda bloqueado para siempre.
- **Arreglo:** copiar `State`, `Mode`, `BlockInput` y `BlocksOutput` en campos de solo lectura de `StopToken` al crearlo, y usarlos en `Resume` y `RefreshDownState`. Alternativa: hacer `StopRequest` inmutable.

### 11. Un único aviso al reanudar deja ítems atascados aguas arriba
- **Dónde:** `ElementDowntime.cs:278`: `if (!IsInputBlocked) GetInput()?.NotifyAvaliable(this);`
- **Problema:** si el elemento reanudado deja pasar los ítems directamente (una cola vacía que reenvía dentro de `Receive`), solo avanza un ítem; el resto espera hasta un evento posterior. Una MultiServer con capacidad N trabaja de uno en uno.
- **Arreglo:** `while (!IsInputBlocked && GetFreeCapacity() > 0 && GetInput()?.NotifyAvaliable(this) == true) {}`, con un tope de iteraciones.

### 12. Cancelar trabajo no muestra la parada AfterCurrent
- **Dónde:** `ElementDowntime.cs:140-148` (`WorkHandle.Cancel`) no llama a `owner.AfterWorkCompleted()`, cosa que `Execute` sí hace en la línea 157.
- **Arreglo:** llamar a `owner.AfterWorkCompleted()` después de `ForgetWork`.

### 13. `TimetableDowntime` ignora el `Mode` del generador
- **Dónde:** `Downtime/DowntimeGenerators.cs:194`. El modo del intervalo siempre gana, y por defecto es `Immediate` (`DowntimeInterval` en la línea 19). El estado, en cambio, sí cae al del generador.
- **Arreglo:** declarar `StopMode? Mode` en `DowntimeInterval` y usar `iv.Mode ?? Mode`.

### 14. Los eventos de fin de parada de Timetable no se cancelan
- **Dónde:** `DowntimeGenerators.cs:195` programa `EndStopEvent` sin guardar el handle, y `CancelPending` (líneas 169-173) solo cancela el siguiente inicio.
- **Arreglo:** guardar los handles y cancelarlos en `CancelPending`.

### 15. MultiServer marca un hueco libre como PROCESSING
- **Dónde:** `Multiserver.cs:113`: `theProcess.state = currentItems == 0 ? ... IDLE : ... PROCESSING;` sobre un proceso que acaba de volver al conjunto de libres.
- **Arreglo:** `theProcess.SetState(State.IDLE);`, como en la línea 173.

---

## P3 — Robustez, métricas y UX

### 16. Las proporciones de estado se calculan desde t = 0
- **Dónde:** `SimElements/ElementStateTracker.cs:95-100` divide por `simTime`, y `Reset` (líneas 126-135) no guarda el instante del reset.
- **Arreglo:** añadir un campo `_resetAt` y usar `total = simTime - _resetAt`. Es necesario para tener calentamiento.

### 17. No hay calentamiento
- **Dónde:** `SimuLean.Unity/Editor/Tools/SimuLeanExperimenter.cs:11`. El campo `warmupTime` no se usa.
- **Arreglo:** programar en `warmupTime` un evento que resetee las estadísticas y los trackers de estado de todos los elementos (requiere el arreglo 16). Si no, quitar el campo.

### 18. Los SamplerSpec erróneos fallan en silencio
- **Dónde:**
  - `Serialization/SamplerSpec.cs:82-84`: un tipo desconocido pasa a `Constant(0)`.
  - `SamplerSpec.cs:90-97`: `D`/`I`/`B` devuelven valores por defecto ante parámetros erróneos; por ejemplo, `"Exponential~abc"` da tasa 0,2.
  - `SamplerSpec.cs:21`: un `null` provoca una NullReferenceException.
  - `ElementBuildHelpers.cs:123-126` registra el error con `Console.WriteLine`, que no se ve en Unity, y devuelve `Constant(5)`.
- **Arreglo:** lanzar `FormatException` con un mensaje claro, o devolver un fallo, ante tipos desconocidos o parámetros que falten o no se puedan parsear.

### 19. `batchMode` del Combiner no tiene efecto
- **Dónde:** `SimElements/Combiner.cs:25/57` lo guarda, pero ningún código de `SimuLean.Net` lo lee; solo `UnityCombiner.cs:365`, para la parte visual.
- **Arreglo:** implementarlo (adjuntar los componentes como subítems del ítem principal en `CheckRequirements`) o eliminarlo de la configuración y de la UI.

### 20. El progreso visual se desplaza mal tras una pausa
- **Dónde:**
  - `Multiserver.cs:225-230` (`OnResumed`) suma `LastPauseDuration` a todos los `loadTime`, también a los de trabajos que empezaron durante la pausa.
  - Combiner y PickingStation (`theProcess`) no se desplazan nunca.
- **Arreglo:** desplazar `now − max(loadTime, pauseStart)` y sobrecargar `OnResumed` en Combiner y PickingStation. Solo afecta a la visualización.

### 21. SETUP está definido pero no se usa
- **Dónde:** `SimElements/ElementState.cs:76`.
- **Arreglo:** implementar el setup (por ejemplo, un tiempo de cambio cuando cambia el tipo de ítem, programado con `ScheduleWork` para que las paradas lo pausen) o documentarlo como reservado.

---

## Ya corregido en PyFlow (referencia para la paridad)

PyFlow resuelve estos casos así:
- 1: semilla explícita por modelo y flujos por clave.
- 3 y 4: `can_accept(item, origin)` incluye la estrategia de entrada.
- 5: los ítems se retiran del hueco pendiente antes de enviarlos.
- 6: cada modo de ParameterizedRouting tiene su instancia cacheada.
- 7: `initialize()` limpia todo.
- 10: `StopRequest` es inmutable.
- 11: al reanudar se repite el aviso mientras haya ítems.
- 12: cancelar trabajo refresca el estado.
- 13: el modo es opcional y cae al del generador.
- 16 y 17: proporciones desde el último reset y `run(until, warmup=)`.
- 18: los errores de SamplerSpec lanzan `E_INVALID_DIST`.
- 19: `batch_mode` implementado.
- 21: setup por cambio de tipo.

Los tests de PyFlow equivalentes están en `tests/unit/test_routing.py`, `test_states_stops.py`, `test_downtime.py` y `test_sampling.py`.
