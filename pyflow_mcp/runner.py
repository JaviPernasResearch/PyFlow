"""Chunked simulation runner with a wall-clock budget.

advance_clock() is synchronous and potentially long-running, so each chunk is
dispatched to a thread via asyncio.to_thread() so the event loop stays responsive.
The wall-clock check happens BETWEEN chunks — a single chunk that runs long will
exceed the budget but will still complete before the timeout is detected.
"""

from __future__ import annotations

import asyncio
import time

from .session import SimulationSession, SessionState


async def run_chunked(
    session: SimulationSession,
    stop_time: float,
    chunk_count: int,
    max_wall_seconds: float,
    ctx=None,
) -> dict:
    """Advance the SimClock in *chunk_count* equal slices up to *stop_time*.

    Stops early when:
      - The wall-clock budget is exhausted (status="wall_clock_timeout")
      - The event calendar becomes empty (status="network_idle")
    Otherwise returns status="completed".

    Timeouts are structured return values, not exceptions.

    Args:
        session: A SimulationSession in READY state.
        stop_time: Simulation end time in model time units.
        chunk_count: Number of equal slices to divide stop_time into.
        max_wall_seconds: Maximum real-world seconds before aborting.
        ctx: Optional FastMCP Context; if provided, progress is reported each chunk.
    """
    session.require_state(SessionState.READY)

    chunk_size = stop_time / chunk_count
    sim_time = 0.0
    wall_start = time.monotonic()
    chunks_done = 0
    network_idle = False
    timed_out = False

    if ctx is not None:
        await ctx.report_progress(0, stop_time)

    for i in range(chunk_count):
        elapsed = time.monotonic() - wall_start
        if elapsed >= max_wall_seconds:
            timed_out = True
            break

        next_t = (i + 1) * chunk_size
        has_more = await asyncio.to_thread(session.clock.advance_clock, next_t)
        sim_time = next_t
        chunks_done += 1

        if ctx is not None:
            await ctx.report_progress(sim_time, stop_time)

        # Re-check wall clock AFTER the chunk: a slow chunk may have exceeded the
        # budget even though it looked fine before it started.  Wall-clock timeout
        # takes priority over network-idle so the caller gets the right signal.
        if time.monotonic() - wall_start >= max_wall_seconds:
            timed_out = True
            break

        if not has_more:
            network_idle = True
            break

    wall_elapsed = time.monotonic() - wall_start

    if timed_out:
        status = "wall_clock_timeout"
    elif network_idle:
        status = "network_idle"
    else:
        status = "completed"

    run_info = {
        "status": status,
        "sim_time_reached": sim_time,
        "stop_time_requested": stop_time,
        "wall_seconds_elapsed": round(wall_elapsed, 3),
        "wall_seconds_budget": max_wall_seconds,
        "chunks_completed": chunks_done,
        "chunks_total": chunk_count,
    }
    session.mark_completed(run_info)
    return run_info
