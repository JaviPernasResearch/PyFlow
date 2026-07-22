"""Canonical ground-truth model definitions + reference emitter (HARNESS-ONLY).

Single source of truth for the structural references that ``structural_score``
compares agent-built models against. Each ground-truth model is defined **once**
as MCP specs here; the emitter builds it via ``SimulationSession`` and writes
``references/<name>.json`` in the same ``describe_model()`` format the agent
produces — so a reference can never drift from its spec definition.

Because a structural reference only needs elements + connections (both present
before ``initialize()``), emitting does not run the simulation.

Regenerate every reference::

    python -m pyflow_mcp.reference_models            # all models
    python -m pyflow_mcp.reference_models model2     # just one

The models mirror the topologies in ``test_I3M.py`` (run_model1/2/3):
    model1 — 3 typed sources → shared 2-stage line, label_expr service times.
    model2 — 2 typed sources → parallel P1/P2 → shared bottleneck P3 (deterministic).
    model3 — model2's topology with stochastic service times (the main reference).
"""

from __future__ import annotations

import json
import os
from typing import Callable

from .schemas import (
    ConnectionSpec, ExponDist, InterArrivalSourceSpec, ItemsQueueSpec,
    LabelExprSpec, MultiServerSpec, NormDist, SinkSpec, TriangDist, UniformDist,
)
from .session import SimulationSession

REFERENCE_DIR = "references"


def _det(loc: float) -> UniformDist:
    """Deterministic 'distribution': uniform(loc, scale=0) always returns loc."""
    return UniformDist(type="uniform", loc=loc, scale=0)


def _pt(label: str) -> LabelExprSpec:
    """label_expr service time that reads a processing-time label off the item."""
    return LabelExprSpec(type="label_expr", expression=f"item.get_label_value('{label}')")


# ---------------------------------------------------------------------------
# Model 1 — three typed sources, shared serial line, label-driven times
# ---------------------------------------------------------------------------

def model1_specs():
    elements = [
        InterArrivalSourceSpec(type="InterArrivalSource", id="src1", name="Source1",
                               interarrival=_det(10), item_type="Type1",
                               labels={"PT1": "10", "PT2": "5"}),
        InterArrivalSourceSpec(type="InterArrivalSource", id="src2", name="Source2",
                               interarrival=_det(10), item_type="Type2",
                               labels={"PT1": "5", "PT2": "15"}),
        InterArrivalSourceSpec(type="InterArrivalSource", id="src3", name="Source3",
                               interarrival=_det(10), item_type="Type3",
                               labels={"PT1": "15", "PT2": "10"}),
        ItemsQueueSpec(type="ItemsQueue", id="buf1", name="Buffer1", capacity=10),
        ItemsQueueSpec(type="ItemsQueue", id="buf2", name="Buffer2", capacity=10),
        ItemsQueueSpec(type="ItemsQueue", id="buf3", name="Buffer3", capacity=10),
        MultiServerSpec(type="MultiServer", id="p1", name="Processor1", num_servers=1,
                        service_time=_pt("PT1")),
        MultiServerSpec(type="MultiServer", id="p2", name="Processor2", num_servers=1,
                        service_time=_pt("PT2")),
        SinkSpec(type="Sink", id="snk", name="Sink"),
    ]
    connections = [
        ConnectionSpec(origin="src1", destinations=["buf1"]),
        ConnectionSpec(origin="src2", destinations=["buf2"]),
        ConnectionSpec(origin="src3", destinations=["buf3"]),
        ConnectionSpec(origin="buf1", destinations=["p1"]),
        ConnectionSpec(origin="buf2", destinations=["p1"]),
        ConnectionSpec(origin="buf3", destinations=["p1"]),
        ConnectionSpec(origin="p1", destinations=["p2"]),
        ConnectionSpec(origin="p2", destinations=["snk"]),
    ]
    return elements, connections


# ---------------------------------------------------------------------------
# Model 2 — parallel P1/P2 converging at shared bottleneck P3 (deterministic)
# ---------------------------------------------------------------------------

def model2_specs():
    elements = [
        InterArrivalSourceSpec(type="InterArrivalSource", id="src1", name="Source1",
                               interarrival=_det(10), item_type="Type1"),
        InterArrivalSourceSpec(type="InterArrivalSource", id="src2", name="Source2",
                               interarrival=_det(10), item_type="Type2"),
        MultiServerSpec(type="MultiServer", id="p1", name="Processor1", num_servers=1,
                        service_time=_det(10)),
        MultiServerSpec(type="MultiServer", id="p2", name="Processor2", num_servers=1,
                        service_time=_det(5)),
        ItemsQueueSpec(type="ItemsQueue", id="buf2", name="Buffer2", capacity=10),
        MultiServerSpec(type="MultiServer", id="p3", name="Processor3", num_servers=1,
                        service_time=_det(9)),
        SinkSpec(type="Sink", id="snk", name="Sink"),
    ]
    connections = [
        ConnectionSpec(origin="src1", destinations=["p1"]),
        ConnectionSpec(origin="src2", destinations=["p2"]),
        ConnectionSpec(origin="p1", destinations=["p3"]),
        ConnectionSpec(origin="p2", destinations=["buf2"]),
        ConnectionSpec(origin="buf2", destinations=["p3"]),
        ConnectionSpec(origin="p3", destinations=["snk"]),
    ]
    return elements, connections


# ---------------------------------------------------------------------------
# Model 3 — model2 topology with stochastic service times (main reference)
# ---------------------------------------------------------------------------

def model3_specs():
    elements = [
        InterArrivalSourceSpec(type="InterArrivalSource", id="src1", name="Source1",
                               interarrival=ExponDist(type="expon", scale=8), item_type="Type1"),
        InterArrivalSourceSpec(type="InterArrivalSource", id="src2", name="Source2",
                               interarrival=ExponDist(type="expon", scale=8), item_type="Type2"),
        MultiServerSpec(type="MultiServer", id="p1", name="Processor1", num_servers=1,
                        service_time=NormDist(type="norm", loc=10, scale=2)),
        MultiServerSpec(type="MultiServer", id="p2", name="Processor2", num_servers=1,
                        service_time=ExponDist(type="expon", scale=5)),
        ItemsQueueSpec(type="ItemsQueue", id="buf2", name="Buffer2", capacity=10),
        MultiServerSpec(type="MultiServer", id="p3", name="Processor3", num_servers=1,
                        service_time=TriangDist(type="triang", c=0.5, loc=7, scale=4)),
        SinkSpec(type="Sink", id="snk", name="Sink"),
    ]
    connections = [
        ConnectionSpec(origin="src1", destinations=["p1"]),
        ConnectionSpec(origin="src2", destinations=["p2"]),
        ConnectionSpec(origin="p1", destinations=["p3"]),
        ConnectionSpec(origin="p2", destinations=["buf2"]),
        ConnectionSpec(origin="buf2", destinations=["p3"]),
        ConnectionSpec(origin="p3", destinations=["snk"]),
    ]
    return elements, connections


MODELS: dict[str, Callable] = {
    "model1": model1_specs,
    "model2": model2_specs,
    "model3": model3_specs,
}


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------

def build_session(elements, connections) -> SimulationSession:
    """Build (but do not initialize) a SimulationSession from spec lists.

    SimulationSession() resets the SimClock singleton and Item.ITEM_NUMBER.
    """
    session = SimulationSession()
    for spec in elements:
        session.add_element(spec)
    for conn in connections:
        session.add_connection(conn)
    return session


def reference_from_session(session: SimulationSession) -> dict:
    """Return the {elements, connections} structural reference for a session."""
    snap = session.snapshot()
    return {"elements": snap["elements"], "connections": snap["connections"]}


def emit_reference(name: str, *, out_dir: str = REFERENCE_DIR) -> str:
    """Build model *name* from its canonical specs and write references/<name>.json."""
    if name not in MODELS:
        raise KeyError(f"Unknown model {name!r}. Known: {sorted(MODELS)}")
    elements, connections = MODELS[name]()
    session = build_session(elements, connections)
    ref = reference_from_session(session)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ref, f, indent=2)
    return path


def emit_all(out_dir: str = REFERENCE_DIR) -> list[str]:
    return [emit_reference(name, out_dir=out_dir) for name in MODELS]


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Emit ground-truth reference JSONs.")
    parser.add_argument("models", nargs="*", choices=sorted(MODELS),
                        help="Model names to emit (default: all)")
    parser.add_argument("--out-dir", default=REFERENCE_DIR)
    args = parser.parse_args(argv)

    names = args.models or list(MODELS)
    for name in names:
        path = emit_reference(name, out_dir=args.out_dir)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
