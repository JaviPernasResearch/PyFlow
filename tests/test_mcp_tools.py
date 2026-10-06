"""MCP tools through a real (in-memory) MCP client: spec loading/export, validation,
downtimes, parameters, warm-up, re-runs and per-client sessions."""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("mcp")
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from pyflow_mcp.server import mcp  # noqa: E402

LINE = {
    "name": "Line", "seed": 3,
    "elements": [
        {"type": "InterArrivalSource", "id": "src", "interarrival": "ExponentialMean~2"},
        {"type": "ItemsQueue", "id": "q", "capacity": 50},
        {"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 1.5},
        {"type": "Sink", "id": "snk"},
    ],
    "connections": [{"origin": "src", "destinations": ["q"]}, {"origin": "q", "destinations": ["m"]},
                    {"origin": "m", "destinations": ["snk"]}],
}


async def _call(client, name, args=None):
    result = await client.call_tool(name, args or {})
    text = result.content[0].text if result.content else ""
    assert not result.isError, text
    return json.loads(text)


def run_session(script):
    """Run ``script(call)`` with one connected client; ``call(tool, args)`` returns the JSON."""
    async def main():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            return await script(lambda name, args=None: _call(client, name, args))
    return asyncio.run(main())


def stats_by_id(response):
    return {s["id"]: s for s in response["stats"]}


def test_load_initialize_run_export():
    async def script(call):
        loaded = await call("load_model_spec", {"spec": LINE})
        assert loaded["created_ids"] == ["src", "q", "m", "snk"] and loaded["warnings"] == []
        init = await call("initialize_model")
        assert init["state"] == "ready" and init["seed"] == 3
        run = await call("run_experiment", {"stop_time": 1000})
        exported = await call("export_model_spec")
        return run, exported["spec"]

    run, exported = run_session(script)
    assert run["run_info"]["status"] == "completed" and run["run_info"]["sim_time_reached"] == 1000
    stats = stats_by_id(run)
    assert stats["snk"]["input_count"] > 0 and stats["m"]["state_ratios"]["PROCESSING"] > 0
    assert exported["elements"][2]["service_time"] == 1.5 and exported["seed"] == 3


def test_same_seed_same_results_and_rerun_in_completed_state():
    async def script(call):
        await call("load_model_spec", {"spec": LINE})
        await call("initialize_model")
        first = await call("run_experiment", {"stop_time": 500})
        again = await call("run_experiment", {"stop_time": 500})      # COMPLETED -> fresh run
        await call("load_model_spec", {"spec": LINE})
        await call("initialize_model")
        reloaded = await call("run_experiment", {"stop_time": 500})
        return first, again, reloaded

    first, again, reloaded = run_session(script)
    assert first["stats"] == again["stats"] == reloaded["stats"]


def test_warmup_resets_statistics():
    async def script(call):
        await call("load_model_spec", {"spec": dict(LINE, downtimes=[
            {"type": "Timetable", "targets": ["m"], "intervals": [{"start": 50, "duration": 100}]}])})
        await call("initialize_model")
        return await call("run_experiment", {"stop_time": 1000, "warmup": 100})

    run = run_session(script)
    assert run["run_info"]["warmup"] == 100
    # down during [50, 150]: only the 50 units after the warm-up count, over 900
    assert stats_by_id(run)["m"]["state_ratios"]["SCHEDULED_DOWN"] == pytest.approx(50 / 900)


def test_incremental_build_with_downtimes_and_parameters():
    async def script(call):
        await call("new_model", {"seed": 7, "parameters": {"route": 1}})
        await call("create_elements_batch", {"elements": [
            {"type": "InfiniteSource", "id": "src"},
            {"type": "MultiServer", "id": "a", "num_servers": 1, "service_time": 1},
            {"type": "MultiServer", "id": "b", "num_servers": 1, "service_time": 1},
            {"type": "Sink", "id": "snk"}]})
        await call("connect_batch", {"connections": [
            {"origin": "src", "destinations": ["a", "b"],
             "strategy": {"type": "Parameterized", "parameter": "route"}},
            {"origin": "a", "destinations": ["snk"]}, {"origin": "b", "destinations": ["snk"]}]})
        added = await call("add_downtimes_batch", {"downtimes": [
            {"type": "Timetable", "targets": ["b"], "intervals": [{"start": 0, "duration": 10}]}]})
        validation = await call("validate_model")
        await call("initialize_model")
        run_b = await call("run_experiment", {"stop_time": 20})
        await call("set_parameters", {"parameters": {"route": 0}})
        run_a = await call("run_experiment", {"stop_time": 20})
        exported = await call("export_model_spec")
        return added, validation, run_b, run_a, exported["spec"]

    added, validation, run_b, run_a, exported = run_session(script)
    assert added == {"status": "success", "added": 1, "failed_at": None}
    assert validation == {"valid": True, "issues": []}
    assert stats_by_id(run_b)["b"]["output_count"] == 10       # stopped during [0, 10]
    assert stats_by_id(run_b)["a"]["input_count"] == 0
    assert stats_by_id(run_a)["a"]["output_count"] == 20
    assert exported["parameters"] == {"route": 0} and exported["downtimes"][0]["type"] == "Timetable"


def test_invalid_spec_returns_every_issue_and_keeps_previous_model():
    bad = dict(LINE, connections=[{"origin": "src", "destinations": ["nope"]},
                                  {"origin": "snk", "destinations": ["q"]}])

    async def script(call):
        await call("load_model_spec", {"spec": LINE})
        error = await call("load_model_spec", {"spec": bad})
        listed = await call("list_elements")
        return error, listed

    error, listed = run_session(script)
    assert error["error"]["type"] == "SpecError"
    assert {i["code"] for i in error["error"]["issues"]} == {"E_UNKNOWN_ELEMENT", "E_SINK_AS_ORIGIN"}
    assert len(listed["elements"]) == 4


def test_validate_model_reports_warnings():
    async def script(call):
        await call("create_elements_batch", {"elements": [
            {"type": "InfiniteSource", "id": "src"}, {"type": "ItemsQueue", "id": "q", "capacity": 3},
            {"type": "Sink", "id": "snk"}]})
        await call("connect_batch", {"connections": [{"origin": "src", "destinations": ["q"]}]})
        return await call("validate_model")

    result = run_session(script)
    assert result["valid"] is True
    assert sorted(i["code"] for i in result["issues"]) == ["W_NO_INPUT", "W_UNCONNECTED_OUTPUT"]


def test_each_client_has_its_own_session():
    async def main():
        async with create_connected_server_and_client_session(mcp._mcp_server) as a, \
                create_connected_server_and_client_session(mcp._mcp_server) as b:
            await _call(a, "load_model_spec", {"spec": LINE})
            return await _call(a, "list_elements"), await _call(b, "list_elements")

    in_a, in_b = asyncio.run(main())
    assert len(in_a["elements"]) == 4 and in_b["elements"] == []


def test_supported_types_come_from_the_registry():
    from PyFlow.spec import element_types

    result = run_session(lambda call: call("get_supported_types"))
    assert set(result["element_types"]) == set(element_types())
    assert result["element_types"]["Combiner"]["component_ports"]
    assert "LabelRouting" in result["output_strategies"]["descriptions"]
    assert "Exponential~rate" in result["samplers"]


def test_resources_tools_and_stats():
    async def script(call):
        created = await call("create_resources_batch", {"resources": [{"id": "op", "kind": "operator",
                                                                       "capacity": 1}]})
        await call("create_elements_batch", {"elements": [
            {"type": "InfiniteSource", "id": "src"},
            {"type": "MultiServer", "id": "a", "num_servers": 1, "service_time": 1, "resources": ["op"]},
            {"type": "MultiServer", "id": "b", "num_servers": 1, "service_time": 1, "resources": ["op"]},
            {"type": "Sink", "id": "snk"}]})
        await call("connect_batch", {"connections": [{"origin": "src", "destinations": ["a", "b"]},
                                                     {"origin": "a", "destinations": ["snk"]},
                                                     {"origin": "b", "destinations": ["snk"]}]})
        failed = await call("create_elements_batch", {"elements": [
            {"type": "MultiServer", "id": "c", "num_servers": 1, "service_time": 1, "resources": ["ghost"]}]})
        await call("initialize_model")
        run = await call("run_experiment", {"stop_time": 10})
        exported = await call("export_model_spec")
        return created, failed, run, exported["spec"]

    created, failed, run, exported = run_session(script)
    assert created == {"status": "success", "created_ids": ["op"], "failed_at": None}
    assert failed["status"] == "partial_success" and "E_UNKNOWN_RESOURCE" in failed["failed_at"]["error_message"]
    assert stats_by_id(run)["snk"]["input_count"] == 10            # one operator: one item per time unit
    assert run["resources"] == [dict(run["resources"][0], id="op", utilization=1.0, capacity=1)]
    assert exported["resources"] == [{"id": "op", "name": "op", "kind": "operator", "capacity": 1,
                                      "unit_order": "skills_count ASC"}]


def test_set_resource_rules_tool():
    async def script(call):
        ok = await call("set_resource_rules", {"rules": {"request_order": "item.due ASC", "discipline": "strict"}})
        exported = await call("export_model_spec")
        return ok, exported["spec"]

    ok, exported = run_session(script)
    assert ok == {"request_order": "item.due ASC", "discipline": "strict"}
    assert exported["resource_rules"] == ok
