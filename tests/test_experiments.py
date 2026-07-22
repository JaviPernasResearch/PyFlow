"""Pytest suite for pyflow_mcp.experiments (harness capture) + score_experiment CLI."""

from __future__ import annotations

import json
import os

from pyflow_mcp.experiments import capture_model, capture_enabled
from pyflow_mcp import score_experiment


def _snapshot() -> dict:
    return {
        "state": "ready",
        "elements": [
            {"type": "InterArrivalSource", "id": "src", "name": "S",
             "interarrival": {"type": "expon", "scale": 8.0},
             "item_type": "Type1", "labels": None},
            {"type": "MultiServer", "id": "p1", "name": "P1", "num_servers": 1,
             "service_time": {"type": "norm", "loc": 10.0, "scale": 2.0}},
            {"type": "Sink", "id": "snk", "name": "Sink"},
        ],
        "connections": [
            {"origin": "src", "destinations": ["p1"], "strategy": "FirstAvailable"},
            {"origin": "p1", "destinations": ["snk"], "strategy": "FirstAvailable"},
        ],
        "last_run_info": None,
    }


def test_capture_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PYFLOW_MCP_CAPTURE", raising=False)
    assert capture_enabled() is False
    monkeypatch.setenv("PYFLOW_MCP_CAPTURE", "1")
    assert capture_enabled() is True


def test_capture_model_writes_scoreable_json(tmp_path):
    snap = _snapshot()
    path = capture_model(snap, run_id="unit", out_dir=str(tmp_path))
    assert os.path.basename(path) == "model_unit.json"

    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["run_id"] == "unit"
    assert saved["elements"] == snap["elements"]
    assert saved["connections"] == snap["connections"]


def test_score_experiment_cli_writes_report_and_summary(tmp_path):
    # A reference and an identical candidate capture in the same dir.
    ref = {"elements": _snapshot()["elements"], "connections": _snapshot()["connections"]}
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(json.dumps(ref), encoding="utf-8")
    capture_model(_snapshot(), run_id="run1", out_dir=str(tmp_path))

    rc = score_experiment.main([
        "--reference", str(ref_path),
        "--latest",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    assert (tmp_path / "model_run1_report.json").exists()
    assert (tmp_path / "model_run1_report.txt").exists()
    summary = (tmp_path / "summary.csv").read_text(encoding="utf-8")
    assert "overall_score" in summary          # header
    assert "1.0" in summary                     # perfect score row

    report = json.loads((tmp_path / "model_run1_report.json").read_text(encoding="utf-8"))
    assert report["overall_score"] == 1.0
    assert report["element_accuracy"] == 1.0
