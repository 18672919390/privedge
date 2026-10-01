"""Public-release source selection after all summaries have been acquired.

Greedy maximizes a monotone submodular coverage surrogate, NOT target recall
or a calibrated reduction in estimation error. No additional user sampling.
"""

from dataclasses import dataclass
import numpy as np

from fusion import ServerRelease, public_context_relevance, release_uncertainty


@dataclass(frozen=True)
class SelectionResult:
    source_ids: tuple[int, ...]
    marginal_gains: tuple[float, ...]
    coverage_utility: float


def coverage_features(releases: list[ServerRelease], context: np.ndarray) -> tuple[list[ServerRelease], np.ndarray, np.ndarray]:
    q = np.asarray(context, dtype=float).copy()
    if q.ndim != 1 or len(q) < 2 or not np.all(np.isfinite(q)) or np.any(q < 0) or q.sum() <= 0:
        raise ValueError("a finite nonnegative nonzero public context is required")
    if not releases or len({r.server_id for r in releases}) != len(releases):
        raise ValueError("nonempty releases with unique source IDs required")
    q /= q.sum()
    ordered = sorted(releases, key=lambda r: r.server_id)
    for r in ordered:
        if not r.top_items or len(set(r.top_items)) != len(r.top_items) or any(i < 0 or i >= len(q) for i in r.top_items):
            raise ValueError("invalid published items")
        if set(r.variances) != set(r.top_items) or any(not np.isfinite(v) or v <= 0 for v in r.variances.values()):
            raise ValueError("positive finite published variances required")
    uncertainty = np.array([release_uncertainty(r) for r in ordered])
    reliability = np.minimum(1.0, np.median(uncertainty) / np.maximum(uncertainty, 1e-12))
    features = np.zeros((len(ordered), len(q)))
    for s, r in enumerate(ordered):
        features[s, list(r.top_items)] = reliability[s] / np.log2(np.arange(len(r.top_items)) + 2)
    return ordered, q, features


def select_sources(releases: list[ServerRelease], context: np.ndarray, budget: int, *, strategy: str = "coverage", seed: int = 0) -> SelectionResult:
    ordered, q, features = coverage_features(releases, context)
    if not isinstance(budget, (int, np.integer)) or not 1 <= budget <= len(ordered):
        raise ValueError("budget must be an integer in [1, number of sources]")
    if strategy not in {"coverage", "relevance", "random"}:
        raise ValueError("unknown selection strategy")
    if strategy == "relevance":
        utility = np.array([public_context_relevance(r, q, len(r.top_items)) / max(release_uncertainty(r), 1e-12) for r in ordered])
        predetermined = np.argsort(-utility, kind="stable")[:budget].tolist()
    elif strategy == "random":
        predetermined = np.random.default_rng(seed).permutation(len(ordered))[:budget].tolist()
    selected, gains = [], []
    covered = np.zeros(len(q))
    for step in range(budget):
        if strategy == "coverage":
            increments = (np.maximum(features, covered) - covered) @ q
            increments[selected] = -np.inf
            index = int(np.argmax(increments))
        else:
            index = int(predetermined[step])
        improved = np.maximum(covered, features[index])
        gains.append(float((improved - covered) @ q))
        covered = improved
        selected.append(index)
    return SelectionResult(tuple(ordered[i].server_id for i in selected), tuple(gains), float(covered @ q))
