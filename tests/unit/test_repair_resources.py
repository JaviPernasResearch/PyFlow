"""Breakdowns whose repair needs shared resources (technicians, operators...): exact cases."""
import pytest

from PyFlow import InfiniteSource, Model, MtbfMttrDowntime, MultiServer, ResourcePool, ResourceRequirement, Sink
from PyFlow.spec import ModelSpec, SpecError, validate_spec
from PyFlow.states import ElementState
from tests.harness import Collector, Feeder, at

BREAKDOWN, WAIT_REPAIR = ElementState.BREAKDOWN, ElementState.WAITING_FOR_REPAIR


def machine(model, name, service=1, **server_kw):
    src = InfiniteSource(f"Src_{name}", model)
    m = MultiServer(1, service, name, model, **server_kw)
    sink = Sink(f"Sink_{name}", model)
    src.connect([m])
    m.connect([sink])
    return m


def test_one_technician_repairs_two_machines_in_turn(model):
    tech = ResourcePool("Tech", model, capacity=1, kind="technician")
    m1, m2 = machine(model, "M1"), machine(model, "M2")
    g1 = MtbfMttrDowntime(m1, 100, 5, first_failure=10, repair_resources=[tech])
    g2 = MtbfMttrDowntime(m2, 100, 5, first_failure=10, repair_resources=[tech])
    model.initialize()
    model.run(30)
    # both fail at 10; M1 repaired 10-15, M2 waits 10-15 and is repaired 15-20
    assert (m1.time_in_state(WAIT_REPAIR), m1.time_in_state(BREAKDOWN)) == (0, 5)
    assert (m2.time_in_state(WAIT_REPAIR), m2.time_in_state(BREAKDOWN)) == (5, 5)
    assert (g1.repairs, g1.repair_wait_total, g2.repair_wait_total, g2.repair_wait_max) == (1, 0, 5, 5)
    assert g2.total_downtime == 10 and g2.stop_count == 1           # one stop: waiting + repair
    assert tech.busy.average(30) * 30 == pytest.approx(10)
    assert [(t, s) for t, s in m2.state_log if 10 <= t <= 20][:3] == [
        (10, WAIT_REPAIR), (15, BREAKDOWN), (20, ElementState.PROCESSING)]


def test_next_failure_counts_from_the_end_of_the_repair(model):
    tech = ResourcePool("Tech", model, capacity=1)
    busy = machine(model, "Other", service=50, resources=[tech])     # holds the technician 0-50
    m = machine(model, "M")
    MtbfMttrDowntime(m, 20, 5, first_failure=10, repair_resources=[tech])
    model.initialize()
    model.run(100)
    # fails at 10, technician free at 50: repair 50-55, next failure 55 + 20 = 75; meanwhile
    # Other got the technician back at 55 (until 105), so the second repair waits past 100
    log = [(t, s) for t, s in m.state_log if s in (WAIT_REPAIR, BREAKDOWN)]
    assert log == [(10, WAIT_REPAIR), (50, BREAKDOWN), (75, WAIT_REPAIR)]
    assert busy.time_in_state(ElementState.PROCESSING) == 95
    assert busy.time_in_state(ElementState.WAITING_FOR_RESOURCE) == 5


@pytest.mark.parametrize("priority, repair_start, q_done", [(10, 4, 11), (0, 8, 8)])
def test_repair_priority_against_production(model, priority, repair_start, q_done):
    """Operator busy on P until 4. Q (since t=1) and the repair of M (since t=2) wait for it."""
    op = ResourcePool("Op", model, capacity=1)
    p_feed = Feeder("FP", model, interval=1000, count=1)
    p = MultiServer(1, 4, "P", model, resources=[op])
    q_feed = Feeder("FQ", model, interval=1000, count=1, start=1)
    q = MultiServer(1, 4, "Q", model, resources=[op])
    out_p, out_q = Collector("OutP", model), Collector("OutQ", model)
    p_feed.connect([p])
    p.connect([out_p])
    q_feed.connect([q])
    q.connect([out_q])
    m = machine(model, "M")
    g = MtbfMttrDowntime(m, 1000, 3, first_failure=2, repair_resources=[op], repair_priority=priority)
    model.initialize()
    model.run(20)
    assert out_p.times == [4]
    assert g.repair_wait_total == repair_start - 2
    assert out_q.times == [q_done]
    assert m.time_in_state(BREAKDOWN) == 3


def test_several_repair_resources_are_granted_together(model):
    tech = ResourcePool("Tech", model, capacity=2)
    crane = ResourcePool("Crane", model, capacity=1, kind="crane")
    machine(model, "Lifter", service=30, resources=[crane])            # crane busy 0-30
    m = machine(model, "M")
    g = MtbfMttrDowntime(m, 1000, 4, first_failure=5,
                         repair_resources=[ResourceRequirement(tech, 2), crane])
    model.initialize()
    model.run(40)
    assert g.repair_wait_total == 25                                    # crane free at 30
    assert tech.busy.average(40) * 40 == pytest.approx(2 * 4)          # techs only held while repairing


def test_impossible_repair_requests_are_rejected(model):
    tech = ResourcePool("Tech", model, capacity=1)
    m = machine(model, "M")
    with pytest.raises(ValueError, match="E_RESOURCE_INSUFFICIENT"):
        MtbfMttrDowntime(m, 10, 1, repair_resources=[tech, ResourceRequirement(tech)])
    with pytest.raises(ValueError, match="another model"):
        MtbfMttrDowntime(m, 10, 1, repair_resources=[ResourcePool("T", Model(seed=3), capacity=1)])


def test_reinitialize_and_warmup_with_pending_repairs(model):
    tech = ResourcePool("Tech", model, capacity=1)
    m1, m2 = machine(model, "M1"), machine(model, "M2")
    g1 = MtbfMttrDowntime(m1, 100, 5, first_failure=10, repair_resources=[tech])
    g2 = MtbfMttrDowntime(m2, 100, 5, first_failure=10, repair_resources=[tech])
    model.initialize()
    model.run(12)                       # M2 waiting for the technician
    model.initialize()
    model.run(30, warmup=12)
    assert (g1.repairs, g2.repairs) == (0, 1)               # counters reset at the warm-up (12)
    # a repair's wait is measured whole (from the failure at 10) when it starts after the reset
    assert g2.repair_wait_total == 5 and m2.time_in_state(WAIT_REPAIR) == 3
    assert tech.busy.average(30) * 18 == pytest.approx(8)  # 12-15 (M1) + 15-20 (M2)


def test_restate_stop_keeps_the_same_stop(model):
    m = machine(model, "M")
    model.initialize()
    model.run(1.5)
    token = m.stop(WAIT_REPAIR)
    at(model, 3, lambda: m.restate_stop(token, BREAKDOWN))
    at(model, 4, lambda: m.resume(token))
    model.run(10)
    assert (m.time_in_state(WAIT_REPAIR), m.time_in_state(BREAKDOWN)) == (1.5, 1)
    assert m.stop_count == 1 and token.state == BREAKDOWN and not m.restate_stop(token, "X")


# ------------------------------------------------------------------ specification and MCP
def repair_spec(**downtime):
    return {
        "resources": [{"id": "techs", "kind": "technician", "units": [{"name": "T1", "skills": ["electric"]},
                                                                      {"name": "T2", "skills": ["mechanic"]}]}],
        "elements": [{"type": "InfiniteSource", "id": "src"},
                     {"type": "MultiServer", "id": "m1", "num_servers": 1, "service_time": 1},
                     {"type": "MultiServer", "id": "m2", "num_servers": 1, "service_time": 1},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "src", "destinations": ["m1", "m2"]}, {"origin": "m1", "destinations": ["snk"]},
                        {"origin": "m2", "destinations": ["snk"]}],
        "downtimes": [dict({"type": "MtbfMttr", "targets": ["m1", "m2"], "ttf": 100, "ttr": 5, "first_failure": 10,
                            "repair_resources": [{"pool": "techs", "skill": "electric"}]}, **downtime)],
    }


def test_repair_resources_through_the_spec():
    spec = ModelSpec.from_dict(repair_spec())
    assert validate_spec(spec) == []
    results = spec.build().run(until=30)
    # only T1 can do electric repairs: m1 10-15, m2 waits and is repaired 15-20
    assert results["elements"]["m2"]["state_ratios"]["WAITING_FOR_REPAIR"] == pytest.approx(5 / 30)
    assert results["resources"]["techs"]["unit_utilization"] == {"T1": pytest.approx(10 / 30), "T2": 0.0}
    assert ModelSpec.from_json(spec.to_json()) == spec


def test_repair_resources_validation():
    spec = ModelSpec.from_dict(repair_spec(repair_resources=["ghost", {"pool": "techs", "skill": "hydraulic"},
                                                             {"pool": "techs", "quantity": 2}, "techs"]))
    issues = [(i.code, i.path) for i in validate_spec(spec)]
    assert issues == [("E_UNKNOWN_RESOURCE", "downtimes[0].repair_resources[0]"),
                      ("E_RESOURCE_INSUFFICIENT", "downtimes[0].repair_resources[1]"),
                      ("E_RESOURCE_INSUFFICIENT", "downtimes[0].repair_resources")]
    with pytest.raises(SpecError):
        spec.build()


def test_add_downtimes_batch_with_repair_resources():
    pytest.importorskip("mcp")
    from tests.test_mcp_tools import run_session

    data = repair_spec()

    async def script(call):
        await call("create_resources_batch", {"resources": data["resources"]})
        await call("create_elements_batch", {"elements": data["elements"]})
        await call("connect_batch", {"connections": data["connections"]})
        bad = await call("add_downtimes_batch", {"downtimes": [dict(data["downtimes"][0],
                                                                    repair_resources=["ghost"])]})
        ok = await call("add_downtimes_batch", {"downtimes": data["downtimes"]})
        await call("initialize_model")
        return bad, ok, await call("run_experiment", {"stop_time": 30})

    bad, ok, run = run_session(script)
    assert bad["status"] == "partial_success" and "E_UNKNOWN_RESOURCE" in bad["failed_at"]["message"]
    assert ok["status"] == "success"
    m2 = next(s for s in run["stats"] if s["id"] == "m2")
    assert m2["state_ratios"]["WAITING_FOR_REPAIR"] == pytest.approx(5 / 30)
