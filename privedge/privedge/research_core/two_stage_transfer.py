"""Two-stage transfer from existing top-m LDP releases.

Stage 1 reconstructs each source independently, without target information.
Stage 2 fits simplex source weights to public target context and mixes the
reconstructed sources. Hidden target data never enters either stage.
"""
from dataclasses import dataclass

import numpy as np

from censor_estimator import CensorDesign, build_design, project_simplex, solve
from fusion import ServerRelease, candidate_set


@dataclass(frozen=True)
class SourceReconstruction:
    probabilities: np.ndarray
    converged: bool
    dual_gap: float


@dataclass(frozen=True)
class TargetMixture:
    probabilities: np.ndarray
    weights: np.ndarray
    context_residual: float


def reconstruct_sources(
    releases: list[ServerRelease], domain: int, *, prior_strength: float = 0.1,
    shift_tolerance: float = 0.02, censor_slack: float = 0.0,
    use_censoring: bool = True,
) -> list[SourceReconstruction]:
    """Reconstruct one full-domain distribution per source release.

    The uniform reference makes this stage target-agnostic. It supplies mass
    for unobserved coordinates but is not interpreted as target context.
    """
    if domain < 2 or not releases:
        raise ValueError("need domain >= 2 and at least one release")
    reference = np.ones(domain, dtype=float) / domain
    results = []
    for release in releases:
        estimate = solve(build_design(
            [release], reference, prior_strength=prior_strength,
            shift_tolerance=shift_tolerance, censor_slack=censor_slack,
            use_censoring=use_censoring,
        ))
        results.append(SourceReconstruction(
            estimate.probabilities, estimate.converged, estimate.dual_gap
        ))
    return results


def reconstruct_candidate_tail(
    releases: list[ServerRelease], domain: int, *, prior_strength: float = 0.1,
    use_censoring: bool = True,
) -> list[SourceReconstruction]:
    """Reconstruct the published candidate union plus one aggregate tail mass.

    Published coordinates use point observations weighted by their variances.
    A candidate omitted by a source is constrained only by that source's
    observed top-m threshold. Items outside the union share one tail variable;
    the method does not pretend their individual frequencies are identified.
    """
    if domain < 2 or not releases or prior_strength <= 0:
        raise ValueError("need domain >= 2, releases, and positive prior strength")
    candidates = sorted(candidate_set(releases))
    if not candidates or any(item < 0 or item >= domain for item in candidates):
        raise ValueError("invalid candidate union")
    has_tail = len(candidates) < domain
    reduced_domain = len(candidates) + int(has_tail)
    candidate_index = {item: index for index, item in enumerate(candidates)}
    reference = np.full(reduced_domain, 1.0 / domain)
    if has_tail:
        reference[-1] = (domain - len(candidates)) / domain
    results = []
    for release in releases:
        observations = np.array([release.frequencies[item] for item in release.top_items])
        variances = np.array([release.variances[item] for item in release.top_items])
        if (release.mechanism not in {"GRR", "OUE", "OLH"} or not len(observations)
                or np.any(~np.isfinite(observations)) or np.any(observations < 0)
                or np.any(~np.isfinite(variances)) or np.any(variances <= 0)):
            raise ValueError("candidate-tail reconstruction needs a valid full-domain FO release")
        if np.any(np.diff(observations) > 1e-12):
            raise ValueError("release values must follow decreasing top-items order")
        threshold = float(observations.min())
        missing_variance = max(float(np.median(variances)), 1e-8)
        lower = np.zeros((1, reduced_domain))
        upper = np.ones((1, reduced_domain))
        precision = np.zeros((1, reduced_domain))
        upper[0, :len(candidates)] = threshold
        precision[0, :len(candidates)] = 1.0 / missing_variance
        for item, observation, variance in zip(release.top_items, observations, variances):
            index = candidate_index[item]
            lower[0, index] = observation if observation > 0 else 0.0
            upper[0, index] = observation
            precision[0, index] = 1.0 / max(float(variance), 1e-8)
        active = precision > 0
        precision[active] = np.clip(
            precision[active] / np.median(precision[active]), 0.1, 10.0
        )
        if not use_censoring:
            for item in candidates:
                if item not in release.frequencies:
                    precision[0, candidate_index[item]] = 0.0
        estimate = solve(CensorDesign(reference, lower, upper, precision, prior_strength))
        expanded = np.zeros(domain)
        expanded[candidates] = estimate.probabilities[:len(candidates)]
        if has_tail:
            outside = np.ones(domain, dtype=bool)
            outside[candidates] = False
            expanded[outside] = estimate.probabilities[-1] / outside.sum()
        results.append(SourceReconstruction(expanded, estimate.converged, estimate.dual_gap))
    return results


def zero_filled_sources(releases: list[ServerRelease], domain: int) -> np.ndarray:
    """Expose the implicit source vectors used by direct averaging."""
    vectors = np.zeros((len(releases), domain), dtype=float)
    for row, release in enumerate(releases):
        for item, value in release.frequencies.items():
            vectors[row, item] = max(0.0, float(value))
    return vectors


def equal_mix(source_probabilities: np.ndarray) -> np.ndarray:
    values = np.asarray(source_probabilities, dtype=float)
    if values.ndim != 2 or not len(values):
        raise ValueError("source_probabilities must be a nonempty matrix")
    result = values.mean(axis=0)
    return result / result.sum() if result.sum() > 0 else np.ones(values.shape[1]) / values.shape[1]


def fit_target_mixture(
    source_probabilities: np.ndarray, public_target_context: np.ndarray, *,
    ridge: float = 0.1, iterations: int = 2000, tolerance: float = 1e-12,
) -> TargetMixture:
    """Fit conservative source weights using public context only.

    Minimizes ||sum_s alpha_s p_s - q||^2 / 2 +
    ridge * ||alpha - uniform||^2 / 2 over the source simplex.
    """
    sources = np.asarray(source_probabilities, dtype=float)
    context = np.asarray(public_target_context, dtype=float)
    if sources.ndim != 2 or not len(sources) or context.shape != (sources.shape[1],):
        raise ValueError("incompatible source matrix and target context")
    if ridge < 0 or iterations < 1 or tolerance <= 0:
        raise ValueError("invalid optimization parameters")
    if not np.all(np.isfinite(sources)) or not np.all(np.isfinite(context)) or np.any(context < 0):
        raise ValueError("inputs must be finite and context nonnegative")
    if context.sum() <= 0:
        raise ValueError("target context must have positive mass")
    normalized = np.maximum(sources, 0.0)
    row_sums = normalized.sum(axis=1, keepdims=True)
    normalized = np.divide(normalized, row_sums, out=np.zeros_like(normalized), where=row_sums > 0)
    context = context / context.sum()
    count = len(normalized)
    anchor = np.ones(count) / count
    weights = anchor.copy()
    gram = normalized @ normalized.T
    linear = normalized @ context
    lipschitz = max(float(np.linalg.eigvalsh(gram).max()) + ridge, 1e-12)
    for _ in range(iterations):
        gradient = gram @ weights - linear + ridge * (weights - anchor)
        updated = project_simplex(weights - gradient / lipschitz)
        if np.linalg.norm(updated - weights) <= tolerance:
            weights = updated
            break
        weights = updated
    probabilities = weights @ normalized
    return TargetMixture(probabilities, weights, float(np.linalg.norm(probabilities-context)))


def candidate_tail_features(
    distributions: np.ndarray, releases: list[ServerRelease]
) -> np.ndarray:
    """Compress distributions to candidate coordinates plus aggregate tail."""
    values = np.asarray(distributions, dtype=float)
    if values.ndim == 1:
        values = values[None, :]
    if values.ndim != 2:
        raise ValueError("distributions must be a vector or matrix")
    candidates = np.array(sorted(candidate_set(releases)), dtype=int)
    if not len(candidates) or np.any(candidates >= values.shape[1]):
        raise ValueError("candidate indices incompatible with distributions")
    outside = np.ones(values.shape[1], dtype=bool)
    outside[candidates] = False
    features = values[:, candidates]
    if np.any(outside):
        features = np.column_stack([features, values[:, outside].sum(axis=1)])
    return features


def fit_candidate_target_mixture(
    source_probabilities: np.ndarray, public_target_context: np.ndarray,
    releases: list[ServerRelease], **parameters,
) -> TargetMixture:
    """Fit weights in identifiable candidate-plus-tail feature space."""
    sources = np.asarray(source_probabilities, dtype=float)
    compressed_sources = candidate_tail_features(sources, releases)
    compressed_context = candidate_tail_features(public_target_context, releases)[0]
    fitted = fit_target_mixture(compressed_sources, compressed_context, **parameters)
    normalized = np.maximum(sources, 0.0)
    row_sums = normalized.sum(axis=1, keepdims=True)
    normalized = np.divide(normalized, row_sums, out=np.zeros_like(normalized), where=row_sums > 0)
    probabilities = fitted.weights @ normalized
    context = np.maximum(np.asarray(public_target_context, dtype=float), 0.0)
    context /= context.sum()
    return TargetMixture(probabilities, fitted.weights,
                         float(np.linalg.norm(candidate_tail_features(probabilities, releases)[0]
                                              - compressed_context / compressed_context.sum())))


def candidate_top_k(probabilities: np.ndarray, releases: list[ServerRelease], k: int) -> list[int]:
    candidates = np.array(sorted(candidate_set(releases)), dtype=int)
    if k < 1 or len(candidates) < k:
        raise ValueError("candidate union must contain at least k items")
    return candidates[np.argsort(-np.asarray(probabilities)[candidates], kind="stable")[:k]].tolist()
