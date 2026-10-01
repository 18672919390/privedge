"""Attack generators used by the security test suite and the demo attack lab."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from .envelope import ContextEnvelope, ReleaseEnvelope, ReleaseItem
from .ldp import OLHReports, hash_matrix, olh_parameters


def mga_fake_reports(
    target_items: list[int], n_fake: int, epsilon: float, rng: np.random.Generator, trials: int = 256
) -> OLHReports:
    """Maximal-gain attack on OLH: each fake user picks the hash seed that maps the
    most target items into one bucket and reports that bucket without noise."""
    g, _, _ = olh_parameters(epsilon)
    targets = np.asarray(target_items, dtype=np.int64)
    seeds = rng.integers(0, 2**31 - 1, size=n_fake * trials, dtype=np.int64)
    hashed = hash_matrix(targets, seeds, g).reshape(n_fake, trials, len(targets))
    counts = np.stack([(hashed == b).sum(axis=2) for b in range(g)], axis=2)
    best_bucket = counts.argmax(axis=2)
    best_count = counts.max(axis=2)
    choice = best_count.argmax(axis=1)
    rows = np.arange(n_fake)
    chosen_seeds = seeds.reshape(n_fake, trials)[rows, choice]
    buckets = best_bucket[rows, choice]
    return OLHReports(chosen_seeds, buckets.astype(np.int64), float(epsilon), g)


def combine(honest: OLHReports, fake: OLHReports) -> OLHReports:
    return OLHReports(
        np.concatenate([honest.seeds, fake.seeds]),
        np.concatenate([honest.buckets, fake.buckets]),
        honest.epsilon,
        honest.g,
    )


def tamper_frequencies(env: ReleaseEnvelope, target_items: list[int], value: float) -> ReleaseEnvelope:
    """Man-in-the-middle edit without re-signing: must fail signature verification."""
    median_var = float(np.median([item.variance for item in env.items]))
    injected = [ReleaseItem(int(t), value, median_var) for t in target_items]
    kept = [item for item in env.items if item.category not in target_items]
    return replace(env, items=tuple(injected + kept)[: env.top_m])


def compromised_publisher_items(
    env: ReleaseEnvelope, target_items: list[int], value: float
) -> tuple[ReleaseItem, ...]:
    """Items a compromised (validly signing) publisher would publish."""
    return tamper_frequencies(env, target_items, value).items


def weight_hijack_items(
    items: tuple[ReleaseItem, ...], target_items: list[int], variance_scale: float = 1e-4, demote: int = 0
) -> tuple[ReleaseItem, ...]:
    """Compromised publisher that also under-reports its noise to dominate variance weighting.

    Targets are injected at the source's top frequency; with ``demote`` > 0 its own
    ``demote`` highest honest items are withheld to push true favourites down.
    """
    top_value = max(item.frequency for item in items)
    median_var = float(np.median([item.variance for item in items]))
    honest = [item for item in items if item.category not in target_items][demote:]
    injected = [ReleaseItem(int(t), top_value, median_var) for t in target_items]
    chosen = (injected + honest)[: len(items)]
    return tuple(ReleaseItem(item.category, item.frequency, item.variance * variance_scale) for item in chosen)


def swap_context(env: ContextEnvelope, other: ContextEnvelope) -> ContextEnvelope:
    """Present another region's validly signed context as the target's."""
    return other


def forge_context_values(env: ContextEnvelope, values: tuple[float, ...]) -> ContextEnvelope:
    return replace(env, values=values)
