"""Model lists in a model specification.

    "lists": [{"id": "jobs", "fields": {"slack": "due - now"}, "backorder_order": "priority DESC"}],
    "connections": [
        {"origin": "q1", "destinations": ["jobs"]},                                  # push to list
        {"origin": "jobs", "destinations": ["m1", "m2"], "query": "ORDER BY slack"}  # pull from list
    ]
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..lists import ModelList
from .bindings import Binding
from .resources import ID_PATTERN, QueryText


class ListSpec(BaseModel):
    """A FlexSim-style list. Elements send to it (their items stay with them, announced) and
    pull from it with a query; values wait as entries, pulls as back-orders."""
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"id": "jobs"},
        {"id": "orders", "fields": {"slack": "due - now", "urgent": "slack < 60"},
         "backorder_order": "priority DESC"}]})

    id: str = Field(min_length=1, pattern=ID_PATTERN)
    name: Optional[str] = Field(default=None, description="Display name (default: the id)")
    fields: Dict[str, QueryText] = Field(default_factory=dict, description=(
        "Calculated fields usable in queries: name -> expression over value, origin, age, push_time, now and "
        "the value's own fields (item type, labels...)"))
    backorder_order: Optional[QueryText] = Field(default=None, description=(
        "ORDER BY for waiting pulls: priority (of the pull), age, time, quantity, puller and the puller's fields. "
        "Default: oldest first"))
    unique: bool = Field(default=True, description="A value already in the list is not added twice")
    deliver: Literal["event", "immediate"] = Field(default="event", description=(
        "event: a waiting pull is served in a separate event at the same time (dt = 0); immediate: inside the push"))

    @model_validator(mode="after")
    def _check(self):
        if self.name is None:
            self.name = self.id
        reserved = {"value", "puller", "origin", "age", "push_time", "now"} & set(self.fields)
        if reserved:
            raise ValueError(f"reserved field name(s): {sorted(reserved)}")
        return self

    def build(self, model: Any) -> ModelList:
        return ModelList(self.name, model, fields=dict(self.fields), backorder_order=self.backorder_order,
                         unique=self.unique, deliver=self.deliver)


# Engine class behind the spec (checked by tests/unit/test_spec_sync.py)
LIST_BINDINGS = {ListSpec: Binding(ModelList, converted={"fields": "{} (no calculated fields) == None"})}

__all__ = ["ListSpec", "LIST_BINDINGS"]
