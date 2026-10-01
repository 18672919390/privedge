"""Convex interval/censor surrogate on the full probability simplex.

This is not a Gaussian selection likelihood. Tolerances are declared modeling
parameters, not confidence bounds. Only published releases and public q enter.
See CENSOR_ESTIMATOR_V2.md for objective, certificates and limitations.
"""

from dataclasses import dataclass
import numpy as np

from fusion import ServerRelease


@dataclass(frozen=True)
class CensorDesign:
    q: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    precision: np.ndarray
    prior_strength: float


@dataclass(frozen=True)
class CensorEstimate:
    probabilities: np.ndarray
    objective: float
    dual_gap: float
    optimization_l2_bound: float
    iterations: int
    converged: bool

    def top_k(self, k: int, candidates: set[int] | None = None) -> list[int]:
        items = np.arange(len(self.probabilities)) if candidates is None else np.array(sorted(candidates), dtype=int)
        if k < 1 or k > len(items) or np.any(items < 0) or np.any(items >= len(self.probabilities)):
            raise ValueError("invalid k or candidates")
        return items[np.argsort(-self.probabilities[items], kind="stable")[:k]].tolist()


def project_simplex(values: np.ndarray) -> np.ndarray:
    """Euclidean projection onto {x >= 0, sum x = 1}."""
    ordered = np.sort(values)[::-1]
    excess = np.cumsum(ordered) - 1.0
    indices = np.arange(1, len(values) + 1)
    rho = np.flatnonzero(ordered - excess / indices > 0)[-1]
    return np.maximum(values - excess[rho] / (rho + 1), 0.0)


def build_design(
    releases: list[ServerRelease], public_context: np.ndarray, *,
    prior_strength: float = 1.0, shift_tolerance: float = 0.02,
    censor_slack: float = 0.0, use_censoring: bool = True,
) -> CensorDesign:
    """Freeze public, data-dependent coefficients before convex optimization.

    Each source's median published variance proxies its missing-item variance.
    Precision is normalized to median 1 to make regularization explicit and
    dimensionless; it is not an inverse exact covariance matrix.
    """
    q = np.asarray(public_context, dtype=float).copy()
    parameters = np.array([prior_strength, shift_tolerance, censor_slack])
    if q.ndim != 1 or len(q) < 2 or not np.all(np.isfinite(q)) or np.any(q < 0) or q.sum() <= 0:
        raise ValueError("public_context must be finite, nonnegative and nonzero")
    if not np.all(np.isfinite(parameters)) or prior_strength <= 0 or min(shift_tolerance, censor_slack) < 0:
        raise ValueError("positive prior strength and nonnegative finite tolerances required")
    if not releases:
        raise ValueError("at least one release required")
    q /= q.sum()
    domain = len(q)
    lower = np.zeros((len(releases), domain))
    upper = np.ones_like(lower)
    precision = np.zeros_like(lower)
    seen = set()
    for s, release in enumerate(releases):
        if release.mechanism not in {"GRR", "OUE", "OLH"}:
            raise ValueError("Only honest full-domain GRR/OUE/OLH releases supported; PEM excluded")
        items = release.top_items
        if release.server_id in seen or not items or len(set(items)) != len(items):
            raise ValueError("unique source IDs and nonempty unique release items required")
        seen.add(release.server_id)
        if any(i < 0 or i >= domain for i in items) or set(items) != set(release.frequencies) or set(items) != set(release.variances):
            raise ValueError("release keys must match in-domain published items")
        y = np.array([release.frequencies[i] for i in items])
        v = np.array([release.variances[i] for i in items])
        if not np.all(np.isfinite(y)) or np.any(y < 0) or not np.all(np.isfinite(v)) or np.any(v <= 0):
            raise ValueError("finite nonnegative frequencies and positive variances required")
        if np.any(np.diff(y) > 1e-12):
            raise ValueError("release must be ordered by decreasing published frequency")
        upper[s, :] = y.min() + shift_tolerance + censor_slack
        precision[s, :] = 1.0 / max(float(np.median(v)), 1e-8)
        for item, observation, variance in zip(items, y, v):
            # A clipped zero is an upper event, not an exact Gaussian observation.
            lower[s, item] = max(0.0, observation - shift_tolerance) if observation > 0 else 0.0
            upper[s, item] = observation + shift_tolerance
            precision[s, item] = 1.0 / max(float(variance), 1e-8)
    active = precision > 0
    precision[active] = np.clip(precision[active] / np.median(precision[active]), 0.1, 10.0)
    precision /= len(releases)
    if not use_censoring:
        # Freeze identical weights for a genuine missing-term-only ablation.
        for s, release in enumerate(releases):
            missing = np.ones(domain, dtype=bool)
            missing[list(release.top_items)] = False
            precision[s, missing] = 0.0
    return CensorDesign(q, lower, upper, precision, prior_strength)


def value_gradient(theta: np.ndarray, design: CensorDesign) -> tuple[float, np.ndarray]:
    """Squared distance to observed intervals plus strongly convex prior."""
    residual = np.maximum(theta - design.upper, 0.0) + np.minimum(theta - design.lower, 0.0)
    difference = theta - design.q
    value = 0.5 * float(np.sum(design.precision * residual**2))
    value += 0.5 * design.prior_strength * float(difference @ difference)
    gradient = np.sum(design.precision * residual, axis=0) + design.prior_strength * difference
    return value, gradient


def solve(design: CensorDesign, *, tolerance: float = 1e-10, max_iterations: int = 20000) -> CensorEstimate:
    if not np.isfinite(tolerance) or tolerance <= 0 or max_iterations < 1:
        raise ValueError("positive tolerance and iteration budget required")
    theta = design.q.copy()
    lipschitz = design.prior_strength + float(np.max(design.precision.sum(axis=0)))
    for iteration in range(max_iterations + 1):
        value, gradient = value_gradient(theta, design)
        # max_z <grad,theta-z> over the simplex; bounds primal suboptimality.
        gap = max(0.0, float(gradient @ theta - gradient.min()))
        if gap <= tolerance or iteration == max_iterations:
            return CensorEstimate(theta, value, gap,
                                  float(np.sqrt(2 * gap / design.prior_strength)),
                                  iteration, gap <= tolerance)
        theta = project_simplex(theta - gradient / lipschitz)
    raise AssertionError("unreachable")


def estimate(releases: list[ServerRelease], public_context: np.ndarray, **parameters) -> CensorEstimate:
    return solve(build_design(releases, public_context, **parameters))
