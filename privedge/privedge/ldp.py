"""Optimized Local Hashing split into a user-side client and a server-side aggregator.

The hash family and the random-number consumption order are identical to the
research core's ``ldp_protocols.olh`` running without xxhash (the configuration
used for every recorded experiment), so identical seeds give identical estimates.
Only the support counting is vectorised.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

HASH_FAMILY = "splitmix64-fallback-v1"
_M1 = np.uint64(0xBF58476D1CE4E5B9)
_M2 = np.uint64(0x94D049BB133111EB)


def olh_parameters(epsilon: float) -> tuple[int, float, float]:
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    ee = math.exp(epsilon)
    g = int(round(ee)) + 1
    return g, ee / (ee + g - 1), 1.0 / g


def hash_matrix(values: np.ndarray, seeds: np.ndarray, g: int) -> np.ndarray:
    """H[i, j] = hash(values[j]; seeds[i]) mod g, shape (len(seeds), len(values))."""
    v = np.asarray(values, dtype=np.uint64)[None, :]
    s = np.asarray(seeds, dtype=np.uint64)[:, None]
    with np.errstate(over="ignore"):
        x = v + s
        x = (x ^ (x >> np.uint64(30))) * _M1
        x = (x ^ (x >> np.uint64(27))) * _M2
        x = x ^ (x >> np.uint64(31))
    return (x % np.uint64(g)).astype(np.int64)


@dataclass(frozen=True)
class OLHReports:
    """What leaves the users' devices: one (seed, bucket) pair per user."""

    seeds: np.ndarray
    buckets: np.ndarray
    epsilon: float
    g: int

    @property
    def n(self) -> int:
        return int(len(self.buckets))

    def bytes_per_report(self) -> int:
        return 4 + max(1, math.ceil(math.log2(max(self.g, 2)) / 8))


def perturb(values: np.ndarray, domain: int, epsilon: float, rng: np.random.Generator) -> OLHReports:
    values = np.asarray(values, dtype=np.int64)
    if values.ndim != 1 or np.any(values < 0) or np.any(values >= domain):
        raise ValueError("values must be a one-dimensional array in [0, domain)")
    g, p, _ = olh_parameters(epsilon)
    n = len(values)
    seeds = rng.integers(0, 2**31 - 1, size=n, dtype=np.int64)
    hashed = _diag_hash(values, seeds, g)
    buckets = np.empty(n, dtype=np.int64)
    for i in range(n):
        if rng.random() <= p:
            buckets[i] = hashed[i]
        else:
            alternative = int(rng.integers(0, g - 1))
            buckets[i] = alternative + (alternative >= hashed[i])
    return OLHReports(seeds, buckets, float(epsilon), g)


def _diag_hash(values: np.ndarray, seeds: np.ndarray, g: int) -> np.ndarray:
    out = np.empty(len(values), dtype=np.int64)
    for start in range(0, len(values), 2048):
        stop = start + 2048
        v = np.asarray(values[start:stop], dtype=np.uint64)
        s = np.asarray(seeds[start:stop], dtype=np.uint64)
        with np.errstate(over="ignore"):
            x = v + s
            x = (x ^ (x >> np.uint64(30))) * _M1
            x = (x ^ (x >> np.uint64(27))) * _M2
            x = x ^ (x >> np.uint64(31))
        out[start:stop] = (x % np.uint64(g)).astype(np.int64)
    return out


def support_matrix(reports: OLHReports, items: np.ndarray, chunk: int = 4096) -> np.ndarray:
    """Boolean (n, len(items)) matrix: does report i support item j."""
    items = np.asarray(items, dtype=np.int64)
    out = np.empty((reports.n, len(items)), dtype=bool)
    for start in range(0, reports.n, chunk):
        stop = start + chunk
        h = hash_matrix(items, reports.seeds[start:stop], reports.g)
        out[start:stop] = h == reports.buckets[start:stop, None]
    return out


@dataclass(frozen=True)
class FrequencyEstimate:
    counts: np.ndarray
    variances: np.ndarray
    n: int


def aggregate(reports: OLHReports, domain: int) -> FrequencyEstimate:
    _, p, q = olh_parameters(reports.epsilon)
    support = support_matrix(reports, np.arange(domain)).sum(axis=0).astype(float)
    n = reports.n
    counts = (support - n * q) / (p - q)
    frequency = np.clip(counts, 0.0, float(n))
    variances = np.maximum((frequency * p * (1 - p) + (n - frequency) * q * (1 - q)) / (p - q) ** 2, 1e-12)
    return FrequencyEstimate(counts, variances, n)


def estimate(values: np.ndarray, domain: int, epsilon: float, rng: np.random.Generator) -> FrequencyEstimate:
    return aggregate(perturb(values, domain, epsilon, rng), domain)


def theoretical_frequency_variance(epsilon: float, n: int) -> float:
    """Approximate variance of an OLH frequency estimate for a rare item."""
    ee = math.exp(epsilon)
    return 4.0 * ee / (n * (ee - 1.0) ** 2)
