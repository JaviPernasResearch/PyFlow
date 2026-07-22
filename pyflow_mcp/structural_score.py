"""Structural correctness scorer for agent-built PyFlow models.

EVALUATION-HARNESS ONLY. This module is intentionally *not* registered as an MCP
tool and is never imported by ``server.py`` — the LLM never sees it and it costs
no tokens at agent runtime. It exists so an evaluation harness can measure how
closely an agent's model matches a hand-built ground-truth reference.

Both inputs are ``describe_model()``-shaped dicts (as produced by
``SimulationSession.snapshot()``)::

    {"elements": [<element spec>, ...],
     "connections": [<connection spec>, ...],
     ...}                                   # extra keys (state, last_run_info) ignored

The score is broken into four dimensions:

    element_types  — are the right element *types* present, in the right counts?
    parameters     — do matched elements have matching key parameters?
    topology       — do the directed connections (origin → destination) match?
    strategy       — do matched connections use the same output strategy?

Matching is **id-agnostic**: agents pick their own element ids/names, so
reference elements are matched to candidate elements by type + parameter
similarity (bipartite assignment), never by id. Ids are used only to translate
connection endpoints once the element mapping is known.

CLI::

    python -m pyflow_mcp.structural_score <reference.json> <candidate.json>
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Optional

try:  # scipy is already a PyFlow dependency; greedy fallback if it is ever missing.
    from scipy.optimize import linear_sum_assignment
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover - defensive
    _HAVE_SCIPY = False


DEFAULT_WEIGHTS = {
    "element_types": 0.25,
    "parameters": 0.30,
    "topology": 0.30,
    "strategy": 0.15,
}

# Numeric fields that define each distribution / service-time spec.
_DIST_FIELDS = {
    "expon": ("scale",),
    "uniform": ("loc", "scale"),
    "norm": ("loc", "scale"),
    "triang": ("c", "loc", "scale"),
}

# Which spec keys carry the "key parameters" for each element type.
_PARAM_KEYS = {
    "InterArrivalSource": ("interarrival", "item_type", "labels"),
    "ItemsQueue": ("capacity",),
    "MultiServer": ("num_servers", "service_time"),
    "Sink": (),
    "ScheduleSource": ("jobs",),
}


# ---------------------------------------------------------------------------
# Low-level comparisons
# ---------------------------------------------------------------------------

def _num_close(a: Any, b: Any, rel_tol: float) -> bool:
    try:
        a = float(a)
        b = float(b)
    except (TypeError, ValueError):
        return a == b
    if a == b:
        return True
    return abs(a - b) <= rel_tol * max(abs(a), abs(b), 1e-9)


def _dist_similarity(ref: Optional[dict], cand: Optional[dict], rel_tol: float):
    """Similarity in [0,1] between two distribution / service-time spec dicts.

    Returns (score, list_of_mismatch_strings). A type mismatch scores 0.
    """
    if ref is None and cand is None:
        return 1.0, []
    if ref is None or cand is None:
        return 0.0, ["distribution present on only one side"]

    r_type = ref.get("type")
    c_type = cand.get("type")
    if r_type != c_type:
        return 0.0, [f"distribution type {c_type!r} != expected {r_type!r}"]

    # label_expr — compare the expression string exactly.
    if r_type == "label_expr":
        if ref.get("expression") == cand.get("expression"):
            return 1.0, []
        return 0.0, [
            f"label_expr expression {cand.get('expression')!r} != {ref.get('expression')!r}"
        ]

    fields = _DIST_FIELDS.get(r_type, ())
    if not fields:
        return 1.0, []

    matched = 0
    mismatches = []
    for f in fields:
        if _num_close(ref.get(f), cand.get(f), rel_tol):
            matched += 1
        else:
            mismatches.append(f"{r_type}.{f}={cand.get(f)} != {ref.get(f)}")
    return matched / len(fields), mismatches


def _element_param_similarity(ref: dict, cand: dict, rel_tol: float):
    """Per-element parameter similarity in [0,1] plus a list of mismatches.

    Assumes ref and cand share the same element ``type``.
    """
    etype = ref.get("type")
    keys = _PARAM_KEYS.get(etype, ())
    if not keys:  # Sink — nothing to compare
        return 1.0, []

    scores = []
    mismatches = []
    for key in keys:
        r_val = ref.get(key)
        c_val = cand.get(key)

        if key in ("interarrival", "service_time"):
            s, mm = _dist_similarity(r_val, c_val, rel_tol)
            scores.append(s)
            mismatches.extend(f"{key}: {m}" for m in mm)
        elif key in ("num_servers", "capacity"):
            ok = _num_close(r_val, c_val, rel_tol)
            scores.append(1.0 if ok else 0.0)
            if not ok:
                mismatches.append(f"{key}={c_val} != {r_val}")
        else:  # item_type, jobs, and any other scalar/structured field → exact
            ok = r_val == c_val
            scores.append(1.0 if ok else 0.0)
            if not ok:
                mismatches.append(f"{key}={c_val!r} != {r_val!r}")

    return (sum(scores) / len(scores) if scores else 1.0), mismatches


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

def _assign(cost: list[list[float]]) -> list[tuple[int, int]]:
    """Return (row, col) pairs minimising total cost. Rectangular-safe."""
    n_rows = len(cost)
    n_cols = len(cost[0]) if n_rows else 0
    if n_rows == 0 or n_cols == 0:
        return []

    if _HAVE_SCIPY:
        rows, cols = linear_sum_assignment(cost)
        return list(zip(rows.tolist(), cols.tolist()))

    # Greedy fallback: repeatedly take the cheapest available (row, col).
    pairs = []
    used_rows: set[int] = set()
    used_cols: set[int] = set()
    candidates = sorted(
        ((cost[r][c], r, c) for r in range(n_rows) for c in range(n_cols)),
        key=lambda t: t[0],
    )
    for _, r, c in candidates:
        if r in used_rows or c in used_cols:
            continue
        used_rows.add(r)
        used_cols.add(c)
        pairs.append((r, c))
        if len(pairs) == min(n_rows, n_cols):
            break
    return pairs


def _match_elements(ref_elems: list[dict], cand_elems: list[dict], rel_tol: float):
    """Bipartite-match reference→candidate elements within each type.

    Returns (matches, unmatched_ref, unmatched_cand) where matches is a list of
    (ref_elem, cand_elem, param_score, mismatches).
    """
    by_type_ref: dict[str, list[dict]] = {}
    by_type_cand: dict[str, list[dict]] = {}
    for e in ref_elems:
        by_type_ref.setdefault(e.get("type"), []).append(e)
    for e in cand_elems:
        by_type_cand.setdefault(e.get("type"), []).append(e)

    matches = []
    unmatched_ref: list[dict] = []
    matched_cand_ids: set[str] = set()

    for etype, r_list in by_type_ref.items():
        c_list = by_type_cand.get(etype, [])
        if not c_list:
            unmatched_ref.extend(r_list)
            continue

        # Precompute similarity for every ref×cand pair of this type.
        sim = [[_element_param_similarity(r, c, rel_tol) for c in c_list] for r in r_list]
        cost = [[1.0 - sim[i][j][0] for j in range(len(c_list))] for i in range(len(r_list))]

        assigned_rows: set[int] = set()
        for i, j in _assign(cost):
            score, mism = sim[i][j]
            matches.append((r_list[i], c_list[j], score, mism))
            assigned_rows.add(i)
            matched_cand_ids.add(c_list[j].get("id"))

        for i, r in enumerate(r_list):
            if i not in assigned_rows:
                unmatched_ref.append(r)

    unmatched_cand = [c for c in cand_elems if c.get("id") not in matched_cand_ids]
    return matches, unmatched_ref, unmatched_cand


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _edge_map(connections: list[dict]) -> dict[tuple[str, str], str]:
    """Flatten connections into {(origin, destination): strategy}."""
    edges: dict[tuple[str, str], str] = {}
    for conn in connections:
        origin = conn.get("origin")
        strategy = conn.get("strategy", "FirstAvailable")
        for dst in conn.get("destinations", []):
            edges[(origin, dst)] = strategy
    return edges


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_model(
    candidate: dict,
    reference: dict,
    *,
    weights: Optional[dict] = None,
    rel_tol: float = 1e-3,
) -> dict:
    """Score a candidate model against a reference. See module docstring.

    Returns a dict with ``overall_score`` (0..1), a per-dimension ``breakdown``,
    and a ``details`` block for diagnostics.
    """
    weights = weights or DEFAULT_WEIGHTS
    ref_elems = list(reference.get("elements", []))
    cand_elems = list(candidate.get("elements", []))
    ref_conns = list(reference.get("connections", []))
    cand_conns = list(candidate.get("connections", []))

    # --- 1. Element-type score (count-based) ---
    ref_type_counts = Counter(e.get("type") for e in ref_elems)
    cand_type_counts = Counter(e.get("type") for e in cand_elems)
    total_ref_elems = sum(ref_type_counts.values())
    matched_types = sum(min(n, cand_type_counts.get(t, 0)) for t, n in ref_type_counts.items())
    type_score = matched_types / total_ref_elems if total_ref_elems else 1.0

    # --- 2. Element matching + parameter score ---
    matches, unmatched_ref, unmatched_cand = _match_elements(ref_elems, cand_elems, rel_tol)
    # Parameter score averages over ALL reference elements, so missing/unmatched
    # elements drag the parameter dimension down too (score 0 each).
    param_sum = sum(score for _, _, score, _ in matches)
    param_score = param_sum / total_ref_elems if total_ref_elems else 1.0

    # "% of elements well constructed": a reference element counts as fully
    # correct only if it was matched AND every key parameter matched (score 1.0).
    fully_correct = sum(1 for _, _, score, _ in matches if score >= 1.0 - 1e-9)
    element_accuracy = fully_correct / total_ref_elems if total_ref_elems else 1.0

    # ref_id → cand_id map for translating connection endpoints.
    id_map = {r.get("id"): c.get("id") for r, c, _, _ in matches}

    # --- 3 & 4. Topology + strategy ---
    ref_edges = _edge_map(ref_conns)
    cand_edges = _edge_map(cand_conns)
    total_ref_edges = len(ref_edges)

    matched_edges = 0
    strategy_matched = 0
    missing_connections = []
    strategy_mismatches = []
    for (r_o, r_d), r_strat in ref_edges.items():
        c_o = id_map.get(r_o)
        c_d = id_map.get(r_d)
        if c_o is not None and c_d is not None and (c_o, c_d) in cand_edges:
            matched_edges += 1
            c_strat = cand_edges[(c_o, c_d)]
            if c_strat == r_strat:
                strategy_matched += 1
            else:
                strategy_mismatches.append(
                    {"edge": [r_o, r_d], "expected": r_strat, "got": c_strat}
                )
        else:
            missing_connections.append({"origin": r_o, "destination": r_d, "strategy": r_strat})

    topology_score = matched_edges / total_ref_edges if total_ref_edges else 1.0
    strategy_score = (strategy_matched / matched_edges) if matched_edges else (
        1.0 if total_ref_edges == 0 else 0.0
    )

    breakdown = {
        "element_types": type_score,
        "parameters": param_score,
        "topology": topology_score,
        "strategy": strategy_score,
    }
    overall = sum(breakdown[k] * weights[k] for k in weights)

    return {
        "overall_score": overall,
        "element_accuracy": element_accuracy,
        "elements_fully_correct": fully_correct,
        "breakdown": breakdown,
        "weights": dict(weights),
        "details": {
            "element_matches": [
                {
                    "ref_id": r.get("id"),
                    "cand_id": c.get("id"),
                    "type": r.get("type"),
                    "param_score": score,
                    "mismatches": mism,
                }
                for r, c, score, mism in matches
            ],
            "missing_elements": [
                {"id": e.get("id"), "type": e.get("type"), "name": e.get("name")}
                for e in unmatched_ref
            ],
            "extra_elements": [
                {"id": e.get("id"), "type": e.get("type"), "name": e.get("name")}
                for e in unmatched_cand
            ],
            "missing_connections": missing_connections,
            "strategy_mismatches": strategy_mismatches,
            "counts": {
                "reference_elements": total_ref_elems,
                "candidate_elements": len(cand_elems),
                "reference_edges": total_ref_edges,
                "matched_edges": matched_edges,
            },
        },
    }


def format_report(result: dict) -> str:
    """Render a human-readable text report from :func:`score_model` output."""
    b = result["breakdown"]
    w = result.get("weights", DEFAULT_WEIGHTS)
    d = result["details"]
    lines = []
    lines.append("=" * 56)
    lines.append("  PyFlow Structural Correctness Report")
    lines.append("=" * 56)
    lines.append(f"  OVERALL SCORE          : {result['overall_score'] * 100:6.2f} %")
    if "element_accuracy" in result:
        cnt_ref = result["details"]["counts"]["reference_elements"]
        lines.append(
            f"  Elements well built    : {result['element_accuracy'] * 100:6.2f} %"
            f"   ({result['elements_fully_correct']}/{cnt_ref})"
        )
    lines.append("")
    lines.append(f"  {'Dimension':<16}{'Score':>9}{'Weight':>9}")
    lines.append(f"  {'-' * 34}")
    for key in ("element_types", "parameters", "topology", "strategy"):
        lines.append(f"  {key:<16}{b[key] * 100:>8.2f}%{w[key]:>9.2f}")
    lines.append("")

    cnt = d["counts"]
    lines.append(
        f"  Elements: {cnt['candidate_elements']} candidate vs "
        f"{cnt['reference_elements']} reference   |   "
        f"Edges matched: {cnt['matched_edges']}/{cnt['reference_edges']}"
    )

    if d["missing_elements"]:
        lines.append("")
        lines.append("  Missing elements (in reference, not matched):")
        for e in d["missing_elements"]:
            lines.append(f"    - {e['type']} '{e['id']}'")
    if d["extra_elements"]:
        lines.append("")
        lines.append("  Extra elements (in candidate, unmatched):")
        for e in d["extra_elements"]:
            lines.append(f"    - {e['type']} '{e['id']}'")
    if d["missing_connections"]:
        lines.append("")
        lines.append("  Missing connections:")
        for c in d["missing_connections"]:
            lines.append(f"    - {c['origin']} -> {c['destination']} ({c['strategy']})")
    if d["strategy_mismatches"]:
        lines.append("")
        lines.append("  Strategy mismatches:")
        for s in d["strategy_mismatches"]:
            lines.append(
                f"    - {s['edge'][0]} -> {s['edge'][1]}: expected {s['expected']}, got {s['got']}"
            )

    param_issues = [m for m in d["element_matches"] if m["mismatches"]]
    if param_issues:
        lines.append("")
        lines.append("  Parameter mismatches on matched elements:")
        for m in param_issues:
            lines.append(f"    - {m['type']} '{m['ref_id']}' ~ '{m['cand_id']}':")
            for mm in m["mismatches"]:
                lines.append(f"        - {mm}")

    lines.append("=" * 56)
    return "\n".join(lines)


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Score an agent-built PyFlow model against a ground-truth reference."
    )
    parser.add_argument("reference", help="Path to the reference model JSON (ground truth)")
    parser.add_argument("candidate", help="Path to the candidate model JSON (describe_model output)")
    parser.add_argument("--json", action="store_true", help="Emit the raw result dict as JSON")
    parser.add_argument("--rel-tol", type=float, default=1e-3, help="Relative tolerance for numeric params")
    args = parser.parse_args(argv)

    reference = _load(args.reference)
    candidate = _load(args.candidate)
    result = score_model(candidate, reference, rel_tol=args.rel_tol)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
