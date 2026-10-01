"""Row-by-row comparison of two experiment runs that share a grid (e.g. a recorded run and its v4.1-policy rerun)."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parents[2] / "runs"
METRICS = ("attack_success", "recall", "ndcg")


def run_dir(run_id: str) -> Path:
    return RUNS / run_id.rsplit("-", 2)[0] / run_id


def rows(run_id: str) -> dict[tuple, dict]:
    with (run_dir(run_id) / "results.csv").open(encoding="utf-8") as handle:
        data = list(csv.DictReader(handle))
    keys = [k for k in data[0] if k not in METRICS and not k.endswith("_rate") and not k.startswith("n_")]
    return {tuple(r[k] for k in keys): r for r in data}


def compare(a: str, b: str) -> dict:
    ra, rb = rows(a), rows(b)
    shared = set(ra) & set(rb)
    changed = []
    for key in sorted(shared):
        diffs = {m: float(rb[key][m]) - float(ra[key][m]) for m in METRICS if m in ra[key]}
        if any(abs(d) > 1e-12 for d in diffs.values()):
            changed.append({"key": list(key), **diffs})
    return {"recorded": a, "rerun": b, "rows_recorded": len(ra), "rows_rerun": len(rb), "shared": len(shared),
            "changed": len(changed), "examples": changed[:10]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pairs", nargs="+", help="recorded_run_id=rerun_run_id")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = [compare(*p.split("=")) for p in args.pairs]
    for r in report:
        print(f'{r["rerun"]}: shared {r["shared"]}/{r["rows_recorded"]}, changed {r["changed"]}')
        for e in r["examples"][:3]:
            print("   ", e)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
