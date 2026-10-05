"""SimulationSession — owns the model lifecycle and state machine.

States:
    BUILDING  → elements and connections can be added.
    READY     → clock has been initialized; run_experiment can be called.
    COMPLETED → run has finished; only read operations are allowed.

Transitions:
    new_model / reset()          → BUILDING  (from any state)
    initialize()                 → READY     (from BUILDING)
    mark_completed() [by runner] → COMPLETED (from READY)
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from PyFlow import Model, SimClock

from .factories import build_element, build_strategy
from .schemas import ConnectionSpec, ElementSpec


class SessionState(str, Enum):
    BUILDING = "building"
    READY = "ready"
    COMPLETED = "completed"


class SessionStateError(Exception):
    """Raised when a tool is called in the wrong session state."""


class SimulationSession:
    """Holds the in-progress or completed simulation model.

    Designed to be held for the lifetime of the MCP server (via lifespan).
    Call reset() / new_model tool to start a fresh simulation.
    """

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed
        self.model: Model | None = None
        self.state: SessionState = SessionState.BUILDING
        self.elements: dict[str, Any] = {}
        self.element_specs: dict[str, dict] = {}
        self.connections: list[ConnectionSpec] = []
        self.clock: SimClock | None = None
        self.last_run_info: dict | None = None
        self.reset()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Full teardown: a brand-new Model (own clock, registry, item ids and RNG)."""
        self.elements.clear()
        self.element_specs.clear()
        self.connections.clear()
        self.last_run_info = None

        self.model = Model(seed=self.seed)
        self.clock = self.model.clock

        self.state = SessionState.BUILDING

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def require_state(self, *allowed: SessionState) -> None:
        if self.state not in allowed:
            raise SessionStateError(
                f"Operation not allowed in state '{self.state.value}'. "
                f"Allowed: {[s.value for s in allowed]}. "
                "Call new_model to start over."
            )

    # ------------------------------------------------------------------
    # Mutations (BUILDING only)
    # ------------------------------------------------------------------

    def add_element(self, spec: ElementSpec) -> None:
        self.require_state(SessionState.BUILDING)
        if spec.id in self.elements:
            raise ValueError(f"Element id '{spec.id}' already exists in this model")
        element = build_element(spec, self.clock)
        self.elements[spec.id] = element
        self.element_specs[spec.id] = spec.model_dump()

    def add_connection(self, conn: ConnectionSpec) -> None:
        self.require_state(SessionState.BUILDING)
        if conn.origin not in self.elements:
            raise ValueError(f"Origin element '{conn.origin}' does not exist")
        for dst in conn.destinations:
            if dst not in self.elements:
                raise ValueError(f"Destination element '{dst}' does not exist")
        origin = self.elements[conn.origin]
        destinations = [self.elements[d] for d in conn.destinations]
        origin.connect(destinations, strategy=build_strategy(conn.strategy))
        self.connections.append(conn)

    def initialize(self) -> None:
        """Wire is frozen; start all elements via the SimClock."""
        self.require_state(SessionState.BUILDING)
        if not self.elements:
            raise ValueError("Cannot initialize: model has no elements")
        types = {spec["type"] for spec in self.element_specs.values()}
        source_types = {"InterArrivalSource", "ScheduleSource"}
        if not source_types.intersection(types):
            raise ValueError(
                "Model must contain at least one source element "
                "(InterArrivalSource or ScheduleSource)"
            )
        if "Sink" not in types:
            raise ValueError("Model must contain at least one Sink")
        self.clock.initialize()
        self.state = SessionState.READY

    # ------------------------------------------------------------------
    # Post-run transition (called by runner)
    # ------------------------------------------------------------------

    def mark_completed(self, run_info: dict) -> None:
        self.last_run_info = run_info
        self.state = SessionState.COMPLETED

    # ------------------------------------------------------------------
    # Read-only inspection (any state)
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """JSON-serialisable summary of the current model."""
        return {
            "state": self.state.value,
            "elements": list(self.element_specs.values()),
            "connections": [c.model_dump() for c in self.connections],
            "last_run_info": self.last_run_info,
        }
