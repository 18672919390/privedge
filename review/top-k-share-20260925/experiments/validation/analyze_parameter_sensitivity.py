"""Summarize G8 without treating its three-round sweep as model selection."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

import numpy as np


METHODS = (
    "censor_aware_item_context",
    "adaptive_censor_aware_item_context",
)
BASELINES = ("item_context", "average", "adaptive_context")


def _mean(records: Iterable[dict[str, str]], field: str) -> float:
    values = [float(record[field]) for record in records]
    return float(np.mean(values))


def _case_type(case: str) -> str:
    if case.startswith("prior_"):
        return "prior_sweep"
    if case.startswith("transfer_"):
        return "transfer_sweep"
    return "joint_grid"


def run(output_root: str = "outputs") -> dict[str, object]:
    group_root = Path(output_root) / "G8_parameter_sensitivity"
    summary_path = group_root / "group_summary.csv"
    manifest_path = group_root / "manifest.json"
    if not summary_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("run G8_parameter_sensitivity.py before analysis")

    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    configs = {case["name"]: case["config"] for case in manifest["cases"]}

    detailed: list[dict[str, object]] = []
    cases = sorted({row["case"] for row in rows})
    for case in cases:
        config = configs[case]
        case_rows = [row for row in rows if row["case"] == case]
        for method in METHODS:
            method_rows = [row for row in case_rows if row["method"] == method]
            record: dict[str, object] = {
                "case": case,
                "case_type": _case_type(case),
                "method": method,
                "prior_strength": config["censor_prior_strength"],
                "transfer_scale": config["censor_transfer_scale"],
                "recall": _mean(method_rows, "recall"),
                "ndcg": _mean(method_rows, "ndcg"),
                "recall_std_across_scenarios": float(
                    np.std([float(row["recall"]) for row in method_rows], ddof=1)
                ),
                "ndcg_std_across_scenarios": float(
                    np.std([float(row["ndcg"]) for row in method_rows], ddof=1)
                ),
            }
            for baseline in BASELINES:
                baseline_rows = [
                    row for row in case_rows if row["method"] == baseline
                ]
                record[f"recall_delta_vs_{baseline}"] = (
                    record["recall"] - _mean(baseline_rows, "recall")
                )
                record[f"ndcg_delta_vs_{baseline}"] = (
                    record["ndcg"] - _mean(baseline_rows, "ndcg")
                )
            detailed.append(record)

    analyses: list[dict[str, object]] = []
    for method in METHODS:
        for case_type in ("prior_sweep", "transfer_sweep", "joint_grid"):
            records = [
                row
                for row in detailed
                if row["method"] == method and row["case_type"] == case_type
            ]
            recall_values = np.asarray([float(row["recall"]) for row in records])
            ndcg_values = np.asarray([float(row["ndcg"]) for row in records])
            best_recall = records[int(np.argmax(recall_values))]
            best_ndcg = records[int(np.argmax(ndcg_values))]
            analyses.append(
                {
                    "method": method,
                    "case_type": case_type,
                    "point_count": len(records),
                    "recall_range": float(np.ptp(recall_values)),
                    "ndcg_range": float(np.ptp(ndcg_values)),
                    "best_recall_point": best_recall,
                    "best_ndcg_point": best_ndcg,
                }
            )

    payload = {
        "rounds_per_case": 3,
        "scenarios": ["OLH", "MIXED"],
        "seed": configs[cases[0]]["seed"],
        "interpretation": (
            "Preliminary descriptive sensitivity analysis. The same three "
            "rounds are paired across parameter settings. Results must not be "
            "used both to tune parameters and to claim final test performance."
        ),
        "details": detailed,
        "analyses": analyses,
    }
    with (group_root / "sensitivity_report.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    with (group_root / "sensitivity_table.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detailed[0]))
        writer.writeheader()
        writer.writerows(detailed)
    return payload


if __name__ == "__main__":
    report = run()
    for result in report["analyses"]:
        best = result["best_recall_point"]
        print(
            f"{result['method']} {result['case_type']}: "
            f"recall range={result['recall_range']:.3f}, "
            f"ndcg range={result['ndcg_range']:.3f}, "
            f"best recall={best['recall']:.3f} at "
            f"prior={best['prior_strength']}, transfer={best['transfer_scale']}"
        )
