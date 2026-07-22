"""Pytest suite for pyflow_mcp.reference_models (canonical specs + emitter)."""

from __future__ import annotations

import json

import pytest

from pyflow_mcp.reference_models import (
    MODELS, build_session, emit_reference, reference_from_session,
)
from pyflow_mcp.structural_score import score_model


@pytest.mark.parametrize("name", sorted(MODELS))
def test_every_model_builds_and_self_scores_perfect(name):
    elements, connections = MODELS[name]()
    session = build_session(elements, connections)
    ref = reference_from_session(session)
    assert ref["elements"] and ref["connections"]
    # A reference must be a perfect reproduction of itself.
    result = score_model(ref, ref)
    assert result["overall_score"] == pytest.approx(1.0)
    assert result["element_accuracy"] == pytest.approx(1.0)


def test_emit_reference_writes_scoreable_file(tmp_path):
    path = emit_reference("model2", out_dir=str(tmp_path))
    assert path.endswith("model2.json")
    ref = json.loads((tmp_path / "model2.json").read_text(encoding="utf-8"))
    assert {e["type"] for e in ref["elements"]} == {
        "InterArrivalSource", "MultiServer", "ItemsQueue", "Sink"
    }
    assert score_model(ref, ref)["overall_score"] == pytest.approx(1.0)


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        emit_reference("nope")


def test_model1_uses_label_expr_and_labels():
    """Model 1's fidelity depends on label_expr servers + source labels."""
    elements, _ = MODELS["model1"]()
    session = build_session(elements, [])
    specs = session.snapshot()["elements"]
    servers = [e for e in specs if e["type"] == "MultiServer"]
    assert all(e["service_time"]["type"] == "label_expr" for e in servers)
    sources = [e for e in specs if e["type"] == "InterArrivalSource"]
    assert all(e["labels"] for e in sources)  # every source carries PT labels
