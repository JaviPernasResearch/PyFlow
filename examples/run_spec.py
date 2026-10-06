"""Validate and run a model file, then print a short report.

    python examples/run_spec.py examples/models/assembly_line.json [--seed 7] [--until 10000] [--json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyFlow.spec import ModelSpec, SpecError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", help="model file (.json, or .yaml with PyYAML installed)")
    parser.add_argument("--seed", type=int, default=None, help="override the seed of the file")
    parser.add_argument("--until", type=float, default=None, help="override run.until")
    parser.add_argument("--warmup", type=float, default=None, help="override run.warmup")
    parser.add_argument("--json", action="store_true", help="print the full results as JSON")
    args = parser.parse_args()

    spec = ModelSpec.from_file(args.file)
    for issue in spec.validate_model():
        print(f"[{issue.severity}] {issue}")
    try:
        built = spec.build(seed=args.seed)
    except SpecError:
        return 1
    results = built.run(args.until, warmup=args.warmup)

    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    print(f"\n{spec.name}: t = {results['time']:g}, seed = {results['seed']}, warm-up = {results['warmup']}")
    print(f"{'element':<12}{'in':>8}{'out':>8}{'WIP avg':>10}{'stay avg':>10}  states")
    for element_id, s in results["elements"].items():
        stay = "-" if s["staytime_average"] is None else f"{s['staytime_average']:.2f}"
        states = ", ".join(f"{k} {v:.0%}" for k, v in sorted(s["state_ratios"].items(), key=lambda kv: -kv[1]) if v)
        print(f"{element_id:<12}{s['input_count']:>8.0f}{s['output_count']:>8.0f}{s['content_average']:>10.2f}"
              f"{stay:>10}  {states}")
    if results["resources"]:
        print(f"\n{'resource':<12}{'units':>6}{'util':>8}{'wait avg':>10}{'grants':>8}  units")
        for pool_id, r in results["resources"].items():
            wait = "-" if r["wait_average"] is None else f"{r['wait_average']:.2f}"
            units = ", ".join(f"{n} {u['utilization']:.0%}" for n, u in r["units"].items())
            print(f"{pool_id:<12}{r['capacity']:>6}{r['utilization']:>8.0%}{wait:>10}{r['grants']:>8}  {units}")
    repairs = [d for d in results["downtimes"] if "repairs" in d]
    for d in repairs:
        wait = "-" if d["repair_wait_average"] is None else f"{d['repair_wait_average']:.2f}"
        print(f"repairs of {d['target']}: {d['repairs']} (resources {', '.join(d['repair_resources'])}, "
              f"wait avg {wait})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
