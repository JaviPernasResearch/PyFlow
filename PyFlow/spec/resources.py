"""Resource pools and resource requirements in a model specification."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..resources import ResourcePool, ResourceRequirement
from .bindings import Binding

ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"


class UnitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    skills: List[str] = Field(default_factory=list, description="What this unit can do (e.g. 'weld')")


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
        return ResourcePool(self.name, model, self.capacity, units=units, kind=self.kind)


class ResourceUseSpec(BaseModel):
    """``quantity`` units of pool ``pool`` (with ``skill``) during ``during``."""
    model_config = ConfigDict(extra="forbid")
    pool: str = Field(pattern=ID_PATTERN, description="Resource pool id")
    quantity: int = Field(default=1, ge=1)
    during: Literal["setup", "processing", "both"] = Field(
        default="both", description="both: from the start of the setup to the end of the processing")
    skill: Optional[str] = Field(default=None, description="Only units with this skill")


ResourceUse = Union[str, ResourceUseSpec]
RESOURCES_DESCRIPTION = ("Resources needed while working: a pool id ('welders' = one unit during the whole "
                         "service) or {pool, quantity, during: setup|processing|both, skill}. All of a phase's "
                         "resources are granted together; waiting requests are served by item priority, then "
                         "in arrival order.")
RELEASE_DESCRIPTION = ("on_finish: units are freed when the processing ends, even if the item cannot leave; "
                       "on_exit: they are kept until the item has left the element")


def as_use(value: ResourceUse) -> ResourceUseSpec:
    return value if isinstance(value, ResourceUseSpec) else ResourceUseSpec(pool=value)


def build_requirements(uses: List[ResourceUse], pools: Dict[str, ResourcePool]) -> List[ResourceRequirement]:
    result = []
    for use in map(as_use, uses):
        if use.pool not in pools:
            raise KeyError(use.pool)
        result.append(ResourceRequirement(pools[use.pool], use.quantity, during=use.during, skill=use.skill))
    return result


# Engine classes behind each spec (checked by tests/unit/test_spec_sync.py)
RESOURCE_BINDINGS = {
    ResourcePoolSpec: Binding(ResourcePool, converted={"units": "UnitSpec -> {name, skills}"}),
    ResourceUseSpec: Binding(ResourceRequirement, converted={"pool": "pool id -> ResourcePool"}),
}

__all__ = ["ResourcePoolSpec", "UnitSpec", "ResourceUseSpec", "ResourceUse", "build_requirements", "as_use",
           "RESOURCE_BINDINGS", "RESOURCES_DESCRIPTION", "RELEASE_DESCRIPTION"]
