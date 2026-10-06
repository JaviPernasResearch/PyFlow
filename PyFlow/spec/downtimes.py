"""Downtime generators in a model specification (one generator per target element)."""
from __future__ import annotations

from typing import Annotated, Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..downtime import DowntimeInterval, MtbfMttrDowntime, ShiftDowntime, TimetableDowntime
from ..simcalendar import WeeklyShiftPattern
from .bindings import Binding
from .resources import ResourceUse, build_requirements
from .samplers import SamplerSpec, build_sampler

TimeValue = Union[float, str]
TIME_DESCRIPTION = "Simulation time (number) or a date ('2026-01-05 06:00') converted with the model calendar"


class _DowntimeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: List[str] = Field(min_length=1, description="Element ids; one generator per target")
    state: Optional[str] = Field(default=None, description="State while stopped (default depends on the kind: "
                                 "BREAKDOWN, SCHEDULED_DOWN, OFF_SHIFT)")
    mode: Optional[Literal["immediate", "after_current"]] = Field(
        default=None, description="immediate: pause the work in progress; after_current: finish it first")
    block_input: bool = True
    block_output: Optional[bool] = Field(default=None, description="Default: true for immediate stops, "
                                         "false for after_current")

    def common_kwargs(self) -> dict:
        return {"state": self.state, "mode": self.mode, "block_input": self.block_input,
                "block_output": self.block_output}


class MtbfMttrSpec(_DowntimeBase):
    """Random failures: time to failure ``ttf`` and time to repair ``ttr``."""
    type: Literal["MtbfMttr"]
    ttf: SamplerSpec = Field(description="Time to failure (e.g. 'ExponentialMean~3600')")
    ttr: SamplerSpec = Field(description="Time to repair")
    first_failure: Optional[SamplerSpec] = None
    basis: Literal["calendar", "busy"] = Field(default="calendar", description="calendar: ttf counts from "
                                               "the end of the last repair; busy: only while processing")
    busy_states: Optional[List[str]] = Field(default=None, description="States that count as busy "
                                             "(default: PROCESSING)")
    code: str = "MTBF"
    repair_resources: List[ResourceUse] = Field(
        default_factory=list, description="Units needed to repair (pool ids or {pool, quantity, skill}), held for "
                                          "the whole repair. The element shows repair_wait_state until they are "
                                          "all granted; ttr starts then")
    repair_priority: float = Field(default=0, description="Priority of the repair request on the pools (higher "
                                                          "first; production requests use the item priority)")
    repair_wait_state: str = Field(default="WAITING_FOR_REPAIR", description="State while waiting for the "
                                                                            "repair resources")


class IntervalSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: TimeValue = Field(description=TIME_DESCRIPTION)
    duration: Optional[float] = Field(default=None, gt=0)
    end: Optional[TimeValue] = Field(default=None, description="Alternative to duration. " + TIME_DESCRIPTION)
    state: Optional[str] = None
    mode: Optional[Literal["immediate", "after_current"]] = None
    code: Optional[str] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _duration_or_end(self):
        if (self.duration is None) == (self.end is None):
            raise ValueError("an interval needs exactly one of 'duration' or 'end'")
        return self


class TimetableSpec(_DowntimeBase):
    """Stops at fixed times (planned maintenance, breaks...)."""
    type: Literal["Timetable"]
    intervals: List[IntervalSpec] = Field(min_length=1)
    overlap: Literal["allow", "serialize", "merge"] = "allow"


class ShiftSpec(_DowntimeBase):
    """Stops the element outside the working windows of a weekly shift pattern."""
    type: Literal["Shift"]
    pattern: str = Field(min_length=1, description="e.g. 'Mon-Fri 06:00-14:00,14:00-22:00; Sat 06:00-14:00'")
    holidays: List[str] = Field(default_factory=list, description="Dates without work ('2026-12-25')")

    @model_validator(mode="after")
    def _check_pattern(self):
        WeeklyShiftPattern.parse(self.pattern, self.holidays)  # raises ValueError if invalid
        return self


DowntimeSpec = Annotated[Union[MtbfMttrSpec, TimetableSpec, ShiftSpec], Field(discriminator="type")]


# Engine classes behind each spec (checked by tests/unit/test_spec_sync.py)
DOWNTIME_BINDINGS = {
    MtbfMttrSpec: Binding(MtbfMttrDowntime,
                          converted={"repair_resources": "pool ids -> ResourceRequirement objects"}),
    TimetableSpec: Binding(TimetableDowntime,
                           converted={"intervals": "IntervalSpec -> DowntimeInterval (dates -> sim time)"}),
    ShiftSpec: Binding(ShiftDowntime, field_map={"holidays": "pattern"}),
    IntervalSpec: Binding(DowntimeInterval, spec_only={"end": "alternative to duration"},
                          converted={"start": "dates -> simulation time"}),
}


def _intervals(spec: TimetableSpec, model: Any) -> List[DowntimeInterval]:
    result = []
    for iv in spec.intervals:
        start = model.calendar.parse_sim_time(iv.start)
        duration = iv.duration if iv.duration is not None else model.calendar.parse_sim_time(iv.end) - start
        if duration <= 0:
            raise ValueError(f"E_INVALID_INTERVAL: interval starting at {iv.start!r} ends before it starts")
        result.append(DowntimeInterval(start, duration, iv.state, iv.mode, iv.code, iv.reason))
    return result


def build_downtime(spec: Any, target: Any, model: Any, pools: Optional[dict] = None) -> Any:
    """One generator for ``target`` (registered in the model, started by ``initialize``).
    ``pools``: resource pools by id (repair resources)."""
    kwargs = spec.common_kwargs()
    if isinstance(spec, MtbfMttrSpec):
        extra = {"busy_states": spec.busy_states} if spec.busy_states else {}
        first = build_sampler(spec.first_failure) if spec.first_failure is not None else None
        return MtbfMttrDowntime(target, build_sampler(spec.ttf), build_sampler(spec.ttr), first_failure=first,
                                basis=spec.basis, code=spec.code,
                                repair_resources=build_requirements(spec.repair_resources, pools or {}),
                                repair_priority=spec.repair_priority, repair_wait_state=spec.repair_wait_state,
                                **extra, **kwargs)
    if isinstance(spec, TimetableSpec):
        return TimetableDowntime(target, _intervals(spec, model), overlap=spec.overlap, **kwargs)
    if isinstance(spec, ShiftSpec):
        return ShiftDowntime(target, WeeklyShiftPattern.parse(spec.pattern, spec.holidays), **kwargs)
    raise ValueError(f"unknown downtime spec: {spec!r}")


__all__ = ["DOWNTIME_BINDINGS", "DowntimeSpec", "MtbfMttrSpec", "TimetableSpec", "ShiftSpec", "IntervalSpec", "build_downtime"]
