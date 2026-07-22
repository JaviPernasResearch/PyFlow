"""CLI: score a captured experiment model against a ground-truth reference.

HARNESS-ONLY. Reads a model JSON produced by the experiment capture (see
``experiments.py``) or any ``describe_model()`` output, scores it with
``structural_score``, prints the report, writes a per-run report (``.txt`` +
``.json``), and appends one row to ``<experiment_dir>/summary.csv`` so many
runs can be compared at a glance.

Typical loop (after a prompt -> agent-builds-model -> chat-report cycle)::

    # 1. run the agent with capture on (server env PYFLOW_MCP_CAPTURE=1);
    #    initialize_model auto-writes experiments/model_<ts>.json
    # 2. score the newest capture against the ground truth:
    python -m pyflow_mcp.score_experiment --latest

    # or score a specific file / a saved describe_model output:
    python -m pyflow_mcp.score_experiment --candidate experiments/model_20260722.json
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
from typing import Optional

from .experiments import experiment_dir
from .structural_score import format_report, score_model

DEFAULT_REFERENCE = os.path.join("references", "model3.json")
SUMMARY_COLUMNS = [
    "run_id", "candidate", "reference",
    "overall_score", "element_accuracy",
    "element_types", "parameters", "topology", "strategy",
]


def _latest_capture(out_dir: str) -> Optional[str]:
    """Newest model_*.json in *out_dir*, excluding report files."""
    files = glob.glob(os.path.join(out_dir, "model_*.json"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _append_summary(summary_path: str, row: dict) -> None:
    is_new = not os.path.exists(summary_path)
    with open(summary_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score a captured agent model against a ground-truth reference."
    )
    parser.add_argument("--reference", default=None,
                        help=f"Ground-truth model JSON (default: {DEFAULT_REFERENCE})")
    parser.add_argument("--model", default=None,
                        help="Shortcut: use references/<model>.json (e.g. --model model2)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--candidate", help="Path to a captured model / describe_model JSON")
    group.add_argument("--latest", action="store_true",
                       help="Score the newest capture in the experiment dir")
    parser.add_argument("--out-dir", default=None,
                        help="Experiment dir for --latest, reports and summary.csv "
                             "(default: PYFLOW_MCP_EXPERIMENT_DIR or 'experiments')")
    parser.add_argument("--rel-tol", type=float, default=1e-3,
                        help="Relative tolerance for numeric parameter matching")
    parser.add_argument("--no-report-files", action="store_true",
                        help="Print only; do not write report or summary files")
    args = parser.parse_args(argv)

    # Resolve the reference: explicit --reference wins, then --model shortcut,
    # then the default (model3).
    if args.reference and args.model:
        parser.error("Pass only one of --reference / --model.")
    if args.model:
        reference_path = os.path.join("references", f"{args.model}.json")
    else:
        reference_path = args.reference or DEFAULT_REFERENCE

    out_dir = args.out_dir or experiment_dir()

    cand_path = args.candidate
    if cand_path is None:
        cand_path = _latest_capture(out_dir)
        if cand_path is None:
            parser.error(
                f"No capture found in '{out_dir}'. Run an experiment with "
                "PYFLOW_MCP_CAPTURE=1, or pass --candidate <file>."
            )
        print(f"[latest] {cand_path}")

    reference = _load(reference_path)
    candidate = _load(cand_path)
    result = score_model(candidate, reference, rel_tol=args.rel_tol)

    report_txt = format_report(result)
    print(report_txt)

    if args.no_report_files:
        return 0

    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(cand_path))[0]
    json_path = os.path.join(out_dir, f"{stem}_report.json")
    txt_path = os.path.join(out_dir, f"{stem}_report.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"candidate": cand_path, "reference": reference_path, **result}, f, indent=2)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_txt + "\n")

    b = result["breakdown"]
    _append_summary(os.path.join(out_dir, "summary.csv"), {
        "run_id": candidate.get("run_id", stem),
        "candidate": cand_path,
        "reference": reference_path,
        "overall_score": round(result["overall_score"], 4),
        "element_accuracy": round(result.get("element_accuracy", 0.0), 4),
        "element_types": round(b["element_types"], 4),
        "parameters": round(b["parameters"], 4),
        "topology": round(b["topology"], 4),
        "strategy": round(b["strategy"], 4),
    })

    print(f"\nReport written : {json_path}")
    print(f"                 {txt_path}")
    print(f"Summary updated: {os.path.join(out_dir, 'summary.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
