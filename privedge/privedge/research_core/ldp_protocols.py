"""Frequency oracles ported from Tianhao Wang's LDP_Protocols repository.

Source mapping:
  GRR -> LDP_Protocols-master/hio/server/fo/rr.py
  OUE -> LDP_Protocols-master/hio/server/fo/ue.py
  OLH -> LDP_Protocols-master/hio/server/fo/lh.py and olh.py

The equations and perturbation logic are retained. Changes are limited to a
Python 3 API, NumPy Generator injection, unbiased aggregation, and a
deterministic universal-hash fallback when the optional xxhash package is not
installed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

import numpy as np

try:
    import xxhash  # type: ignore
except ImportError:  # pragma: no cover - exercised on machines without xxhash
    xxhash = None


@dataclass(frozen=True)
class FrequencyEstimate:
    counts: np.ndarray
    variances: np.ndarray
    mechanism: str


def _validate(data: np.ndarray, domain: int, epsilon: float) -> np.ndarray:
    values = np.asarray(data, dtype=np.int64)
    if domain < 2:
        raise ValueError("domain must be at least 2")
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    if values.ndim != 1 or np.any(values < 0) or np.any(values >= domain):
        raise ValueError("data must be a one-dimensional array in [0, domain)")
    return values


def _plugin_variance(
    estimates: np.ndarray, n: int, p: float, q: float
) -> np.ndarray:
    """Plug-in variance of the unbiased count estimator.

    This follows the error decomposition used by the original FO code while
    retaining both true-positive and false-positive Bernoulli terms.
    """
    frequency = np.clip(estimates, 0.0, float(n))
    numerator = frequency * p * (1.0 - p) + (n - frequency) * q * (1.0 - q)
    return np.maximum(numerator / ((p - q) ** 2), 1e-12)


def grr(
    data: np.ndarray, domain: int, epsilon: float, rng: np.random.Generator
) -> FrequencyEstimate:
    """Generalized randomized response (RR in the source repository)."""
    values = _validate(data, domain, epsilon)
    n = len(values)
    ee = math.exp(epsilon)
    p = ee / (ee + domain - 1)
    q = 1.0 / (ee + domain - 1)

    reports = values.copy()
    changed = rng.random(n) > p
    alternatives = rng.integers(0, domain - 1, size=int(changed.sum()))
    originals = values[changed]
    reports[changed] = alternatives + (alternatives >= originals)

    observed = np.bincount(reports, minlength=domain).astype(float)
    estimates = (observed - n * q) / (p - q)
    return FrequencyEstimate(estimates, _plugin_variance(estimates, n, p, q), "GRR")


def oue(
    data: np.ndarray, domain: int, epsilon: float, rng: np.random.Generator
) -> FrequencyEstimate:
    """Optimized unary encoding (UE with p=1/2 in the source repository)."""
    values = _validate(data, domain, epsilon)
    n = len(values)
    p = 0.5
    q = 1.0 / (math.exp(epsilon) + 1.0)

    reports = rng.random((n, domain)) < q
    reports[np.arange(n), values] = rng.random(n) < p
    observed = reports.sum(axis=0, dtype=np.int64).astype(float)
    estimates = (observed - n * q) / (p - q)
    return FrequencyEstimate(estimates, _plugin_variance(estimates, n, p, q), "OUE")


def _fallback_hash(values: np.ndarray, seed: int, modulus: int) -> np.ndarray:
    """Deterministic 64-bit mixing used only if xxhash is unavailable."""
    x = np.asarray(values, dtype=np.uint64) + np.uint64(seed)
    with np.errstate(over="ignore"):
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        x = x ^ (x >> np.uint64(31))
    return (x % np.uint64(modulus)).astype(np.int64)


def _hash_many(values: np.ndarray, seed: int, modulus: int) -> np.ndarray:
    if xxhash is None:
        return _fallback_hash(values, seed, modulus)
    return np.fromiter(
        (xxhash.xxh32(str(int(v)).encode("ascii"), seed=int(seed)).intdigest() % modulus for v in values),
        dtype=np.int64,
        count=len(values),
    )


def olh(
    data: np.ndarray, domain: int, epsilon: float, rng: np.random.Generator
) -> FrequencyEstimate:
    """Optimized local hashing using the original LH probabilities."""
    values = _validate(data, domain, epsilon)
    n = len(values)
    ee = math.exp(epsilon)
    g = int(round(ee)) + 1
    p = ee / (ee + g - 1)
    q = 1.0 / g

    seeds = rng.integers(0, 2**31 - 1, size=n, dtype=np.int64)
    reports = np.empty(n, dtype=np.int64)
    for i, (value, seed) in enumerate(zip(values, seeds)):
        hashed = int(_hash_many(np.asarray([value]), int(seed), g)[0])
        if rng.random() <= p:
            reports[i] = hashed
        else:
            alternative = int(rng.integers(0, g - 1))
            reports[i] = alternative + (alternative >= hashed)

    support = np.zeros(domain, dtype=float)
    candidates = np.arange(domain, dtype=np.int64)
    for report, seed in zip(reports, seeds):
        support += _hash_many(candidates, int(seed), g) == report
    estimates = (support - n * q) / (p - q)
    return FrequencyEstimate(estimates, _plugin_variance(estimates, n, p, q), "OLH")


PROTOCOLS: dict[str, Callable[..., FrequencyEstimate]] = {
    "GRR": grr,
    "OUE": oue,
    "OLH": olh,
}


def estimate_frequency(
    mechanism: str,
    data: np.ndarray,
    domain: int,
    epsilon: float,
    rng: np.random.Generator,
) -> FrequencyEstimate:
    name = mechanism.upper()
    if name not in PROTOCOLS:
        raise ValueError(f"unknown frequency oracle: {mechanism}")
    return PROTOCOLS[name](data, domain, epsilon, rng)
