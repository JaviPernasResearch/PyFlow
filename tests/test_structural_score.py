"""Pytest suite for pyflow_mcp.structural_score (evaluation-harness scorer).

These tests use describe_model()-shaped dicts directly, so they never touch the
MCP layer or the simulation clock.
"""

from __future__ import annotations

import copy
import json
import os

import pytest

from pyflow_mcp.structural_score import score_model, format_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _reference() -> dict:
    """A describe_model()-shaped reference model (extended Model 2, stochastic)."""
    return {
        "elements": [
            {"type": "InterArrivalSource", "id": "src1", "name": "Source1",
             "interarrival": {"type": "expon", "scale": 8.0},
             "item_type": "Type1", "labels": None},
            {"type": "InterArrivalSource", "id": "src2", "name": "Source2",
             "interarrival": {"type": "expon", "scale": 8.0},
             "item_type": "Type2", "labels": None},
            {"type": "MultiServer", "id": "p1", "name": "Processor1",
             "num_servers": 1, "service_time": {"type": "norm", "loc": 10.0, "scale": 2.0}},
            {"type": "MultiServer", "id": "p2", "name": "Processor2",
             "num_servers": 1, "service_time": {"type": "expon", "scale": 5.0}},
            {"type": "ItemsQueue", "id": "buf2", "name": "Buffer2", "capacity": 10},
            {"type": "MultiServer", "id": "p3", "name": "Processor3",
             "num_servers": 1, "service_time": {"type": "triang", "c": 0.5, "loc": 7.0, "scale": 4.0}},
            {"type": "Sink", "id": "snk", "name": "Sink"},
        ],
        "connections": [
            {"origin": "src1", "destinations": ["p1"], "strategy": "FirstAvailable"},
            {"origin": "src2", "destinations": ["p2"], "strategy": "FirstAvailable"},
            {"origin": "p1", "destinations": ["p3"], "strategy": "FirstAvailable"},
            {"origin": "p2", "destinations": ["buf2"], "strategy": "FirstAvailable"},
            {"origin": "buf2", "destinations": ["p3"], "strategy": "FirstAvailable"},
            {"origin": "p3", "destinations": ["snk"], "strategy": "FirstAvailable"},
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_identical_model_scores_perfect():
    ref = _reference()
    result = score_model(copy.deepcopy(ref), ref)
    assert result["overall_score"] == pytest.approx(1.0)
    for dim, val in result["breakdown"].items():
        assert val == pytest.approx(1.0), f"{dim} should be perfect"
    # "% of elements well constructed" headline metric.
    assert result["element_accuracy"] == pytest.approx(1.0)
    assert result["elements_fully_correct"] == len(ref["elements"])
    # format_report should not raise and should mention 100%.
    assert "100.00 %" in format_report(result)


def test_element_accuracy_counts_fully_correct_elements():
    """element_accuracy is all-or-nothing per element: 1 broken of 7 -> 6/7."""
    ref = _reference()
    cand = copy.deepcopy(ref)
    for e in cand["elements"]:
        if e["id"] == "p1":
            e["service_time"]["loc"] = 99.0  # p1 now wrong
    result = score_model(cand, ref)
    assert result["elements_fully_correct"] == len(ref["elements"]) - 1
    assert result["element_accuracy"] == pytest.approx(6 / 7)


def test_id_agnostic_rename_still_perfect():
    """Renaming every id/name must not change the score (structural matching)."""
    ref = _reference()
    cand = copy.deepcopy(ref)
    rename = {"src1": "A", "src2": "B", "p1": "X", "p2": "Y",
              "buf2": "Q", "p3": "Z", "snk": "OUT"}
    for e in cand["elements"]:
        e["id"] = rename[e["id"]]
        e["name"] = e["name"] + "_renamed"
    for c in cand["connections"]:
        c["origin"] = rename[c["origin"]]
        c["destinations"] = [rename[d] for d in c["destinations"]]

    result = score_model(cand, ref)
    assert result["overall_score"] == pytest.approx(1.0)


def test_missing_element_lowers_types_and_params():
    ref = _reference()
    cand = copy.deepcopy(ref)
    cand["elements"] = [e for e in cand["elements"] if e["id"] != "p2"]
    cand["connections"] = [
        c for c in cand["connections"] if c["origin"] != "p2"
    ]

    result = score_model(cand, ref)
    assert result["breakdown"]["element_types"] < 1.0
    assert result["breakdown"]["parameters"] < 1.0
    missing_types = {e["type"] for e in result["details"]["missing_elements"]}
    assert "MultiServer" in missing_types


def test_wrong_service_time_param_lowers_parameters():
    ref = _reference()
    cand = copy.deepcopy(ref)
    for e in cand["elements"]:
        if e["id"] == "p1":
            e["service_time"]["loc"] = 50.0  # way off
    result = score_model(cand, ref)
    assert result["breakdown"]["parameters"] < 1.0
    # element types and topology are untouched.
    assert result["breakdown"]["element_types"] == pytest.approx(1.0)
    assert result["breakdown"]["topology"] == pytest.approx(1.0)
    # A parameter mismatch must be reported on some matched element.
    assert any(m["mismatches"] for m in result["details"]["element_matches"])


def test_wrong_strategy_lowers_strategy_only():
    ref = _reference()
    cand = copy.deepcopy(ref)
    for c in cand["connections"]:
        if c["origin"] == "src1":
            c["strategy"] = "RoundRobin"
    result = score_model(cand, ref)
    assert result["breakdown"]["strategy"] < 1.0
    assert result["breakdown"]["topology"] == pytest.approx(1.0)
    assert result["details"]["strategy_mismatches"]


def test_missing_connection_lowers_topology():
    ref = _reference()
    cand = copy.deepcopy(ref)
    cand["connections"] = [c for c in cand["connections"] if c["origin"] != "buf2"]
    result = score_model(cand, ref)
    assert result["breakdown"]["topology"] < 1.0
    assert result["details"]["missing_connections"]


def test_tolerance_allows_tiny_float_drift():
    ref = _reference()
    cand = copy.deepcopy(ref)
    for e in cand["elements"]:
        if e["id"] == "p1":
            e["service_time"]["loc"] = 10.0 + 1e-9  # within default rel_tol
    result = score_model(cand, ref)
    assert result["breakdown"]["parameters"] == pytest.approx(1.0)


def test_reference_json_self_scores_perfect_if_present():
    """If the generated reference exists, it must self-score 100% (format lock)."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "references", "model3.json"
    )
    if not os.path.exists(path):
        pytest.skip("reference JSON not generated yet (python -m pyflow_mcp.reference_models)")
    with open(path, "r", encoding="utf-8") as f:
        ref = json.load(f)
    result = score_model(copy.deepcopy(ref), ref)
    assert result["overall_score"] == pytest.approx(1.0)
