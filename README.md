# PyFlow

PyFlow is an open-source, Python-based discrete-event simulation (DES) engine for manufacturing
systems. It follows the semantics of SimuLean (the Unity-embeddable simulator it is ported from)
and is designed to be driven by code, by model files and by AI agents through an MCP server.

> Status: alpha. The API may still change.

## Features

- **Engine**: one `Model` per run (no global state), event calendar with deterministic
  tie-breaks, seeded random streams per element (same seed ⇒ same results), warm-up.
- **Elements**: sources (inter-arrival, buffering, infinite, schedule), queues, parallel servers
  with setup times, combiner and assembler with component ports, sinks.
- **Routing**: output and input strategies (round robin, shortest queue, by label, by priority,
  by model parameter...).
- **States and downtime**: per-element states and time in each state; failures (MTBF/MTTR),
  timetables, weekly shifts with a calendar.
- **Shared resources**: operators, robots, tools... with skills, quantities, phases and
  configurable dispatching rules; repairs that need technicians.
- **FlexSim-style lists**: push items to a list (they stay where they are) and pull them with
  `WHERE ... ORDER BY ...` queries.
- **Models as data**: JSON (or YAML) model specifications with validation, and an MCP server
  exposing everything to agents.

## Installation

Python 3.11 or newer.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows; on Linux/macOS: .venv/bin/python
```

## Quick start

```python
from PyFlow import InterArrivalSource, ItemsQueue, Model, MultiServer, Sink

model = Model(seed=42)
source = InterArrivalSource("Source", model, "ExponentialMean~2")
queue = ItemsQueue(100, "Queue", model)
server = MultiServer(1, "Triangular~1~1.5~2", "Server", model)
sink = Sink("Sink", model)
source.connect([queue])
queue.connect([server])
server.connect([sink])

model.initialize()
model.run(10_000, warmup=1_000)
print(sink.get_stats_collector().get_var_input_value())
```

Or from a model file:

```bash
python examples/run_spec.py examples/models/assembly_line.json
```

MCP server for agents (Claude Code, Claude Desktop, Langflow...):

```bash
python -m pyflow_mcp.server --transport stdio
```

## Documentation and tests

- [DOCUMENTATION.md](DOCUMENTATION.md): library reference and model specification format.
- [docs/propuesta-paridad-simulean.md](docs/propuesta-paridad-simulean.md): roadmap towards parity with SimuLean.
- Tests: `python -m pytest`.

## Contributors

- [Javier Pernas-Álvarez](https://pdi.udc.es/en/File/Pdi/HF9NK)
- [Diego Crespo-Pereira](https://pdi.udc.es/en/File/Pdi/6W6MH)

## Contact

**Javier Pernas-Álvarez** — javier.pernas2@udc.es — Universidade da Coruña

## License

[GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/).
