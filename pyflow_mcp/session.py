"""SimulationSession — owns the model lifecycle and state machine.

States:
    BUILDING  → elements, connections and downtimes can be added.
    READY     → the model has been initialized; run_experiment can be called.
    COMPLETED → run has finished; only read operations (and a new run) are allowed.

Transitions:
    new_model / reset() / load_spec()  → BUILDING  (from any state)
    initialize()                       → READY     (from BUILDING)
    mark_completed() [by runner]       → COMPLETED (from READY)
    rerun() [by runner]                → READY     (from COMPLETED: same model, fresh run)

The model is built through :class:`PyFlow.spec.ModelBuilder`, so what an agent builds tool
call by tool call can be exported as a :class:`PyFlow.spec.ModelSpec` and loaded back.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from PyFlow import Model, SimClock
from PyFlow.spec import (BuiltModel, CalendarSpec, ConnectionSpec, ModelBuilder, ModelSpec, RunSpec, get_element_type,
                         validate_spec)

from .schemas import ElementSpec


class SessionState(str, Enum):
    BUILDING = "building"
    READY = "ready"
    COMPLETED = "completed"


class SessionStateError(Exception):
    """Raised when a tool is called in the wrong session state."""


class SimulationSession:
    """Holds the in-progress or completed simulation model.

    One session per MCP client (see ``server._session``). Call reset() / new_model to start
    a fresh simulation, or load_spec() to load a complete model in one step.
    """

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed
        self.name = "Model"
        self.calendar: Optional[CalendarSpec] = None
        self.run_spec: Optional[RunSpec] = None
        self.builder: ModelBuilder | None = None
        self.model: Model | None = None
        self.clock: SimClock | None = None
        self.state: SessionState = SessionState.BUILDING
        self.last_run_info: dict | None = None
        self.reset(seed)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self, seed: int | None = None, *, name: str = "Model", parameters: dict | None = None,
              calendar: CalendarSpec | None = None) -> None:
        """Full teardown: a brand-new Model (own clock, registry, item ids and RNG)."""
        self.seed = seed
        self.name = name
        self.calendar = calendar
        self.run_spec = None
        self.last_run_info = None
        self.builder = ModelBuilder(seed=seed, name=name, parameters=parameters,
                                    calendar=calendar.build() if calendar else None)
        self._attach(self.builder)

    def _attach(self, builder: ModelBuilder) -> None:
        self.builder = builder
        self.model = builder.model
        self.clock = self.model.clock
        self.state = SessionState.BUILDING

    def load_spec(self, spec: ModelSpec) -> BuiltModel:
        """Replace the current model with a complete specification (validated first)."""
        built = spec.build()  # raises SpecError (a ValueError) with every problem found
        self.seed, self.name, self.calendar, self.run_spec = spec.seed, spec.name, spec.calendar, spec.run
        self.last_run_info = None
        self._attach(built.builder)
        return built

    def export_spec(self) -> ModelSpec:
        return self.builder.to_spec(name=self.name, run=self.run_spec, calendar=self.calendar)

    def validate(self) -> list[dict]:
        return [issue.to_dict() for issue in validate_spec(self.export_spec())]

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
    # Views
    # ------------------------------------------------------------------

    @property
    def elements(self) -> dict[str, Any]:
        return self.builder.elements

    @property
    def element_specs(self) -> dict[str, dict]:
        return {eid: spec.model_dump(mode="json", exclude_none=True) for eid, spec in self.builder.specs.items()}

    @property
    def connections(self) -> list[ConnectionSpec]:
        return self.builder.connections

    # ------------------------------------------------------------------
    # Mutations (BUILDING only)
    # ------------------------------------------------------------------

    def add_resource(self, spec: Any) -> None:
        self.require_state(SessionState.BUILDING)
        self.builder.add_resource(spec)

    def add_element(self, spec: ElementSpec) -> None:
        self.require_state(SessionState.BUILDING)
        self.builder.add_element(spec)

    def add_connection(self, conn: ConnectionSpec) -> None:
        self.require_state(SessionState.BUILDING)
        self.builder.add_connection(conn)

    def add_downtime(self, spec: Any) -> None:
        self.require_state(SessionState.BUILDING)
        self.builder.add_downtime(spec)

    def set_parameters(self, parameters: dict) -> None:
        """Model parameters (Parameterized routing). Allowed in any state before a run."""
        self.require_state(SessionState.BUILDING, SessionState.READY, SessionState.COMPLETED)
        self.model.parameters.update(parameters)

    def initialize(self) -> None:
        """Freeze the wiring and start every element and downtime generator."""
        self.require_state(SessionState.BUILDING)
        if not self.elements:
            raise ValueError("Cannot initialize: model has no elements")
        roles = {get_element_type(spec.type).role for spec in self.builder.specs.values()}
        if "source" not in roles:
            raise ValueError("Model must contain at least one source element "
                             "(InterArrivalSource, InterArrivalBufferingSource, InfiniteSource or ScheduleSource)")
        if "sink" not in roles:
            raise ValueError("Model must contain at least one Sink")
        self.builder.finalize()
        self.model.initialize()
        self.state = SessionState.READY

    def rerun(self) -> None:
        """Back to READY for a fresh run of the same model (t = 0, same seed => same results)."""
        self.require_state(SessionState.READY, SessionState.COMPLETED)
        self.model.initialize()
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
            "seed": self.model.seed,
            "resources": [r.model_dump(mode="json", exclude_none=True) for r in self.builder.resource_specs.values()],
            "elements": list(self.element_specs.values()),
            "connections": [c.model_dump(mode="json") for c in self.connections],
            "downtimes": [d.model_dump(mode="json", exclude_none=True) for d in self.builder.downtimes],
            "parameters": dict(self.model.parameters),
            "last_run_info": self.last_run_info,
        }
