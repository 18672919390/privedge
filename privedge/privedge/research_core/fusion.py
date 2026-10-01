"""Candidate-only multi-server fusion methods."""

from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class ServerRelease:
    server_id: int
    mechanism: str
    top_items: tuple[int, ...]
    frequencies: dict[int, float]
    variances: dict[int, float]


def candidate_set(releases: list[ServerRelease]) -> set[int]:
    return {item for release in releases for item in release.top_items}


def context_augmented_candidate_set(
    releases: list[ServerRelease],
    public_context: np.ndarray,
    top_r: int,
) -> set[int]:
    """Add public-context candidates without inventing an LDP observation."""
    candidates = candidate_set(releases)
    if top_r <= 0:
        return candidates
    context = np.asarray(public_context, dtype=float)
    if context.ndim != 1 or not np.all(np.isfinite(context)):
        raise ValueError("public_context must be a finite one-dimensional vector")
    positive_items = np.flatnonzero(context > 0.0)
    ordered = positive_items[np.argsort(-context[positive_items], kind="stable")]
    candidates.update(int(item) for item in ordered[:top_r])
    return candidates


def _rank_vector(items: tuple[int, ...], domain: int) -> np.ndarray:
    vector = np.zeros(domain, dtype=float)
    for rank, item in enumerate(items):
        vector[item] = 1.0 / math.log2(rank + 2.0)
    return vector


def public_context_relevance(
    release: ServerRelease, public_context: np.ndarray, report_k: int
) -> float:
    ordered_items = np.argsort(-public_context, kind="stable")
    # A zero in sparse public context means "not published", not low rank.
    # Excluding it prevents item IDs from becoming artificial tie breakers.
    context_items = tuple(
        int(item) for item in ordered_items if public_context[item] > 0
    )[:report_k]
    server_vector = _rank_vector(release.top_items, len(public_context))
    context_vector = _rank_vector(context_items, len(public_context))
    denominator = np.linalg.norm(server_vector) * np.linalg.norm(context_vector)
    return float(np.dot(server_vector, context_vector) / denominator) if denominator else 0.0


def release_uncertainty(release: ServerRelease) -> float:
    values = [release.variances[item] for item in release.top_items]
    return float(np.sqrt(np.mean(values))) if values else float("inf")


def item_context_relevance(
    release: ServerRelease, item: int, public_context: np.ndarray
) -> float:
    """Public target-context relevance for one published item."""
    if item not in release.frequencies:
        return 0.0
    context_max = float(np.max(public_context)) if len(public_context) else 0.0
    context_mass = float(public_context[item]) / context_max if context_max > 0 else 0.0
    source_rank = release.top_items.index(item)
    rank_score = 1.0 / math.log2(source_rank + 2.0)
    return max(0.0, min(1.0, context_mass * rank_score))


def _top(scores: dict[int, float], k: int) -> list[int]:
    return [item for item, _ in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))[:k]]


def fuse_vote(releases: list[ServerRelease], k: int) -> list[int]:
    votes: dict[int, float] = {}
    tie_break: dict[int, float] = {}
    for release in releases:
        for rank, item in enumerate(release.top_items):
            votes[item] = votes.get(item, 0.0) + 1.0
            tie_break[item] = tie_break.get(item, 0.0) + 1.0 / (rank + 1.0)
    scores = {item: votes[item] + 1e-6 * tie_break[item] for item in votes}
    return _top(scores, k)


def fuse_average(releases: list[ServerRelease], k: int) -> list[int]:
    scores = {
        item: float(np.mean([release.frequencies.get(item, 0.0) for release in releases]))
        for item in candidate_set(releases)
    }
    return _top(scores, k)


def _weighted_fusion(releases: list[ServerRelease], weights: np.ndarray, k: int) -> list[int]:
    weights = np.maximum(np.asarray(weights, dtype=float), 0.0)
    if weights.sum() == 0:
        weights = np.ones(len(releases), dtype=float)
    weights /= weights.sum()
    scores = {
        item: sum(weight * release.frequencies.get(item, 0.0) for weight, release in zip(weights, releases))
        for item in candidate_set(releases)
    }
    return _top(scores, k)


def fuse_variance_weighted(releases: list[ServerRelease], k: int) -> list[int]:
    uncertainty = np.asarray([release_uncertainty(r) for r in releases])
    return _weighted_fusion(releases, 1.0 / np.maximum(uncertainty, 1e-12), k)


def fuse_anchor_weighted(
    releases: list[ServerRelease], public_context: np.ndarray, report_k: int, k: int
) -> list[int]:
    relevance = np.asarray([public_context_relevance(r, public_context, report_k) for r in releases])
    uncertainty = np.asarray([release_uncertainty(r) for r in releases])
    weights = relevance / np.maximum(uncertainty, 1e-12)
    return _weighted_fusion(releases, weights, k)


def fuse_adaptive_anchor(
    releases: list[ServerRelease],
    public_context: np.ndarray,
    report_k: int,
    k: int,
    server_budget: int,
) -> list[int]:
    """Select low-error, target-relevant published releases, then fuse them."""
    relevance = np.asarray([public_context_relevance(r, public_context, report_k) for r in releases])
    uncertainty = np.asarray([release_uncertainty(r) for r in releases])
    utility = relevance / np.maximum(uncertainty, 1e-12)
    selected = np.argsort(-utility, kind="stable")[: max(1, min(server_budget, len(releases)))]
    chosen = [releases[int(i)] for i in selected]
    return _weighted_fusion(chosen, utility[selected], k)


def fuse_item_level_anchor(
    releases: list[ServerRelease],
    public_context: np.ndarray,
    k: int,
    beta: float = 2.0,
    variance_floor: float = 1e-8,
) -> list[int]:
    """Fuse candidates with item-specific relevance and uncertainty weights."""
    raw_weights: dict[tuple[int, int], float] = {}
    all_weights: list[float] = []
    for item in candidate_set(releases):
        for release in releases:
            if item not in release.frequencies:
                continue
            relevance = item_context_relevance(release, item, public_context)
            variance = max(release.variances.get(item, variance_floor), variance_floor)
            weight = math.exp(beta * relevance) / math.sqrt(variance)
            raw_weights[(release.server_id, item)] = weight
            all_weights.append(weight)
    # Robust clipping prevents a plug-in variance that is accidentally tiny
    # from dominating all other published releases.
    median_weight = float(np.median(all_weights)) if all_weights else 1.0
    low = median_weight * 0.1
    high = median_weight * 10.0

    scores: dict[int, float] = {}
    for item in candidate_set(releases):
        numerator = 0.0
        denominator = 0.0
        for release in releases:
            if item not in release.frequencies:
                continue
            relevance = item_context_relevance(release, item, public_context)
            variance = max(release.variances.get(item, variance_floor), variance_floor)
            weight = raw_weights[(release.server_id, item)]
            weight = min(high, max(low, weight))
            numerator += weight * release.frequencies[item]
            denominator += weight
        if denominator:
            scores[item] = numerator / denominator
    return _top(scores, k)


def fuse_adaptive_item_anchor(
    releases: list[ServerRelease],
    public_context: np.ndarray,
    k: int,
    server_budget: int,
    beta: float = 2.0,
) -> list[int]:
    """Select useful sources, then apply item-level target-aware fusion."""
    relevance = np.asarray([
        public_context_relevance(release, public_context, len(release.top_items))
        for release in releases
    ])
    uncertainty = np.asarray([release_uncertainty(release) for release in releases])
    utility = relevance / np.maximum(uncertainty, 1e-12)
    selected = np.argsort(-utility, kind="stable")[: max(1, min(server_budget, len(releases)))]
    return fuse_item_level_anchor(
        [releases[int(index)] for index in selected], public_context, k, beta=beta
    )


def _log_standard_normal_cdf(value: float) -> float:
    """Numerically stable log Phi(value), without requiring SciPy."""
    if value < -8.0:
        inverse_square = 1.0 / (value * value)
        correction = max(1e-12, 1.0 - inverse_square + 3.0 * inverse_square**2)
        return (
            -0.5 * value * value
            - math.log(-value)
            - 0.5 * math.log(2.0 * math.pi)
            + math.log(correction)
        )
    cdf = 0.5 * math.erfc(-value / math.sqrt(2.0))
    return math.log(max(cdf, 1e-300))


def _bounded_scalar_minimize(
    objective, lower: float = 0.0, upper: float = 1.0, iterations: int = 64
) -> float:
    """Golden-section minimization for a one-dimensional convex objective."""
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_value = objective(left)
    right_value = objective(right)
    for _ in range(iterations):
        if left_value <= right_value:
            upper = right
            right = left
            right_value = left_value
            left = upper - ratio * (upper - lower)
            left_value = objective(left)
        else:
            lower = left
            left = right
            left_value = right_value
            right = lower + ratio * (upper - lower)
            right_value = objective(right)
    return 0.5 * (lower + upper)


def _release_threshold(release: ServerRelease) -> float:
    """Smallest published estimate, conditioning on the observed top-m list."""
    values = [release.frequencies[item] for item in release.top_items]
    return max(0.0, float(min(values))) if values else 0.0


def _censor_source_weights(
    releases: list[ServerRelease], public_context: np.ndarray, report_k: int
) -> tuple[np.ndarray, np.ndarray]:
    relevance = np.asarray(
        [public_context_relevance(release, public_context, report_k) for release in releases],
        dtype=float,
    )
    uncertainty = np.asarray(
        [release_uncertainty(release) for release in releases], dtype=float
    )
    finite = uncertainty[np.isfinite(uncertainty)]
    median_uncertainty = float(np.median(finite)) if len(finite) else 1.0
    uncertainty = np.maximum(uncertainty, max(1e-8, 0.5 * median_uncertainty))
    utility = np.maximum(relevance, 1e-3) / uncertainty
    if len(utility):
        utility = np.minimum(utility, 3.0 * max(float(np.median(utility)), 1e-12))
    if not len(utility) or utility.sum() <= 0:
        utility = np.ones(len(releases), dtype=float)
    return utility / utility.sum(), relevance


def fuse_censor_aware_item_context(
    releases: list[ServerRelease],
    public_context: np.ndarray,
    report_k: int,
    k: int,
    server_budget: int | None = None,
    prior_strength: float = 0.10,
    transfer_scale: float = 1.0,
    variance_floor: float = 1e-8,
    candidate_items: set[int] | None = None,
) -> list[int]:
    """Fuse top-m releases with a threshold-censoring likelihood approximation.

    For a reported item, the objective uses its LDP estimate and variance. For
    an unreported item, it uses the event Y <= tau, where tau is the smallest
    published estimate from that source. Public context is a regularizing
    prior, never a target observation. The likelihood conditions on the
    observed, random top-m threshold and is therefore an approximation rather
    than an exact fixed-threshold Tobit likelihood.
    """
    if not releases:
        return []
    if prior_strength < 0 or transfer_scale < 0 or variance_floor <= 0:
        raise ValueError("invalid censor-aware fusion hyperparameters")
    if len(public_context) == 0 or not np.all(np.isfinite(public_context)):
        raise ValueError("public_context must be a finite non-empty vector")

    context = np.maximum(np.asarray(public_context, dtype=float), 0.0)
    context_sum = float(context.sum())
    context = context / context_sum if context_sum > 0 else np.zeros_like(context)
    source_weights, relevance = _censor_source_weights(
        releases, context, report_k
    )

    if server_budget is not None:
        budget = max(1, min(int(server_budget), len(releases)))
        selected_indices = np.argsort(-source_weights, kind="stable")[:budget]
        selected = [releases[int(index)] for index in selected_indices]
        source_weights = source_weights[selected_indices]
        source_weights /= source_weights.sum()
        relevance = relevance[selected_indices]
    else:
        selected = releases

    thresholds = np.asarray([_release_threshold(release) for release in selected])
    release_variances = np.asarray(
        [
            max(
                variance_floor,
                float(np.median(list(release.variances.values())))
                if release.variances
                else variance_floor,
            )
            for release in selected
        ]
    )
    finite_variances = release_variances[np.isfinite(release_variances)]
    median_variance = (
        float(np.median(finite_variances)) if len(finite_variances) else variance_floor
    )
    variance_lower_bound = max(variance_floor, 0.25 * median_variance)
    domain_scale = 1.0 / len(context)
    context_scale = max(
        domain_scale,
        float(np.median(thresholds)) if len(thresholds) else domain_scale,
        math.sqrt(max(median_variance, variance_floor)),
    )

    scores: dict[int, float] = {}
    scoring_candidates = (
        candidate_set(selected) if candidate_items is None else set(candidate_items)
    )
    scoring_candidates = {
        int(item) for item in scoring_candidates if 0 <= int(item) < len(context)
    }
    for item in scoring_candidates:
        prior_mean = float(context[item])

        def objective(theta: float) -> float:
            loss = 0.5 * prior_strength * ((theta - prior_mean) / context_scale) ** 2
            for index, release in enumerate(selected):
                shift_sd = (
                    transfer_scale
                    * (1.0 - relevance[index])
                    * max(domain_scale, thresholds[index])
                )
                if item in release.frequencies:
                    observation = min(1.0, max(0.0, release.frequencies[item]))
                    observation_variance = max(
                        variance_lower_bound,
                        release.variances.get(item, release_variances[index]),
                    ) + shift_sd**2
                    loss += (
                        0.5
                        * source_weights[index]
                        * (theta - observation) ** 2
                        / observation_variance
                    )
                else:
                    censor_variance = max(
                        variance_lower_bound, release_variances[index]
                    ) + shift_sd**2
                    standardized = (thresholds[index] - theta) / math.sqrt(
                        censor_variance
                    )
                    loss -= source_weights[index] * _log_standard_normal_cdf(
                        standardized
                    )
            return loss

        scores[item] = _bounded_scalar_minimize(objective)
    return _top(scores, k)


def release_consensus(release: ServerRelease, releases: list[ServerRelease]) -> float:
    """Average Jaccard agreement with other published candidate lists."""
    own = set(release.top_items)
    agreements: list[float] = []
    for other in releases:
        if other.server_id == release.server_id:
            continue
        theirs = set(other.top_items)
        union = own | theirs
        agreements.append(len(own & theirs) / len(union) if union else 0.0)
    return float(np.mean(agreements)) if agreements else 1.0


def fuse_robust_adaptive_context(
    releases: list[ServerRelease],
    public_context: np.ndarray,
    report_k: int,
    k: int,
    server_budget: int,
) -> list[int]:
    """Context-aware source selection robust to isolated abnormal releases.

    A source must agree with both public context and peer releases. Claimed
    uncertainty is floored by the population median and final utilities are
    clipped, limiting a maliciously tiny variance from dominating fusion.
    """
    relevance = np.asarray(
        [public_context_relevance(release, public_context, report_k) for release in releases]
    )
    consensus = np.asarray([release_consensus(release, releases) for release in releases])
    uncertainty = np.asarray([release_uncertainty(release) for release in releases])
    finite = uncertainty[np.isfinite(uncertainty)]
    median_uncertainty = float(np.median(finite)) if len(finite) else 1.0
    effective_uncertainty = np.maximum(uncertainty, 0.5 * median_uncertainty)
    utility = (0.65 * relevance + 0.35 * consensus) / np.maximum(
        effective_uncertainty, 1e-12
    )
    if len(utility):
        utility = np.minimum(utility, 3.0 * max(float(np.median(utility)), 1e-12))
    selected = np.argsort(-utility, kind="stable")[: max(1, min(server_budget, len(releases)))]
    chosen = [releases[int(index)] for index in selected]
    return _weighted_fusion(chosen, utility[selected], k)


# Compatibility aliases for earlier notebooks/scripts. New papers and code
# should use public_context terminology.
anchor_relevance = public_context_relevance
item_anchor_relevance = item_context_relevance
fuse_public_context_weighted = fuse_anchor_weighted
fuse_adaptive_public_context = fuse_adaptive_anchor
fuse_item_level_context = fuse_item_level_anchor
fuse_adaptive_item_context = fuse_adaptive_item_anchor


def fuse_oracle(
    releases: list[ServerRelease], true_similarities: np.ndarray, k: int
) -> list[int]:
    """Simulation-only true-similarity diagnostic; never deployable."""
    return _weighted_fusion(releases, true_similarities, k)
