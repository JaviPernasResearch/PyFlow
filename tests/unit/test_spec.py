"""Model specification: registry, validation, building, round trip (deterministic unless noted)."""
import json
from typing import Literal

import pytest
from pydantic import Field, ValidationError

from PyFlow import InterArrivalSource, ItemsQueue, Model, MultiServer, Sink
from PyFlow.spec import (BUILTIN_ELEMENT_SPECS, ElementSpecBase, ModelBuilder, ModelSpec, SpecError, element_types,
                         register_element, unregister_element, validate_spec)


def line_spec(**overrides):
    """src -> q -> m -> snk with exponential times."""
    data = {
        "name": "Line", "seed": 5,
        "elements": [
            {"type": "InterArrivalSource", "id": "src", "interarrival": "ExponentialMean~2"},
            {"type": "ItemsQueue", "id": "q", "capacity": 20},
            {"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": "ExponentialMean~1.6"},
            {"type": "Sink", "id": "snk"},
        ],
        "connections": [{"origin": "src", "destinations": ["q"]}, {"origin": "q", "destinations": ["m"]},
                        {"origin": "m", "destinations": ["snk"]}],
    }
    data.update(overrides)
    return data


def jobs(*rows):
    """ScheduleSource jobs from (time, name, qty, labels) tuples."""
    return [{"time": t, "name": n, "qty": q, "labels": labels} for t, n, q, labels in rows]


def codes(issues, severity=None):
    return sorted(i.code for i in issues if severity is None or i.severity == severity)


# ------------------------------------------------------------------ registry
def test_builtin_types_are_registered():
    names = {"InterArrivalSource", "InterArrivalBufferingSource", "InfiniteSource", "ScheduleSource", "ItemsQueue",
             "MultiServer", "Combiner", "MultiAssembler", "Sink"}
    assert names == set(element_types()) >= {cls.model_fields["type"].annotation.__args__[0]
                                             for cls in BUILTIN_ELEMENT_SPECS}
    assert element_types()["Sink"].role == "sink"
    assert element_types()["ScheduleSource"].role == "source"
    assert element_types()["MultiAssembler"].main_input is False


def test_unknown_type_and_extra_fields_are_rejected():
    with pytest.raises(ValidationError, match="unknown element type 'Conveyor'.*Known: Combiner"):
        ModelSpec.from_dict({"elements": [{"type": "Conveyor", "id": "c"}]})
    with pytest.raises(ValidationError, match="capacty"):
        ModelSpec.from_dict({"elements": [{"type": "ItemsQueue", "id": "q", "capacty": 3}]})


def test_name_defaults_to_id():
    spec = ModelSpec.from_dict(line_spec())
    assert [e.name for e in spec.elements] == ["src", "q", "m", "snk"]


@pytest.fixture
def custom_type():
    class DelaySpec(ElementSpecBase):
        """Constant-delay single server (test type)."""
        type: Literal["Delay"]
        delay: float = Field(gt=0)

    @register_element(DelaySpec)
    def build(spec, ctx):
        return MultiServer(1, spec.delay, spec.name, ctx.model)

    yield DelaySpec
    unregister_element("Delay")


def test_custom_element_type(custom_type):
    spec = ModelSpec.from_dict({
        "elements": [{"type": "InfiniteSource", "id": "src"}, {"type": "Delay", "id": "d", "delay": 4},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "src", "destinations": ["d"]}, {"origin": "d", "destinations": ["snk"]}]})
    assert isinstance(spec.elements[1], custom_type)
    results = spec.build().run(until=40)
    assert results["elements"]["snk"]["input_count"] == 10
    schema = ModelSpec.json_schema()
    assert "DelaySpec" in schema["$defs"]
    assert ModelSpec.from_json(spec.to_json()) == spec


def test_duplicate_registration_needs_replace(custom_type):
    with pytest.raises(ValueError, match="already registered"):
        register_element(custom_type)(lambda spec, ctx: None)


# ------------------------------------------------------------------ samplers
@pytest.mark.parametrize("value", ["Exponential~0", "Foo~1", "Triangular~1~2", "PT1 +", "__import__('os')"])
def test_invalid_sampler_strings_fail_at_validation(value):
    with pytest.raises(ValidationError):
        ModelSpec.from_dict(line_spec(elements=[{"type": "MultiServer", "id": "m", "num_servers": 1,
                                                 "service_time": value}]))


@pytest.mark.parametrize("value", [3, 2.5, "Uniform~1~2", "PT1 * 60", {"type": "expon", "scale": 2},
                                   {"type": "label_expr", "expression": "item.get_label_value('PT1')"}])
def test_valid_sampler_forms(value):
    ModelSpec.from_dict(line_spec(elements=[{"type": "MultiServer", "id": "m", "num_servers": 1,
                                             "service_time": value}]))


# ------------------------------------------------------------------ building = same results as code
def test_spec_matches_hand_built_model():
    model = Model(seed=5)
    src = InterArrivalSource("src", model, "ExponentialMean~2")
    q = ItemsQueue(20, "q", model)
    m = MultiServer(1, "ExponentialMean~1.6", "m", model)
    snk = Sink("snk", model)
    src.connect([q])
    q.connect([m])
    m.connect([snk])
    model.initialize()
    model.run(5000)

    built = ModelSpec.from_dict(line_spec()).build()
    results = built.run(until=5000)
    for name, element in {"src": src, "q": q, "m": m, "snk": snk}.items():
        sc = element.get_stats_collector()
        assert results["elements"][name]["output_count"] == sc.get_var_output_value()
        assert results["elements"][name]["input_count"] == sc.get_var_input_value()
        assert results["elements"][name]["content_average"] == pytest.approx(sc.get_var_content_average(), abs=1e-12)


def test_seed_override_and_determinism():
    spec = ModelSpec.from_dict(line_spec())
    a = spec.build(seed=1).run(until=2000)
    b = spec.build(seed=1).run(until=2000)
    c = spec.build(seed=2).run(until=2000)
    assert a == b
    assert a["elements"]["snk"] != c["elements"]["snk"]
    built = spec.build(seed=1)
    assert built.run(until=2000) == built.run(until=2000)   # re-running a built model starts over


def test_run_defaults_and_results_are_json():
    spec = ModelSpec.from_dict(line_spec(run={"until": 1000, "warmup": 200}))
    results = spec.build().run()
    assert results["time"] == 1000 and results["warmup"] == 200
    assert results["elements"]["snk"]["staytime_min"] is None      # nothing ever leaves a sink
    json.dumps(results)
    with pytest.raises(ValueError, match="E_NO_HORIZON"):
        ModelSpec.from_dict(line_spec()).build().run()


# ------------------------------------------------------------------ element features through the spec
def test_combiner_ports_and_pull_mode():
    """Same scenario as test_combiner_matches_components_by_label_and_requirement."""
    spec = ModelSpec.from_dict({
        "seed": 1,
        "elements": [
            {"type": "ScheduleSource", "id": "plates", "jobs": jobs(
                (0, "Plate", 1, {"Previa_ID": "A", "nRefuerzos": 1}),
                (0, "Plate", 1, {"Previa_ID": "B", "nRefuerzos": 2}),
                (0, "Plate", 1, {"Previa_ID": "C", "nRefuerzos": 1}))},
            {"type": "ScheduleSource", "id": "parts", "jobs": jobs(
                (0, "Part", 1, {"Previa_ID": "A"}), (0, "Part", 2, {"Previa_ID": "B"}),
                (0, "Part", 1, {"Previa_ID": "C"}), (0, "Part", 1, {"Previa_ID": "Z"}))},
            {"type": "ItemsQueue", "id": "q_plates", "capacity": 100},
            {"type": "ItemsQueue", "id": "q_parts", "capacity": 100},
            {"type": "Combiner", "id": "welding", "requirements": [1], "service_time": 2, "batch_mode": True,
             "pull_mode": {"type": "SingleLabel", "label": "Previa_ID"}, "update_requirements": True,
             "update_labels": ["nRefuerzos"]},
            {"type": "Sink", "id": "snk", "keep_items": True},
        ],
        "connections": [
            {"origin": "plates", "destinations": ["q_plates"]}, {"origin": "parts", "destinations": ["q_parts"]},
            {"origin": "q_plates", "destinations": ["welding"]}, {"origin": "q_parts", "destinations": ["welding:0"]},
            {"origin": "welding", "destinations": ["snk"]}]})
    assert validate_spec(spec) == []
    built = spec.build()
    built.run(until=100)
    done = built["snk"].items
    assert [p.get_label_value("Previa_ID") for p in done] == ["A", "B", "C"]
    assert [len(p.get_sub_items()) for p in done] == [1, 2, 1]
    assert built.model.clock.last_event_time == 6


def test_multiassembler_through_ports():
    spec = ModelSpec.from_dict({
        "elements": [{"type": "InfiniteSource", "id": "a", "item_type": "A"},
                     {"type": "InfiniteSource", "id": "b", "item_type": "B"},
                     {"type": "MultiAssembler", "id": "asm", "num_servers": 1, "requirements": [1, 2],
                      "service_time": 5},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "a", "destinations": ["asm:0"]}, {"origin": "b", "destinations": ["asm:1"]},
                        {"origin": "asm", "destinations": ["snk"]}]})
    assert validate_spec(spec) == []
    assert spec.build().run(until=50)["elements"]["snk"]["input_count"] == 10


def test_label_routing_matches_numeric_labels():
    spec = ModelSpec.from_dict({
        "elements": [{"type": "ScheduleSource", "id": "src", "jobs": jobs(
                         (0, "J", 2, {"family": 1}), (0, "J", 3, {"family": 2}), (0, "J", 1, {"family": 9}))},
                     {"type": "Sink", "id": "s0"}, {"type": "Sink", "id": "s1"}, {"type": "Sink", "id": "s2"}],
        "connections": [{"origin": "src", "destinations": ["s0", "s1", "s2"],
                         "strategy": {"type": "LabelRouting", "label": "family", "mapping": {"1": 0, "2": 1},
                                      "default_index": 2}}]})
    counts = [spec.build().run(until=1)["elements"][s]["input_count"] for s in ("s0", "s1", "s2")]
    assert counts == [2, 3, 1]


def test_parameterized_routing_reads_model_parameters():
    data = {"parameters": {"route": 1},
            "elements": [{"type": "ScheduleSource", "id": "src", "jobs": jobs((0, "J", 4, {}))},
                         {"type": "Sink", "id": "s0"}, {"type": "Sink", "id": "s1"}],
            "connections": [{"origin": "src", "destinations": ["s0", "s1"],
                             "strategy": {"type": "Parameterized", "parameter": "route"}}]}
    built = ModelSpec.from_dict(data).build()
    assert built.run(until=1)["elements"]["s1"]["input_count"] == 4
    built.model.parameters["route"] = 0
    assert built.run(until=1)["elements"]["s0"]["input_count"] == 4


def test_origin_name_input_strategy_uses_ids():
    """q accepts only items from the element with id 'b' (whose name is 'Second')."""
    spec = ModelSpec.from_dict({
        "elements": [{"type": "ScheduleSource", "id": "a", "jobs": jobs((0, "A", 3, {}))},
                     {"type": "ScheduleSource", "id": "b", "name": "Second", "jobs": jobs((0, "B", 2, {}))},
                     {"type": "ItemsQueue", "id": "q", "capacity": 10,
                      "input_strategy": {"type": "Or", "strategies": [{"type": "OriginName", "origins": ["b"]}]}},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "a", "destinations": ["q"]}, {"origin": "b", "destinations": ["q"]},
                        {"origin": "q", "destinations": ["snk"]}]})
    results = spec.build().run(until=1)
    assert results["elements"]["snk"]["input_count"] == 2
    assert results["elements"]["snk"]["type_counts"] == {"B": 2}


def test_setup_times_by_type_and_change():
    """A A B A on one server, service 1: setup 2 for any change to B, 3 for B -> A."""
    spec = ModelSpec.from_dict({
        "elements": [{"type": "ScheduleSource", "id": "src", "jobs": jobs(
                         (0, "A", 2, {}), (0, "B", 1, {}), (0, "A", 1, {}))},
                     {"type": "ItemsQueue", "id": "q", "capacity": 10},
                     {"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 1,
                      "setup_time": {"by_type": {"B": 2}, "changes": [{"from_type": "B", "to_type": "A", "time": 3}]}},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "src", "destinations": ["q"]}, {"origin": "q", "destinations": ["m"]},
                        {"origin": "m", "destinations": ["snk"]}]})
    built = spec.build()
    results = built.run(until=100)
    assert built.model.clock.last_event_time == 1 + 1 + (2 + 1) + (3 + 1)
    assert results["elements"]["m"]["state_ratios"]["SETUP"] == pytest.approx(5 / 100)


def test_timetable_downtime_pauses_work():
    spec = ModelSpec.from_dict({
        "elements": [{"type": "ScheduleSource", "id": "src", "jobs": jobs((0, "J", 1, {}))},
                     {"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 10},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "src", "destinations": ["m"]}, {"origin": "m", "destinations": ["snk"]}],
        "downtimes": [{"type": "Timetable", "targets": ["m"], "intervals": [{"start": 5, "end": 10}]}]})
    built = spec.build()
    built.run(until=20)
    assert built["m"].time_in_state("SCHEDULED_DOWN") == 5
    assert built["snk"].get_stats_collector().get_var_input_value() == 1
    assert built.model.clock.last_event_time == 15


def test_shift_downtime_with_calendar():
    """Time unit = 1 h, t = 0 is Monday 00:00; the shift starts at 06:00."""
    spec = ModelSpec.from_dict({
        "calendar": {"start": "2026-01-05 00:00", "seconds_per_unit": 3600},
        "elements": [{"type": "ScheduleSource", "id": "src", "jobs": jobs((0, "J", 1, {}))},
                     {"type": "ItemsQueue", "id": "q", "capacity": 5},
                     {"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 1},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "src", "destinations": ["q"]}, {"origin": "q", "destinations": ["m"]},
                        {"origin": "m", "destinations": ["snk"]}],
        "downtimes": [{"type": "Shift", "targets": ["m"], "pattern": "Mon-Fri 06:00-14:00"}]})
    assert validate_spec(spec) == []
    built = spec.build()
    results = built.run(until=10)
    assert built["m"].time_in_state("OFF_SHIFT") == 6
    assert results["elements"]["q"]["staytime_average"] == 6
    assert results["elements"]["snk"]["input_count"] == 1


def test_mtbf_downtime_builds_one_generator_per_target():
    """Stochastic: only checks that failures happen."""
    data = line_spec(downtimes=[{"type": "MtbfMttr", "targets": ["q", "m"], "ttf": "ExponentialMean~100",
                                 "ttr": "ExponentialMean~10", "basis": "busy"}])
    built = ModelSpec.from_dict(data).build()
    assert len(built.generators) == 2
    results = built.run(until=5000)
    assert results["elements"]["m"]["state_ratios"]["BREAKDOWN"] > 0


def test_schedule_source_from_file():
    spec = ModelSpec.from_dict({
        "elements": [{"type": "ScheduleSource", "id": "src", "file": "Data/model_scheduleSource.csv"},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "src", "destinations": ["snk"]}]})
    assert spec.build().run(until=100)["elements"]["snk"]["input_count"] == 4
    with pytest.raises(ValidationError, match="exactly one of 'jobs' or 'file'"):
        ModelSpec.from_dict({"elements": [{"type": "ScheduleSource", "id": "src"}]})


# ------------------------------------------------------------------ validation
def test_validation_errors():
    spec = ModelSpec.from_dict({
        "parameters": {},
        "elements": [{"type": "InfiniteSource", "id": "src"}, {"type": "ItemsQueue", "id": "q", "capacity": 1},
                     {"type": "ItemsQueue", "id": "q", "capacity": 2},
                     {"type": "MultiAssembler", "id": "asm", "num_servers": 1, "requirements": [1],
                      "service_time": 1},
                     {"type": "Sink", "id": "snk",
                      "input_strategy": {"type": "OriginName", "origins": ["ghost"]}}],
        "connections": [{"origin": "src", "destinations": ["q", "nope", "src", "q:0", "asm", "asm:3"],
                         "strategy": {"type": "LabelRouting", "label": "x", "mapping": {"a": 7}}},
                        {"origin": "snk", "destinations": ["q"]},
                        {"origin": "q", "destinations": ["q"]}],
        "downtimes": [{"type": "Timetable", "targets": ["ghost"], "intervals": [{"start": 1, "duration": 1}]}]})
    issues = validate_spec(spec)
    assert codes(issues, "error") == sorted([
        "E_DUPLICATE_ID", "E_UNKNOWN_ELEMENT", "E_SELF_LOOP", "E_SOURCE_AS_DESTINATION", "E_INVALID_PORT",
        "E_PORT_REQUIRED", "E_INVALID_PORT", "E_ROUTING_INDEX", "E_SINK_AS_ORIGIN", "E_SELF_LOOP",
        "E_UNKNOWN_ELEMENT", "E_UNKNOWN_ELEMENT"])
    paths = {i.code: i.path for i in issues}
    assert paths["E_SINK_AS_ORIGIN"] == "connections[1].origin"
    with pytest.raises(SpecError) as info:
        spec.build()
    assert len(info.value.issues) == 12


def test_validation_warnings():
    spec = ModelSpec.from_dict({
        "elements": [{"type": "InfiniteSource", "id": "src"}, {"type": "ItemsQueue", "id": "q", "capacity": 1},
                     {"type": "ItemsQueue", "id": "idle", "name": "q", "capacity": 1},
                     {"type": "Combiner", "id": "c", "requirements": [1, 1], "service_time": 1},
                     {"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 1}],
        "connections": [{"origin": "src", "destinations": ["q"]},
                        {"origin": "src", "destinations": ["c:0"],
                         "strategy": {"type": "Parameterized", "parameter": "route"}},
                        {"origin": "q", "destinations": ["c"]}],
        "downtimes": [{"type": "Shift", "targets": ["m"], "pattern": "Mon 06:00-14:00"}]})
    issues = validate_spec(spec)
    assert codes(issues, "error") == []
    assert codes(issues) == sorted([
        "W_DUPLICATE_NAME", "W_SPLIT_CONNECTION", "W_MISSING_PARAMETER", "W_UNCONNECTED_OUTPUT",
        "W_UNCONNECTED_OUTPUT", "W_UNCONNECTED_OUTPUT", "W_NO_INPUT", "W_NO_INPUT", "W_UNFED_PORT",
        "W_DEFAULT_CALENDAR", "W_NO_SINK"])
    spec.build()   # warnings do not block
    with pytest.raises(SpecError):
        spec.build(strict_warnings=True)


def test_builder_errors_are_spec_errors():
    builder = ModelBuilder(seed=1)
    builder.add_element({"type": "InfiniteSource", "id": "src"})
    builder.add_element({"type": "Sink", "id": "snk"})
    for bad, code in [({"origin": "src", "destinations": ["x"]}, "E_UNKNOWN_ELEMENT"),
                      ({"origin": "snk", "destinations": ["src"]}, "E_SINK_AS_ORIGIN"),
                      ({"origin": "src", "destinations": ["snk:1"]}, "E_INVALID_PORT")]:
        with pytest.raises(SpecError) as info:
            builder.add_connection(bad)
        assert info.value.issues[0].code == code
    with pytest.raises(SpecError, match="E_DUPLICATE_ID"):
        builder.add_element({"type": "Sink", "id": "snk"})


# ------------------------------------------------------------------ round trip
FULL_SPEC = {
    "name": "Full", "seed": 11,
    "calendar": {"start": "2026-01-05 00:00", "seconds_per_unit": 60},
    "parameters": {"route": "round_robin", "flag": True},
    "elements": [
        {"type": "InterArrivalSource", "id": "src", "interarrival": {"type": "expon", "scale": 3},
         "item_type": "P", "labels": {"PT": 2.5, "family": "A"}},
        {"type": "InfiniteSource", "id": "parts", "item_type": "C"},
        {"type": "ItemsQueue", "id": "q1", "capacity": 10,
         "input_strategy": {"type": "And", "strategies": [{"type": "MaxQueue", "max_queue": 8},
                                                          {"type": "MultiLabel", "labels": {"family": ["A", "B"]}}]}},
        {"type": "ItemsQueue", "id": "q2", "capacity": 10},
        {"type": "MultiServer", "id": "m1", "num_servers": 2, "service_time": "PT * 2",
         "setup_time": "Uniform~0.5~1"},
        {"type": "Combiner", "id": "c", "requirements": [2], "service_time": "Triangular~1~2~4"},
        {"type": "Sink", "id": "snk"},
    ],
    "connections": [
        {"origin": "src", "destinations": ["q1", "q2"], "strategy": {"type": "Parameterized", "parameter": "route"}},
        {"origin": "q1", "destinations": ["m1"]}, {"origin": "q2", "destinations": ["m1"]},
        {"origin": "m1", "destinations": ["c"]}, {"origin": "parts", "destinations": ["c:0"]},
        {"origin": "c", "destinations": ["snk"], "strategy": "RoundRobin"}],
    "downtimes": [
        {"type": "MtbfMttr", "targets": ["m1"], "ttf": "ExponentialMean~500", "ttr": 20, "mode": "after_current"},
        {"type": "Timetable", "targets": ["c"], "intervals": [{"start": "2026-01-05 08:00", "duration": 30,
                                                                "code": "PM"}], "overlap": "merge"},
        {"type": "Shift", "targets": ["q1", "q2"], "pattern": "Mon-Fri 06:00-22:00", "holidays": ["2026-01-06"]}],
    "run": {"until": 5000, "warmup": 500},
}


def test_round_trip_json_and_file(tmp_path):
    spec = ModelSpec.from_dict(FULL_SPEC)
    assert validate_spec(spec) == []
    assert ModelSpec.from_json(spec.to_json()) == spec
    path = tmp_path / "full.json"
    spec.to_file(path)
    assert ModelSpec.from_file(path) == spec
    a = spec.build().run()
    b = ModelSpec.from_file(path).build().run()
    assert a == b


def test_builder_export_reproduces_the_model():
    spec = ModelSpec.from_dict(FULL_SPEC)
    exported = spec.build().builder.to_spec(run=spec.run, calendar=spec.calendar)
    assert exported == spec
    assert exported.build().run() == spec.build().run()


def test_json_schema_lists_every_type():
    schema = ModelSpec.json_schema()
    mapping = schema["properties"]["elements"]["items"]["discriminator"]["mapping"]
    assert set(mapping) == set(element_types())


def test_example_model_file_is_valid_and_runs():
    spec = ModelSpec.from_file("examples/models/assembly_line.json")
    assert validate_spec(spec) == []
    results = spec.build().run()
    assert results["time"] == 7200 and results["elements"]["shipping"]["input_count"] > 0
    assert results["elements"]["assembly"]["state_ratios"]["SCHEDULED_DOWN"] == pytest.approx(30 / (7200 - 1440))


# ------------------------------------------------------------------ resources
def shared_operator_spec(**overrides):
    data = {
        "resources": [{"id": "op", "kind": "operator", "capacity": 1},
                      {"id": "robots", "kind": "robot", "units": [{"name": "R1", "skills": ["weld", "paint"]},
                                                                  {"name": "R2", "skills": ["paint"]}]}],
        "elements": [{"type": "ScheduleSource", "id": "src", "jobs": jobs((0, "J", 2, {}))},
                     {"type": "MultiServer", "id": "a", "num_servers": 1, "service_time": 4, "resources": ["op"]},
                     {"type": "MultiServer", "id": "b", "num_servers": 1, "service_time": 4,
                      "resources": ["op", {"pool": "robots", "skill": "weld", "during": "processing"}],
                      "resource_release": "on_exit"},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "src", "destinations": ["a", "b"]}, {"origin": "a", "destinations": ["snk"]},
                        {"origin": "b", "destinations": ["snk"]}],
    }
    data.update(overrides)
    return data


def test_resources_through_the_spec():
    spec = ModelSpec.from_dict(shared_operator_spec())
    assert validate_spec(spec) == []
    built = spec.build()
    results = built.run(until=10)
    assert built.model.clock.last_event_time == 8          # a 0-4, b waits for the operator, 4-8
    assert results["elements"]["b"]["state_ratios"]["WAITING_FOR_RESOURCE"] == pytest.approx(0.4)
    op = results["resources"]["op"]
    assert (op["kind"], op["capacity"], op["utilization"], op["wait_average"]) == ("operator", 1, 0.8, 2)
    assert results["resources"]["robots"]["unit_utilization"] == {"R1": 0.4, "R2": 0.0}
    assert ModelSpec.from_json(spec.to_json()) == spec
    assert built.builder.to_spec() == spec.model_copy(update={"run": None})


def test_resource_validation():
    data = shared_operator_spec(resources=[{"id": "op", "capacity": 1}, {"id": "op", "capacity": 2},
                                           {"id": "snk", "capacity": 1}, {"id": "idle", "capacity": 1}])
    data["elements"][1]["resources"] = ["ghost", {"pool": "op", "quantity": 2}, {"pool": "op", "skill": "weld"}]
    data["elements"][2]["resources"] = ["op", {"pool": "op", "during": "setup"}]   # 2 units at once in setup
    issues = validate_spec(ModelSpec.from_dict(data))
    assert [(i.code, i.path) for i in issues] == [
        ("E_DUPLICATE_ID", "resources[1].id"),
        ("E_DUPLICATE_ID", "elements[3].id"),
        ("E_UNKNOWN_RESOURCE", "elements[1].resources[0]"),
        ("E_RESOURCE_INSUFFICIENT", "elements[1].resources[1]"),
        ("E_RESOURCE_INSUFFICIENT", "elements[1].resources[2]"),
        ("E_RESOURCE_INSUFFICIENT", "elements[2].resources"),
        ("W_UNUSED_RESOURCE", "resources[2]"),
        ("W_UNUSED_RESOURCE", "resources[3]"),
    ]
    with pytest.raises(ValidationError, match="exactly one of 'capacity' or 'units'"):
        ModelSpec.from_dict({"resources": [{"id": "x"}]})


def test_builder_requires_existing_pools():
    builder = ModelBuilder(seed=1)
    with pytest.raises(SpecError, match="E_UNKNOWN_RESOURCE"):
        builder.add_element({"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 1,
                             "resources": ["op"]})
    builder.add_resource({"id": "op", "units": [{"name": "Ana"}]})
    with pytest.raises(SpecError, match="E_RESOURCE_INSUFFICIENT"):
        builder.add_element({"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 1,
                             "resources": [{"pool": "op", "skill": "weld"}]})
    builder.add_element({"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 1, "resources": ["op"]})
    with pytest.raises(SpecError, match="E_DUPLICATE_ID"):
        builder.add_resource({"id": "m", "capacity": 1})


def test_resource_rules_through_the_spec():
    data = shared_operator_spec(resource_rules={"request_order": "element == 'b' DESC", "discipline": "strict"})
    data["resources"][0]["unit_order"] = "utilization ASC"
    data["resources"][1]["units"][0]["attributes"] = {"level": 3}
    data["elements"][2]["resources"] = ["op", {"pool": "robots", "skill": "weld", "where": "level >= 2"}]
    spec = ModelSpec.from_dict(data)
    assert validate_spec(spec) == []
    built = spec.build()
    assert (built.model.resources.request_order, built.model.resources.discipline) == ("element == 'b' DESC", "strict")
    assert built.resources["op"].unit_order == "utilization ASC"
    built.run(until=10)
    assert ModelSpec.from_json(spec.to_json()) == spec
    assert built.builder.to_spec() == spec.model_copy(update={"run": None})
    default = ModelSpec.from_dict(shared_operator_spec()).build().builder.to_spec()
    assert default.resource_rules is None


@pytest.mark.parametrize("patch", [
    {"resource_rules": {"request_order": "priority DESC,"}},
    {"resource_rules": {"discipline": "random"}},
    {"resources": [{"id": "op", "capacity": 1, "unit_order": "level >"}]},
])
def test_invalid_rules_are_rejected(patch):
    with pytest.raises(ValidationError):
        ModelSpec.from_dict(shared_operator_spec(**patch))
