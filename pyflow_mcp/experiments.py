"""Experiment capture for the evaluation harness.

HARNESS-ONLY. Not part of the agent-facing tool schemas. This module persists
the model the agent constructed (a ``describe_model()``-shaped snapshot) to disk
so it can later be scored against a ground-truth reference with
``structural_score``.

Capture is **off by default** and gated by an environment variable so normal
(production / Langflow) use is unaffected. Turn it on for an experiment session::

    # PowerShell
    $env:PYFLOW_MCP_CAPTURE = "1"
    # bash
    export PYFLOW_MCP_CAPTURE=1

Optional environment variables:
    PYFLOW_MCP_EXPERIMENT_DIR   output directory (default: "experiments")
    PYFLOW_MCP_RUN_ID           fixed run id; if unset a timestamp is used, so
                                every initialize_model call writes a new file.

The server calls :func:`capture_model` from ``initialize_model`` — the moment
the topology is frozen (BUILDING → READY), i.e. construction is complete. Since
connections must be added before initialize, this snapshot is the final model
structure.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Optional

_TRUE = {"1", "true", "yes", "on"}


def experiment_dir() -> str:
    return os.environ.get("PYFLOW_MCP_EXPERIMENT_DIR", "experiments")


def capture_enabled() -> bool:
    return os.environ.get("PYFLOW_MCP_CAPTURE", "").strip().lower() in _TRUE


def _run_id() -> str:
    rid = os.environ.get("PYFLOW_MCP_RUN_ID")
    if rid:
        return rid
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def capture_model(
    snapshot: dict,
    *,
    run_id: Optional[str] = None,
    out_dir: Optional[str] = None,
) -> str:
    """Write *snapshot*'s model (elements + connections) to a JSON file.

    Returns the path written. The file is directly scoreable by
    ``structural_score`` (which reads only ``elements`` and ``connections``).
    """
    out_dir = out_dir or experiment_dir()
    run_id = run_id or _run_id()
    os.makedirs(out_dir, exist_ok=True)

    payload = {
        "run_id": run_id,
        "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "state": snapshot.get("state"),
        "elements": snapshot.get("elements", []),
        "connections": snapshot.get("connections", []),
    }
    path = os.path.join(out_dir, f"model_{run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path
