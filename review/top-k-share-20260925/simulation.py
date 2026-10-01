"""Synthetic target and related existing-server distributions.

A latent business profile is generated first. The hidden target and public
target context are then sampled independently from that profile.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


CONTEXT_CONDITIONS = (
    "clean",
    "partial",
    "noisy",
    "misleading",
    "outdated",
    "adversarial",
)
SOURCE_CONDITIONS = ("clean", "unrelated", "stale")


@dataclass(frozen=True)
class SyntheticProblem:
    target: np.ndarray
    servers: list[np.ndarray]
    similarities: np.ndarray
    public_target_context: np.ndarray

    @property
    def anchor(self) -> np.ndarray:
        """Backward-compatible alias; use ``public_target_context`` in papers."""
        return self.public_target_context


def _zipf_distribution(domain: int, exponent: float, permutation: np.ndarray) -> np.ndarray:
    ranks = np.arange(1, domain + 1, dtype=float)
    probabilities = ranks ** (-exponent)
    probabilities /= probabilities.sum()
    result = np.empty(domain, dtype=float)
    result[permutation] = probabilities
    return result


def make_problem(
    domain: int,
    server_count: int,
    context_quality: float,
    rng: np.random.Generator,
    context_condition: str = "clean",
    source_condition: str = "clean",
    affected_source_fraction: float = 0.34,
    target_concentration: float = 24.0,
    latent_exponent: float = 0.9,
    source_exponent: float = 1.08,
    source_mix_min: float = 0.15,
    source_mix_max: float = 0.9,
) -> SyntheticProblem:
    if domain < 16 or server_count < 2:
        raise ValueError("use domain >= 16 and at least two existing servers")
    if not 0 <= context_quality <= 1:
        raise ValueError("context_quality must be in [0, 1]")
    if context_condition not in CONTEXT_CONDITIONS:
        raise ValueError(f"unknown context_condition: {context_condition}")
    if source_condition not in SOURCE_CONDITIONS:
        raise ValueError(f"unknown source_condition: {source_condition}")
    if not 0 <= affected_source_fraction <= 1:
        raise ValueError("affected_source_fraction must be in [0, 1]")
    if target_concentration <= 0 or latent_exponent <= 0 or source_exponent <= 0:
        raise ValueError("distribution parameters must be positive")
    if not 0 <= source_mix_min <= source_mix_max <= 1:
        raise ValueError("source mix range must satisfy 0 <= min <= max <= 1")

    # Independent random streams ensure that a context-only ablation does not
    # silently change the target or source populations.
    seeds = rng.integers(0, 2**63 - 1, size=5, dtype=np.int64)
    latent_rng, target_rng, context_rng, source_rng, corruption_rng = (
        np.random.default_rng(int(seed)) for seed in seeds
    )
    latent_business_profile = _zipf_distribution(
        domain, latent_exponent, latent_rng.permutation(domain)
    )
    target = target_rng.dirichlet(target_concentration * latent_business_profile)
    context_strength = 0.5 + 80.0 * context_quality
    context_center = latent_business_profile.copy()
    if context_condition == "outdated":
        old_profile = _zipf_distribution(domain, 0.9, context_rng.permutation(domain))
        context_center = 0.45 * context_center + 0.55 * old_profile
    elif context_condition == "adversarial":
        context_center = np.empty_like(context_center)
        context_center[np.argsort(latent_business_profile)] = np.sort(latent_business_profile)[::-1]

    public_target_context = context_rng.dirichlet(context_strength * context_center)
    if context_condition == "partial":
        # Only a small published subset has context metadata; this must be
        # smaller than the default top-2k list to create a meaningful ablation.
        keep = max(1, domain // 16)
        indices = np.argsort(-public_target_context, kind="stable")[:keep]
        partial = np.zeros(domain, dtype=float)
        partial[indices] = public_target_context[indices]
        public_target_context = partial / partial.sum()
    elif context_condition == "noisy":
        noise = context_rng.dirichlet(np.ones(domain))
        public_target_context = 0.5 * public_target_context + 0.5 * noise
    elif context_condition == "misleading":
        public_target_context = public_target_context[context_rng.permutation(domain)]

    mixing_coefficients = np.linspace(source_mix_max, source_mix_min, server_count)
    servers: list[np.ndarray] = []
    affected_count = (
        max(1, int(round(server_count * affected_source_fraction)))
        if affected_source_fraction > 0
        else 0
    )
    for server_id, coefficient in enumerate(mixing_coefficients):
        unrelated = _zipf_distribution(domain, source_exponent, source_rng.permutation(domain))
        if source_condition == "unrelated" and server_id < affected_count:
            coefficient = 0.0
        distribution = coefficient * target + (1.0 - coefficient) * unrelated
        if source_condition == "stale" and server_id < affected_count:
            stale = _zipf_distribution(domain, source_exponent, corruption_rng.permutation(domain))
            distribution = 0.35 * distribution + 0.65 * stale
        servers.append(distribution / distribution.sum())

    # True similarities are retained only for the oracle diagnostic baseline.
    similarities = np.asarray(
        [1.0 - 0.5 * np.sum(np.abs(source - target)) for source in servers]
    )
    return SyntheticProblem(target, servers, similarities, public_target_context)
