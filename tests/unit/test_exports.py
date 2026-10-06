"""Every statistics export includes the resources used (pools, units), lists and repairs."""
import json

import pytest

from PyFlow import InfiniteSource, Model, MtbfMttrDowntime, MultiServer, ResourcePool, Sink
from PyFlow.executers import TaskExecuter, TaskSequence, Utilize
from PyFlow.lists import ModelList
from PyFlow.reporting import model_summary
from PyFlow.spec import ModelSpec

SPEC = {
    "seed": 3,
    "resources": [{"id": "ops", "kind": "operator", "capacity": 2},
                  {"id": "techs", "kind": "technician", "units": [{"name": "T1", "skills": ["electric"]}]}],
    "lists": [{"id": "jobs"}],
    "elements": [{"type": "InterArrivalSource", "id": "src", "interarrival": "ExponentialMean~2"},
                 {"type": "ItemsQueue", "id": "q", "capacity": 50},
                 {"type": "MultiServer", "id": "m", "num_servers": 2, "service_time": 3, "resources": ["ops"]},
                 {"type": "Sink", "id": "snk"}],
    "connections": [{"origin": "src", "destinations": ["q"]}, {"origin": "q", "destinations": ["jobs"]},
                    {"origin": "jobs", "destinations": ["m"]}, {"origin": "m", "destinations": ["snk"]}],
    "downtimes": [{"type": "MtbfMttr", "targets": ["m"], "ttf": 40, "ttr": 5,
                   "repair_resources": [{"pool": "techs", "skill": "electric"}]}],
    "run": {"until": 200, "warmup": 20},
}


def check_resources(resources, *, keyed_by="id"):
    pools = resources if isinstance(resources, dict) else {r[keyed_by]: r for r in resources}
    assert set(pools) == {"ops", "techs"}
    ops = pools["ops"]
    assert ops["grants"] > 0 and 0 < ops["utilization"] <= 1 and ops["kind"] == "operator"
    assert set(ops["units"]) == {"ops.1", "ops.2"}
    unit = ops["units"]["ops.1"]
    assert {"state", "state_ratios", "utilization", "sequences_completed"} <= set(unit)
    assert unit["state_ratios"].get("WORKING", 0) > 0
    assert pools["techs"]["units"]["T1"]["sequences_completed"] > 0


def check_downtimes(downtimes):
    (d,) = downtimes
    assert d["target"] == "m" and d["stop_count"] > 0 and d["repairs"] > 0
    assert d["repair_resources"] == ["techs"] and d["repair_wait_average"] is not None


def test_built_model_results():
    results = ModelSpec.from_dict(SPEC).build().run()
    check_resources(results["resources"])
    check_downtimes(results["downtimes"])
    assert results["lists"]["jobs"]["pulls"] > 0
    json.dumps(results)


def test_model_summary_of_a_model_built_by_code():
    model = Model(seed=1)
    ops = ResourcePool("ops", model, capacity=2, kind="operator")
    techs = ResourcePool("techs", model, units=[{"name": "T1", "skills": ["electric"]}], kind="technician")
    src, m, sink = InfiniteSource("src", model), MultiServer(2, 3, "m", model, resources=[ops]), Sink("snk", model)
    src.connect([m])
    m.connect([sink])
    MtbfMttrDowntime(m, 40, 5, repair_resources=[techs])
    loose = TaskExecuter("forklift", model)
    tasks = ModelList("tasks", model)
    loose.serve(tasks)
    model.initialize()
    tasks.push(TaskSequence([Utilize(4)]))
    model.run(200, warmup=20)
    summary = model_summary(model)
    assert set(summary["elements"]) == {"src", "m", "snk"}                 # units are reported in their pool
    check_resources(summary["resources"])
    check_downtimes(summary["downtimes"])
    assert summary["executers"]["forklift"]["sequences_completed"] == 0   # done before the warm-up
    assert set(summary["lists"]) == {"tasks"}                              # the pools' own lists are internal
    assert summary["resources"]["ops"]["idle_units_average"] is not None
    json.dumps(summary)


def test_mcp_exports():
    pytest.importorskip("mcp")
    from tests.test_mcp_tools import run_session

    async def script(call):
        await call("load_model_spec", {"spec": SPEC})
        await call("initialize_model")
        run = await call("run_experiment", {"stop_time": 200, "warmup": 20})
        stats = await call("get_stats")
        return run, stats

    run, stats = run_session(script)
    for response in (run, stats):
        check_resources(response["resources"])
        check_downtimes(response["downtimes"])
        assert response["lists"][0]["id"] == "jobs"


def test_standard_line_summary_includes_resources():
    from PyFlow.standard_lines import Stage, serial_line
    line = serial_line(arrival="Exponential~1", stages=[Stage(0.8)], seed=1)
    summary = line.run(100)
    assert summary["resources"] == {} and summary["downtimes"] == []
    pool = ResourcePool("ops", line.model, capacity=1)
    MultiServer(1, 1, "extra", line.model, resources=[pool])
    assert "ops" in line.run(100)["resources"]
