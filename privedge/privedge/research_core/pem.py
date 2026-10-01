"""Prefix Extending Method (PEM), adapted from LDP_Protocols/pem.

The original implementation splits users into disjoint groups, expands a
prefix/suffix candidate set one bit at a time, invokes local hashing, and keeps
the k largest estimates. This port retains that design while repairing the
missing ``self.args`` state, deprecated NumPy integer aliases, and candidate
initialization so it runs on current Python.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ldp_protocols import olh


@dataclass(frozen=True)
class PEMEstimate:
    items: np.ndarray
    counts: np.ndarray
    variances: np.ndarray
    mechanism: str = "PEM"


def pem(
    data: np.ndarray,
    domain: int,
    top_k: int,
    epsilon: float,
    rng: np.random.Generator,
    step_bits: int = 1,
) -> PEMEstimate:
    values = np.asarray(data, dtype=np.int64)
    if len(values) == 0:
        raise ValueError("PEM needs at least one user")
    if domain < 2 or np.any(values < 0) or np.any(values >= domain):
        raise ValueError("data must be in [0, domain)")
    if top_k < 1 or epsilon <= 0 or step_bits < 1:
        raise ValueError("top_k, epsilon, and step_bits must be positive")

    n_bits = max(1, int(math.ceil(math.log2(domain))))
    keep = min(top_k, domain)
    first_bits = min(n_bits, int(math.log2(keep)) + 1)
    iterations = 1 + int(math.ceil(max(0, n_bits - first_bits) / step_bits))

    shuffled = values[rng.permutation(len(values))]
    groups = np.array_split(shuffled, iterations)
    candidates = np.arange(1 << first_bits, dtype=np.int64)
    candidates = candidates[candidates < domain]

    final_counts = np.zeros(len(candidates), dtype=float)
    final_variances = np.ones(len(candidates), dtype=float)
    known_bits = first_bits

    for iteration, group in enumerate(groups):
        if iteration > 0:
            add_bits = min(step_bits, n_bits - known_bits)
            expanded = [
                candidate | (suffix << known_bits)
                for candidate in candidates
                for suffix in range(1 << add_bits)
                if candidate | (suffix << known_bits) < domain
            ]
            candidates = np.asarray(expanded, dtype=np.int64)
            known_bits += add_bits

        lookup = {int(value): idx for idx, value in enumerate(candidates)}
        mask = (1 << known_bits) - 1
        categories = np.fromiter(
            (lookup.get(int(value) & mask, len(candidates)) for value in group),
            dtype=np.int64,
            count=len(group),
        )
        estimate = olh(categories, len(candidates) + 1, epsilon, rng)
        candidate_counts = estimate.counts[:-1]
        candidate_variances = estimate.variances[:-1]

        selected = np.argsort(-candidate_counts, kind="stable")[:keep]
        candidates = candidates[selected]
        # Each user participates in exactly one group. Scaling estimates to the
        # full population makes scores comparable between servers.
        scale = len(values) / max(1, len(group))
        final_counts = candidate_counts[selected] * scale
        final_variances = candidate_variances[selected] * scale**2

    order = np.argsort(-final_counts, kind="stable")
    return PEMEstimate(
        candidates[order], final_counts[order], final_variances[order]
    )

