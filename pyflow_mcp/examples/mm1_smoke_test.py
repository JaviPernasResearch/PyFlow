"""Standalone M/M/1 smoke test — no MCP, exercises SimulationSession directly.

Run:
    python -m pyflow_mcp.examples.mm1_smoke_test

Expected: ~500 items through the Sink for stop_time=1000 with λ=0.5 (scale=2).
Should complete in well under 5 seconds.
"""

from __future__ import annotations

import asyncio
import sys
import os

# Make sure the repo root is on the path when run directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pyflow_mcp.schemas import (
    ConnectionSpec,
    ExponDist,
    InterArrivalSourceSpec,
    ItemsQueueSpec,
    MultiServerSpec,
    SinkSpec,
)
from pyflow_mcp.session import SimulationSession
from pyflow_mcp.runner import run_chunked
from pyflow_mcp.inspection import all_stats


def build_mm1(session: SimulationSession, arrival_scale: float = 2.0, service_scale: float = 1.0) -> None:
    """Add a classic M/M/1 model to *session* (λ=1/arrival_scale, μ=1/service_scale)."""
    session.add_element(InterArrivalSourceSpec(
        type="InterArrivalSource", id="src", name="Source",
        interarrival=ExponDist(type="expon", scale=arrival_scale),
    ))
    session.add_element(ItemsQueueSpec(
        type="ItemsQueue", id="q", name="Queue", capacity=100_000,
    ))
    session.add_element(MultiServerSpec(
        type="MultiServer", id="srv", name="Server", num_servers=1,
        service_time=ExponDist(type="expon", scale=service_scale),
    ))
    session.add_element(SinkSpec(type="Sink", id="snk", name="Sink"))

    session.add_connection(ConnectionSpec(origin="src", destinations=["q"]))
    session.add_connection(ConnectionSpec(origin="q",   destinations=["srv"]))
    session.add_connection(ConnectionSpec(origin="srv", destinations=["snk"]))


async def main() -> None:
    stop_time = 1_000.0
    # M/M/1: λ=0.5, μ=1.0, ρ=0.5 → ~500 items expected at Sink
    session = SimulationSession()
    build_mm1(session, arrival_scale=2.0, service_scale=1.0)
    session.initialize()

    print(f"Running M/M/1 simulation for {stop_time} time units ...")
    run_info = await run_chunked(
        session, stop_time=stop_time, chunk_count=10,
        max_wall_seconds=30.0,
    )

    print(f"\nRun result: {run_info['status']}")
    print(f"  Sim time reached : {run_info['sim_time_reached']:.1f} / {stop_time}")
    print(f"  Wall time elapsed: {run_info['wall_seconds_elapsed']:.3f}s")
    print()

    stats = all_stats(session.elements, session.element_specs)
    col = 20
    header = f"{'Element':<{col}} {'Type':<20} {'Input':>7} {'Output':>7} {'AvgWait':>9} {'AvgContent':>11}"
    print(header)
    print("-" * len(header))
    for s in stats:
        print(
            f"{s['name']:<{col}} {s['type']:<20} "
            f"{s['input_count']:>7.0f} {s['output_count']:>7.0f} "
            f"{s['staytime_average']:>9.3f} {s['content_average']:>11.4f}"
        )

    sink_input = next(s["input_count"] for s in stats if s["id"] == "snk")
    expected = 0.5 * stop_time  # λ × T
    ratio = sink_input / expected if expected else 0
    print(f"\nSink received {sink_input:.0f} items  (expected ~{expected:.0f}, ratio={ratio:.2f})")

    if 0.80 <= ratio <= 1.20:
        print("PASS — throughput within ±20% of Little's Law expectation.")
    else:
        print("WARNING — throughput outside ±20% band; check model or run longer.")


if __name__ == "__main__":
    asyncio.run(main())
