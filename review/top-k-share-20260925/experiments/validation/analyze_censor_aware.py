"""Paired descriptive validation for the censor-aware fusion methods."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

import numpy as np


GROUPS = (
    "G1_protocol_baselines",
    "G2_context_quality",
    "G3_adaptive_ablation",
    "G4_heterogeneous",
    "G5_context_robustness",
    "G6_source_robustness",
    "G7_candidate_release",
)

COMPARISONS = (
    ("censor_aware_item_context", "item_context"),
    ("adaptive_censor_aware_item_context", "adaptive_item_context"),
    ("censor_aware_item_context", "average"),
    ("adaptive_censor_aware_item_context", "adaptive_context"),
)


def _load_rows(output_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for group in GROUPS:
        path = output_root / group / "group_summary.csv"
        if not path.exists():
            raise FileNotFoundError(f"run {group} before validation: {path}")
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _compare(
    rows: Iterable[dict[str, str]], new_method: str, baseline: str
) -> dict[str, object]:
    indexed = {
        (row["group"], row["case"], row["scenario"], row["method"]): row
        for row in rows
    }
    settings = sorted({key[:3] for key in indexed})
    recall_deltas: list[float] = []
    ndcg_deltas: list[float] = []
    recall_wins = recall_ties = recall_losses = 0
    ndcg_wins = ndcg_ties = ndcg_losses = 0
    tolerance = 1e-12
    for setting in settings:
        new = indexed.get((*setting, new_method))
        old = indexed.get((*setting, baseline))
        if new is None or old is None:
            continue
        recall_delta = float(new["recall"]) - float(old["recall"])
        ndcg_delta = float(new["ndcg"]) - float(old["ndcg"])
        recall_deltas.append(recall_delta)
        ndcg_deltas.append(ndcg_delta)
        recall_wins += recall_delta > tolerance
        recall_ties += abs(recall_delta) <= tolerance
        recall_losses += recall_delta < -tolerance
        ndcg_wins += ndcg_delta > tolerance
        ndcg_ties += abs(ndcg_delta) <= tolerance
        ndcg_losses += ndcg_delta < -tolerance
    return {
        "method": new_method,
        "baseline": baseline,
        "paired_settings": len(recall_deltas),
        "recall": {
            "wins": recall_wins,
            "ties": recall_ties,
            "losses": recall_losses,
            "mean_delta": float(np.mean(recall_deltas)),
        },
        "ndcg": {
            "wins": ndcg_wins,
            "ties": ndcg_ties,
            "losses": ndcg_losses,
            "mean_delta": float(np.mean(ndcg_deltas)),
        },
    }


def run(output_root: str = "outputs") -> list[dict[str, object]]:
    root = Path(output_root)
    rows = _load_rows(root)
    report = [_compare(rows, method, baseline) for method, baseline in COMPARISONS]
    payload = {
        "scope": list(GROUPS),
        "rounds_per_case_max": 3,
        "interpretation": (
            "Descriptive paired comparisons over configured cases. Cases share "
            "seeds and some configurations, so counts are not independent "
            "hypothesis tests or publication-grade significance evidence."
        ),
        "comparisons": report,
    }
    output_path = root / "censor_aware_validation.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return report


if __name__ == "__main__":
    for result in run():
        recall = result["recall"]
        ndcg = result["ndcg"]
        print(
            f"{result['method']} vs {result['baseline']}: "
            f"recall {recall['wins']}/{recall['ties']}/{recall['losses']} "
            f"delta={recall['mean_delta']:+.3f}; "
            f"ndcg {ndcg['wins']}/{ndcg['ties']}/{ndcg['losses']} "
            f"delta={ndcg['mean_delta']:+.3f}"
        )
