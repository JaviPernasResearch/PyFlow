"""Resource pools and resource requirements in a model specification."""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from ..query import QueryError, check_query
from ..resources import DEFAULT_REQUEST_ORDER, DEFAULT_UNIT_ORDER, ResourcePool, ResourceRequirement
from .bindings import Binding

ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"


def _query(value: Optional[str]) -> Optional[str]:
    try:
        return check_query(value)
    except QueryError as exc:
        raise ValueError(str(exc)) from None


QueryText = Annotated[str, AfterValidator(_query)]
UNIT_FIELDS = ("name, index, skills ('weld' in skills), skills_count, busy_time, utilization, idle_since, "
               "idle_time, kind and the unit attributes")


class UnitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    skills: List[str] = Field(default_factory=list, description="What this unit can do (e.g. 'weld')")
    attributes: Dict[str, Union[bool, int, float, str]] = Field(
        default_factory=dict, description="Free values usable in queries, e.g. {\"level\": 3, \"zone\": \"A\"}")


class ResourcePoolSpec(BaseModel):
    """Shared units (operators, robots, tools, fixtures...) that elements need while they work.
    Give ``capacity`` for identical anonymous units, or ``units`` with names and skills."""
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"id": "welders", "kind": "operator", "capacity": 2},
        {"id": "robots", "kind": "robot", "units": [{"name": "R1", "skills": ["weld", "paint"]},
                                                    {"name": "R2", "skills": ["paint"]}]}]})

    id: str = Field(min_length=1, pattern=ID_PATTERN, description="Identifier used by elements' 'resources'")
    name: Optional[str] = Field(default=None, description="Display name (default: the id)")
    kind: str = Field(default="resource", description="Free label for reports: operator, robot, tool...")
    capacity: Optional[int] = Field(default=None, ge=1, description="Number of identical units")
    units: Optional[List[UnitSpec]] = Field(default=None, min_length=1, description="Named units with skills")
    unit_order: QueryText = Field(default=DEFAULT_UNIT_ORDER, description=(
        "ORDER BY used to choose among the idle units, over " + UNIT_FIELDS + ". Examples: 'utilization ASC' "
        "(balance the work), 'idle_time DESC' (longest idle), 'level DESC'"))

    @model_validator(mode="after")
    def _check(self):
        if self.name is None:
            self.name = self.id
        if (self.capacity is None) == (self.units is None):
            raise ValueError("a resource pool needs exactly one of 'capacity' or 'units'")
        if self.units is not None and len({u.name for u in self.units}) != len(self.units):
            raise ValueError("unit names must be unique within a pool")
        return self

    def count(self, skill: Optional[str] = None) -> int:
        if self.units is None:
            return self.capacity if skill is None else 0
        return sum(1 for u in self.units if skill is None or skill in u.skills)

    def build(self, model: Any) -> ResourcePool:
        units = [u.model_dump() for u in self.units] if self.units is not None else None
        return ResourcePool(self.name, model, self.capacity, units=units, kind=self.kind, unit_order=self.unit_order)


class ResourceUseSpec(BaseModel):
    """``quantity`` units of pool ``pool`` (with ``skill``) during ``during``."""
    model_config = ConfigDict(extra="forbid")
    pool: str = Field(pattern=ID_PATTERN, description="Resource pool id")
    quantity: int = Field(default=1, ge=1)
    during: Literal["setup", "processing", "both"] = Field(
        default="both", description="both: from the start of the setup to the end of the processing")
    skill: Optional[str] = Field(default=None, description="Only units with this skill")
    where: Optional[QueryText] = Field(default=None, description=(
        "Filter over " + UNIT_FIELDS + ", plus item and element of the request. Example: "
        "'level >= item.complexity'"))


ResourceUse = Union[str, ResourceUseSpec]
RESOURCES_DESCRIPTION = ("Resources needed while working: a pool id ('welders' = one unit during the whole "
                         "service) or {pool, quantity, during: setup|processing|both, skill}. All of a phase's "
                         "resources are granted together; waiting requests are served by item priority, then "
                         "in arrival order.")
RELEASE_DESCRIPTION = ("on_exit (default): units are kept until the item has left the element (also while it is "
                       "blocked); on_finish: they are freed when the processing ends")


def as_use(value: ResourceUse) -> ResourceUseSpec:
    return value if isinstance(value, ResourceUseSpec) else ResourceUseSpec(pool=value)


def build_requirements(uses: List[ResourceUse], pools: Dict[str, ResourcePool]) -> List[ResourceRequirement]:
    result = []
    for use in map(as_use, uses):
        if use.pool not in pools:
            raise KeyError(use.pool)
        result.append(ResourceRequirement(pools[use.pool], use.quantity, during=use.during, skill=use.skill,
                                          where=use.where))
    return result


class ResourceRulesSpec(BaseModel):
    """How waiting resource requests are served (model-wide)."""
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"request_order": "priority DESC, item.due_date ASC", "discipline": "first_fit"},
        {"request_order": "kind == 'repair' DESC, age DESC", "discipline": "strict"}]})

    request_order: QueryText = Field(default=DEFAULT_REQUEST_ORDER, description=(
        "ORDER BY over the waiting requests: priority (item priority or repair priority), time, age, seq, "
        "quantity, kind ('work' | 'repair'), element (name), item (item.due_date, item.type...). Ties keep "
        "the request order"))
    discipline: Literal["first_fit", "strict"] = Field(default="first_fit", description=(
        "first_fit: grant, in that order, every request that can be fully served; strict: stop at the first "
        "one that cannot (nobody overtakes)"))

    def apply(self, model: Any) -> None:
        model.resources.configure(request_order=self.request_order, discipline=self.discipline)

    @property
    def is_default(self) -> bool:
        return self.request_order == DEFAULT_REQUEST_ORDER and self.discipline == "first_fit"


# Engine classes behind each spec (checked by tests/unit/test_spec_sync.py)
RESOURCE_BINDINGS = {
    ResourcePoolSpec: Binding(ResourcePool, converted={"units": "UnitSpec -> {name, skills}"}),
    ResourceUseSpec: Binding(ResourceRequirement, converted={"pool": "pool id -> ResourcePool"}),
}

__all__ = ["ResourcePoolSpec", "ResourceRulesSpec", "UnitSpec", "ResourceUseSpec", "ResourceUse", "build_requirements", "as_use",
           "RESOURCE_BINDINGS", "RESOURCES_DESCRIPTION", "RELEASE_DESCRIPTION"]
