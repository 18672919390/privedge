"""Calibrate LDP frequency-estimator variances.

The calibration keeps one sampled user dataset fixed within a condition and
repeats only the randomized reporting step.  This estimates conditional
mechanism variance, which is the quantity consumed by the fusion modules.
PEM is reported separately because its prefix search and top-k selection make
the returned variance conditional on an item being released.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ldp_protocols import estimate_frequency
from pem import pem


DOMAIN = 64
USER_COUNTS = (500, 1500)
EPSILONS = (1.0, 2.0, 4.0)
REPETITIONS = 20
TOP_K = 10
CALIBRATION_SEED = 20260911
Z95 = 1.959963984540054
MECHANISMS = ("GRR", "OUE", "OLH", "PEM")


def _distributions(domain: int) -> dict[str, np.ndarray]:
    uniform = np.full(domain, 1.0 / domain)
    ranks = np.arange(1, domain + 1, dtype=float)
    zipf = ranks ** -0.9
    zipf /= zipf.sum()
    rare = np.full(domain, 0.2 / (domain - 1))
    rare[0] = 0.8
    return {"uniform": uniform, "zipf": zipf, "dominant": rare}


def _theoretical_variance(
    mechanism: str, true_counts: np.ndarray, n: int, epsilon: float
) -> np.ndarray:
    """Conditional count-estimator variance under the protocol p/q model."""
    if mechanism == "GRR":
        ee = np.exp(epsilon)
        p = ee / (ee + DOMAIN - 1)
        q = 1.0 / (ee + DOMAIN - 1)
    elif mechanism == "OUE":
        p = 0.5
        q = 1.0 / (np.exp(epsilon) + 1.0)
    elif mechanism == "OLH":
        g = int(round(float(np.exp(epsilon)))) + 1
        p = np.exp(epsilon) / (np.exp(epsilon) + g - 1)
        q = 1.0 / g
    else:
        return np.full(DOMAIN, np.nan)
    numerator = true_counts * p * (1.0 - p) + (n - true_counts) * q * (1.0 - q)
    return numerator / (p - q) ** 2


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 1e-12 else float("nan")


def _frequency_condition(
    mechanism: str,
    distribution_name: str,
    distribution: np.ndarray,
    n: int,
    epsilon: float,
    repetitions: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    """Calibrate GRR/OUE/OLH on one fixed data set."""
    data = rng.choice(DOMAIN, size=n, p=distribution)
    true_counts = np.bincount(data, minlength=DOMAIN).astype(float)
    estimates = []
    plugin_variances = []
    for _ in range(repetitions):
        result = estimate_frequency(
            mechanism, data, DOMAIN, epsilon, rng
        )
        estimates.append(result.counts)
        plugin_variances.append(result.variances)
    estimate_array = np.asarray(estimates, dtype=float)
    plugin_array = np.asarray(plugin_variances, dtype=float)
    empirical_variance = np.var(estimate_array, axis=0, ddof=1)
    plugin_mean = np.mean(plugin_array, axis=0)
    theoretical = _theoretical_variance(mechanism, true_counts, n, epsilon)
    error = estimate_array - true_counts[None, :]
    intervals_cover = np.abs(error) <= Z95 * np.sqrt(np.maximum(plugin_array, 1e-12))
    return {
        "protocol": mechanism,
        "distribution": distribution_name,
        "domain": DOMAIN,
        "users": n,
        "epsilon": epsilon,
        "repetitions": repetitions,
        "mean_abs_bias_count": float(np.mean(np.abs(np.mean(error, axis=0)))),
        "rmse_count": float(np.sqrt(np.mean(error**2))),
        "empirical_variance_count_mean": float(np.mean(empirical_variance)),
        "theoretical_variance_count_mean": float(np.mean(theoretical)),
        "plugin_variance_count_mean": float(np.mean(plugin_mean)),
        "plugin_to_empirical_variance_ratio": _safe_ratio(
            float(np.mean(plugin_mean)), float(np.mean(empirical_variance))
        ),
        "empirical_to_theoretical_variance_ratio": _safe_ratio(
            float(np.mean(empirical_variance)), float(np.mean(theoretical))
        ),
        "plugin_to_theoretical_variance_ratio": _safe_ratio(
            float(np.mean(plugin_mean)), float(np.mean(theoretical))
        ),
        "nominal_95_coverage": float(np.mean(intervals_cover)),
        "itemwise_ratio_median": float(
            np.nanmedian(
                np.divide(
                    plugin_mean,
                    empirical_variance,
                    out=np.full(DOMAIN, np.nan),
                    where=empirical_variance > 1e-12,
                )
            )
        ),
    }


def _pem_condition(
    distribution_name: str,
    distribution: np.ndarray,
    n: int,
    epsilon: float,
    repetitions: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    """Calibrate PEM only on item/repetition pairs that PEM releases."""
    data = rng.choice(DOMAIN, size=n, p=distribution)
    true_counts = np.bincount(data, minlength=DOMAIN).astype(float)
    observations: dict[int, list[float]] = {item: [] for item in range(DOMAIN)}
    variances: dict[int, list[float]] = {item: [] for item in range(DOMAIN)}
    selected = np.zeros(DOMAIN, dtype=float)
    for _ in range(repetitions):
        result = pem(data, DOMAIN, TOP_K, epsilon, rng)
        for item, count, variance in zip(result.items, result.counts, result.variances):
            item_id = int(item)
            selected[item_id] += 1.0
            observations[item_id].append(float(count))
            variances[item_id].append(float(variance))
    item_records = []
    for item in range(DOMAIN):
        if len(observations[item]) < 2:
            continue
        values = np.asarray(observations[item])
        item_variances = np.asarray(variances[item])
        errors = values - true_counts[item]
        item_records.append(
            {
                "empirical_variance": float(np.var(values, ddof=1)),
                "plugin_variance": float(np.mean(item_variances)),
                "coverage": float(
                    np.mean(np.abs(errors) <= Z95 * np.sqrt(np.maximum(item_variances, 1e-12)))
                ),
                "abs_bias": float(abs(np.mean(errors))),
                "rmse": float(np.sqrt(np.mean(errors**2))),
            }
        )
    if not item_records:
        raise RuntimeError("PEM selected no item often enough for calibration")
    empirical = np.asarray([record["empirical_variance"] for record in item_records])
    plugin = np.asarray([record["plugin_variance"] for record in item_records])
    return {
        "protocol": "PEM",
        "distribution": distribution_name,
        "domain": DOMAIN,
        "users": n,
        "epsilon": epsilon,
        "repetitions": repetitions,
        "calibration_scope": "released-item conditional",
        "mean_abs_bias_count": float(np.mean([record["abs_bias"] for record in item_records])),
        "rmse_count": float(np.mean([record["rmse"] for record in item_records])),
        "empirical_variance_count_mean": float(np.mean(empirical)),
        "theoretical_variance_count_mean": None,
        "plugin_variance_count_mean": float(np.mean(plugin)),
        "plugin_to_empirical_variance_ratio": _safe_ratio(
            float(np.mean(plugin)), float(np.mean(empirical))
        ),
        "empirical_to_theoretical_variance_ratio": None,
        "plugin_to_theoretical_variance_ratio": None,
        "nominal_95_coverage": float(np.mean([record["coverage"] for record in item_records])),
        "itemwise_ratio_median": float(
            np.nanmedian(
                np.divide(
                    plugin,
                    empirical,
                    out=np.full_like(plugin, np.nan),
                    where=empirical > 1e-12,
                )
            )
        ),
        "mean_item_selection_rate": float(np.mean(selected / repetitions)),
        "items_with_two_or_more_releases": len(item_records),
    }


def run_calibration(
    repetitions: int = REPETITIONS,
    user_counts: tuple[int, ...] = USER_COUNTS,
    epsilons: tuple[float, ...] = EPSILONS,
    mechanisms: tuple[str, ...] = MECHANISMS,
    seed: int = CALIBRATION_SEED,
) -> list[dict[str, object]]:
    if repetitions < 3:
        raise ValueError("at least three repetitions are required")
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for distribution_name, distribution in _distributions(DOMAIN).items():
        for users in user_counts:
            for epsilon in epsilons:
                for mechanism in mechanisms:
                    if mechanism == "PEM":
                        row = _pem_condition(
                            distribution_name, distribution, users, epsilon, repetitions, rng
                        )
                    else:
                        row = _frequency_condition(
                            mechanism, distribution_name, distribution, users, epsilon, repetitions, rng
                        )
                    rows.append(row)
    return rows


def write_calibration(rows: list[dict[str, object]], output_root: str = "outputs") -> Path:
    output_dir = Path(output_root) / "ldp_variance_calibration"
    output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with (output_dir / "calibration_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "design": {
            "domain": DOMAIN,
            "user_counts": list(USER_COUNTS),
            "epsilons": list(EPSILONS),
            "repetitions_per_condition": REPETITIONS,
            "distributions": list(_distributions(DOMAIN)),
            "mechanisms": list(MECHANISMS),
            "seed": CALIBRATION_SEED,
            "fixed_data_within_condition": True,
            "interval": "estimate +/- 1.95996 * sqrt(reported variance)",
        },
        "interpretation": (
            "GRR/OUE/OLH compare conditional empirical randomized-report variance "
            "with the p/q theoretical variance and plug-in variance. PEM is a "
            "released-item conditional diagnostic because prefix search and top-k "
            "selection make an all-item variance comparison invalid. These are "
            "calibration diagnostics, not target utility results."
        ),
        "rows": rows,
    }
    with (output_dir / "calibration_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=True)
    return output_dir


if __name__ == "__main__":
    calibration_rows = run_calibration()
    output_dir = write_calibration(calibration_rows)
    print(f"wrote {len(calibration_rows)} calibration conditions to {output_dir.resolve()}")
