"""Independent-seed validation for the main deployable fusion methods.

This is a confirmatory laptop-scale validation, not another G-series ablation.
Hyperparameters are fixed before the run.  The independent statistical unit is
the seed: three rounds are averaged within each seed before confidence
intervals and paired tests are calculated.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiment import ExperimentConfig, run


VALIDATION_SEEDS = (
    110734825,
    328497261,
    594821037,
    781306459,
    1029384756,
    1265078943,
    1492837601,
    1736509284,
    1964285730,
    2140679351,
)
METHODS = (
    "average",
    "adaptive_context",
    "censor_aware_item_context",
    "adaptive_censor_aware_item_context",
)
COMPARISONS = (
    ("censor_aware_item_context", "average"),
    ("censor_aware_item_context", "adaptive_context"),
    ("adaptive_censor_aware_item_context", "average"),
    ("adaptive_censor_aware_item_context", "adaptive_context"),
    ("adaptive_censor_aware_item_context", "censor_aware_item_context"),
)
METRICS = ("recall", "ndcg")
SCENARIOS = ("OLH", "MIXED")
BOOTSTRAP_SAMPLES = 10_000
ANALYSIS_SEED = 20260910


def build_config(seed: int) -> ExperimentConfig:
    """Return the frozen weak-context configuration used for every seed."""
    return ExperimentConfig(
        context_quality=0.25,
        censor_prior_strength=0.10,
        censor_transfer_scale=1.0,
        rounds=3,
        seed=seed,
        mechanisms=SCENARIOS,
    )


def _mean(values: Iterable[float]) -> float:
    array = np.asarray(list(values), dtype=float)
    return float(np.mean(array))


def _percentile_interval(values: np.ndarray, confidence: float = 0.95) -> tuple[float, float]:
    alpha = (1.0 - confidence) / 2.0
    return (
        float(np.quantile(values, alpha)),
        float(np.quantile(values, 1.0 - alpha)),
    )


def _bootstrap_mean_interval(
    values: np.ndarray, rng: np.random.Generator
) -> tuple[float, float]:
    """Percentile bootstrap CI, resampling independent seed-level values."""
    indices = rng.integers(0, len(values), size=(BOOTSTRAP_SAMPLES, len(values)))
    bootstrap_means = np.mean(values[indices], axis=1)
    return _percentile_interval(bootstrap_means)


def _exact_sign_flip_pvalue(deltas: np.ndarray) -> float:
    """Two-sided exact paired randomization test for a zero mean difference."""
    nonzero = deltas[np.abs(deltas) > 1e-15]
    if len(nonzero) == 0:
        return 1.0
    observed = abs(float(np.mean(nonzero)))
    permutation_count = 1 << len(nonzero)
    exceedances = 0
    for mask in range(permutation_count):
        signs = np.fromiter(
            (1.0 if mask & (1 << index) else -1.0 for index in range(len(nonzero))),
            dtype=float,
            count=len(nonzero),
        )
        permuted = abs(float(np.mean(nonzero * signs)))
        exceedances += permuted >= observed - 1e-15
    return exceedances / permutation_count


def _seed_level_rows(raw_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[int, str, str], list[dict[str, object]]] = {}
    for row in raw_rows:
        if row["method"] not in METHODS:
            continue
        key = (int(row["seed"]), str(row["scenario"]), str(row["method"]))
        grouped.setdefault(key, []).append(row)

    result: list[dict[str, object]] = []
    for (seed, scenario, method), records in sorted(grouped.items()):
        result.append(
            {
                "seed": seed,
                "scenario": scenario,
                "method": method,
                "rounds": len(records),
                "recall": _mean(float(record["recall"]) for record in records),
                "ndcg": _mean(float(record["ndcg"]) for record in records),
                "coverage": _mean(float(record["coverage"]) for record in records),
            }
        )
    return result


def _records_for_scope(
    rows: list[dict[str, object]], scenario: str, method: str
) -> dict[int, dict[str, float]]:
    relevant = [
        row
        for row in rows
        if row["method"] == method
        and (scenario == "ALL" or row["scenario"] == scenario)
    ]
    by_seed: dict[int, list[dict[str, object]]] = {}
    for row in relevant:
        by_seed.setdefault(int(row["seed"]), []).append(row)
    return {
        seed: {
            metric: _mean(float(record[metric]) for record in records)
            for metric in (*METRICS, "coverage")
        }
        for seed, records in by_seed.items()
    }


def analyze(
    raw_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    seed_rows = _seed_level_rows(raw_rows)
    rng = np.random.default_rng(ANALYSIS_SEED)
    method_summary: list[dict[str, object]] = []
    comparisons: list[dict[str, object]] = []

    for scenario in (*SCENARIOS, "ALL"):
        for method in METHODS:
            records = _records_for_scope(seed_rows, scenario, method)
            summary: dict[str, object] = {
                "scenario": scenario,
                "method": method,
                "independent_seeds": len(records),
                "rounds_per_seed": 3,
            }
            for metric in (*METRICS, "coverage"):
                values = np.asarray(
                    [records[seed][metric] for seed in sorted(records)], dtype=float
                )
                lower, upper = _bootstrap_mean_interval(values, rng)
                summary[f"{metric}_mean"] = float(np.mean(values))
                summary[f"{metric}_std_across_seeds"] = float(np.std(values, ddof=1))
                summary[f"{metric}_ci95_low"] = lower
                summary[f"{metric}_ci95_high"] = upper
            method_summary.append(summary)

        for method, baseline in COMPARISONS:
            method_records = _records_for_scope(seed_rows, scenario, method)
            baseline_records = _records_for_scope(seed_rows, scenario, baseline)
            common_seeds = sorted(set(method_records).intersection(baseline_records))
            for metric in METRICS:
                deltas = np.asarray(
                    [
                        method_records[seed][metric] - baseline_records[seed][metric]
                        for seed in common_seeds
                    ],
                    dtype=float,
                )
                lower, upper = _bootstrap_mean_interval(deltas, rng)
                tolerance = 1e-12
                comparisons.append(
                    {
                        "scenario": scenario,
                        "method": method,
                        "baseline": baseline,
                        "metric": metric,
                        "independent_seed_pairs": len(deltas),
                        "mean_delta": float(np.mean(deltas)),
                        "std_delta_across_seeds": float(np.std(deltas, ddof=1)),
                        "ci95_low": lower,
                        "ci95_high": upper,
                        "wins": int(np.sum(deltas > tolerance)),
                        "ties": int(np.sum(np.abs(deltas) <= tolerance)),
                        "losses": int(np.sum(deltas < -tolerance)),
                        "exact_sign_flip_pvalue": _exact_sign_flip_pvalue(deltas),
                    }
                )

    report = {
        "design": {
            "purpose": "Independent-seed confirmatory validation; not a new G-series experiment.",
            "independent_unit": "seed",
            "seeds": list(VALIDATION_SEEDS),
            "rounds_per_seed": 3,
            "scenarios": list(SCENARIOS),
            "methods": list(METHODS),
            "context_quality": 0.25,
            "censor_prior_strength": 0.10,
            "censor_transfer_scale": 1.0,
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "analysis_seed": ANALYSIS_SEED,
        },
        "interpretation": (
            "Confidence intervals and exact paired randomization tests use ten "
            "seed-level means; the three rounds within a seed are not treated "
            "as independent replicates. This is stronger than the prior "
            "three-round descriptive analysis but remains laptop-scale "
            "synthetic evidence. P-values are unadjusted exploratory diagnostics."
        ),
        "method_summary": method_summary,
        "paired_comparisons": comparisons,
    }
    return method_summary, comparisons, report


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def execute(output_root: str = "outputs") -> dict[str, object]:
    output_dir = Path(output_root) / "independent_seed_validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_rows: list[dict[str, object]] = []
    for index, seed in enumerate(VALIDATION_SEEDS, start=1):
        rows = run(build_config(seed))
        for row in rows:
            if row["method"] in METHODS:
                raw_rows.append({"seed": seed, **row})
        print(f"seed {index:02d}/{len(VALIDATION_SEEDS)} complete: {seed}")

    seed_rows = _seed_level_rows(raw_rows)
    method_summary, comparisons, report = analyze(raw_rows)
    _write_csv(output_dir / "round_results.csv", raw_rows)
    _write_csv(output_dir / "seed_level_results.csv", seed_rows)
    _write_csv(output_dir / "method_summary.csv", method_summary)
    _write_csv(output_dir / "paired_comparisons.csv", comparisons)
    with (output_dir / "statistical_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return report


def _print_primary_results(report: dict[str, object]) -> None:
    print("\nALL-scenario paired seed-level results")
    print("method                              baseline          metric  delta    95% CI              W/T/L   p")
    for row in report["paired_comparisons"]:
        if row["scenario"] != "ALL":
            continue
        print(
            f"{row['method']:<35} {row['baseline']:<17} {row['metric']:<6} "
            f"{row['mean_delta']:+.3f}  "
            f"[{row['ci95_low']:+.3f}, {row['ci95_high']:+.3f}]  "
            f"{row['wins']}/{row['ties']}/{row['losses']}  "
            f"{row['exact_sign_flip_pvalue']:.4f}"
        )


if __name__ == "__main__":
    validation_report = execute()
    _print_primary_results(validation_report)
