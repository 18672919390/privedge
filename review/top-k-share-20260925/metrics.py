"""Top-k evaluation metrics used in the experiment notes."""

from __future__ import annotations

import math
import numpy as np


def top_items(distribution: np.ndarray, k: int) -> list[int]:
    return np.argsort(-distribution, kind="stable")[:k].astype(int).tolist()


def precision_recall(truth: list[int], prediction: list[int]) -> tuple[float, float]:
    hits = len(set(truth).intersection(prediction))
    precision = hits / len(prediction) if prediction else 0.0
    recall = hits / len(truth) if truth else 0.0
    return precision, recall


def coverage(truth: list[int], candidates: set[int]) -> float:
    return len(set(truth).intersection(candidates)) / len(truth) if truth else 0.0


def candidate_recall_upper_bound(truth: list[int], candidates: set[int]) -> float:
    """Hard upper bound on candidate-only top-k recall."""
    return coverage(truth, candidates)


def candidate_miss_mass(target: np.ndarray, candidates: set[int]) -> float:
    """Target probability mass outside the candidate set."""
    return float(np.sum([mass for item, mass in enumerate(target) if item not in candidates]))


def migration_error(target: np.ndarray, sources: list[np.ndarray]) -> dict[str, float]:
    """Distribution-shift diagnostics between source and target populations."""
    if not sources:
        return {"source_target_tv_mean": 0.0, "source_target_tv_best": 0.0, "source_mean_bias_l1": 0.0}
    distances = np.asarray([0.5 * np.sum(np.abs(source - target)) for source in sources])
    source_mean = np.mean(np.asarray(sources), axis=0)
    return {
        "source_target_tv_mean": float(np.mean(distances)),
        "source_target_tv_best": float(np.min(distances)),
        "source_mean_bias_l1": float(np.sum(np.abs(source_mean - target))),
    }


def ndcg(target: np.ndarray, truth: list[int], prediction: list[int]) -> float:
    def dcg(items: list[int]) -> float:
        return sum(float(target[item]) / math.log2(rank + 2.0) for rank, item in enumerate(items))

    ideal = dcg(truth)
    return dcg(prediction) / ideal if ideal else 0.0


def evaluate(
    target: np.ndarray, truth: list[int], prediction: list[int], candidates: set[int]
) -> dict[str, float]:
    precision, recall = precision_recall(truth, prediction)
    return {
        "precision": precision,
        "recall": recall,
        "coverage": coverage(truth, candidates),
        "ndcg": ndcg(target, truth, prediction),
    }
