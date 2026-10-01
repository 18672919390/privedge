"""Two-layer poisoning defence.

Layer 1 (publisher side, sees raw OLH reports): detect fake-report clusters.
Honest OLH reports support any fixed item set T jointly with probability close
to g^-|T|; maximal-gain fake reports are crafted to support all target items at
once, so their joint support is far above that expectation.

Layer 2 (target gateway, sees only signed summaries): each published frequency
is clipped into [floor, leave-one-out consensus + clip_z * scale], where the scale
uses the peers' LDP noise plus the observed cross-source heterogeneity, and each
source's fusion weight is capped at kappa x the leave-one-out median weight.
The per-source anomaly score is an alert only; it never removes a source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np

from .algorithms import ServerRelease, release_uncertainty
from .ldp import OLHReports, aggregate, olh_parameters, support_matrix


@dataclass
class FilterReport:
    flagged_items: list[int] = field(default_factory=list)
    z_score: float = 0.0
    removed_reports: int = 0
    removed_mask: np.ndarray | None = None

    def to_json(self) -> dict:
        return {"method": "joint-support-itemset-v1", "flagged_items": self.flagged_items,
                "z_score": round(self.z_score, 3), "removed_reports": self.removed_reports}


def _expected_joint(n: int, freqs: np.ndarray, p: float, q: float) -> float:
    size = len(freqs)
    inside = float(np.clip(freqs, 0.0, 1.0).sum())
    inside = min(inside, 1.0)
    return n * (inside * p * q ** (size - 1) + (1.0 - inside) * q**size)


def filter_fake_reports(
    reports: OLHReports,
    domain: int,
    candidate_size: int = 40,
    z_threshold: float = 6.0,
    max_set_size: int = 8,
    retain: float = 0.7,
) -> tuple[OLHReports, FilterReport]:
    """Remove reports that jointly support an anomalous item set."""
    estimate = aggregate(reports, domain)
    n = reports.n
    freqs = np.clip(estimate.counts / max(n, 1), 0.0, 1.0)
    _, p, q = olh_parameters(reports.epsilon)
    candidates = np.argsort(-estimate.counts, kind="stable")[:candidate_size]
    support = support_matrix(reports, candidates)
    joint = support.T.astype(np.int64) @ support.astype(np.int64)

    best_pair, best_z = None, z_threshold
    for a, b in combinations(range(len(candidates)), 2):
        expected = _expected_joint(n, freqs[candidates[[a, b]]], p, q)
        z = (joint[a, b] - expected) / np.sqrt(max(expected, 1.0))
        if z > best_z:
            best_pair, best_z = (a, b), z
    if best_pair is None:
        return reports, FilterReport()

    members = list(best_pair)
    mask = support[:, members].all(axis=1)
    excess = mask.sum() - _expected_joint(n, freqs[candidates[members]], p, q)
    while len(members) < max_set_size:
        best_next, best_next_excess, best_next_z = None, retain * excess, z_threshold
        for c in range(len(candidates)):
            if c in members:
                continue
            trial = mask & support[:, c]
            expected = _expected_joint(n, freqs[candidates[members + [c]]], p, q)
            trial_excess = trial.sum() - expected
            z = trial_excess / np.sqrt(max(expected, 1.0))
            # An item joins only if the anomalous cluster keeps most of its mass;
            # an unrelated item would cut the cluster to roughly 1/g of its size.
            if z > z_threshold and trial_excess >= best_next_excess:
                best_next, best_next_excess, best_next_z = c, trial_excess, z
        if best_next is None:
            break
        members.append(best_next)
        mask = mask & support[:, best_next]
        excess, best_z = best_next_excess, best_next_z

    keep = ~mask
    filtered = OLHReports(reports.seeds[keep], reports.buckets[keep], reports.epsilon, reports.g)
    return filtered, FilterReport(sorted(int(candidates[m]) for m in members), float(best_z), int(mask.sum()), mask)


@dataclass
class SourceScore:
    index: int
    score: float
    worst_item: int | None
    flagged: bool


def _dense(release: ServerRelease, items: list[int]) -> tuple[np.ndarray, np.ndarray]:
    published = [release.frequencies[i] for i in release.top_items]
    threshold = max(0.0, min(published)) if published else 0.0
    median_var = float(np.median(list(release.variances.values()))) if release.variances else 1e-8
    values = np.array([release.frequencies.get(i, 0.5 * threshold) for i in items], dtype=float)
    variances = np.array([release.variances.get(i, median_var) for i in items], dtype=float)
    return values, variances


def source_scores(releases: list[ServerRelease], z_threshold: float = 4.0, rel_floor: float = 0.25) -> list[SourceScore]:
    """Leave-one-out robust z-score of each source's largest over-report."""
    if len(releases) < 3:
        return [SourceScore(i, 0.0, None, False) for i in range(len(releases))]
    items = sorted({item for release in releases for item in release.top_items})
    dense = [_dense(release, items) for release in releases]
    values = np.vstack([v for v, _ in dense])
    variances = np.vstack([v for _, v in dense])
    scores = []
    for s in range(len(releases)):
        others = np.delete(values, s, axis=0)
        consensus = np.median(others, axis=0)
        spread = 1.4826 * np.median(np.abs(others - consensus), axis=0)
        scale = np.sqrt(variances[s] + spread**2 + (rel_floor * consensus) ** 2 + 1e-10)
        z = (values[s] - consensus) / scale
        worst = int(np.argmax(z))
        scores.append(SourceScore(s, float(z[worst]), int(items[worst]), bool(z[worst] > z_threshold)))
    return scores


def winsorize_releases(
    releases: list[ServerRelease], clip_z: float = 3.0, rel_floor: float = 0.25, floor: float | None = None
) -> tuple[list[ServerRelease], list[float]]:
    """Clip each published frequency to at most consensus + clip_z * scale (and at least ``floor``).

    Consensus and scale are leave-one-out statistics over the other sources, so a
    single source cannot move its own ceiling. Fusion treats unpublished items as 0,
    so floor=0 limits a source's downward pull on any item to what withholding it achieves.
    Returns the sanitised releases and the total clipped mass per source (an audit signal).
    """
    if len(releases) < 3:
        return releases, [0.0] * len(releases)
    items = sorted({item for release in releases for item in release.top_items})
    position = {item: j for j, item in enumerate(items)}
    dense = [_dense(release, items) for release in releases]
    values = np.vstack([v for v, _ in dense])
    variances = np.vstack([v for _, v in dense])
    sanitised, clipped_mass = [], []
    for s, release in enumerate(releases):
        others = np.delete(values, s, axis=0)
        consensus = np.median(others, axis=0)
        spread = 1.4826 * np.median(np.abs(others - consensus), axis=0)
        # A source's own claimed variance is attacker-controlled; use its peers'.
        noise = np.median(np.delete(variances, s, axis=0), axis=0)
        ceiling = consensus + clip_z * np.sqrt(noise + spread**2 + (rel_floor * consensus) ** 2 + 1e-10)
        frequencies, removed = {}, 0.0
        for item in release.top_items:
            value = release.frequencies[item]
            capped = min(value, float(ceiling[position[item]]))
            if floor is not None:
                capped = max(capped, floor)
            removed += abs(value - capped)
            frequencies[item] = capped
        top_items = tuple(sorted(frequencies, key=lambda i: (-frequencies[i], i)))
        sanitised.append(ServerRelease(release.server_id, release.mechanism, top_items, frequencies, dict(release.variances)))
        clipped_mass.append(removed)
    return sanitised, clipped_mass


def capped_weights(releases: list[ServerRelease], kappa: float | None) -> np.ndarray:
    """Inverse-uncertainty weights, each capped at kappa x the leave-one-out median weight.

    Claimed variances are publisher-controlled; without the cap one source can take
    almost all fusion weight by under-reporting its noise.
    """
    weights = 1.0 / np.maximum(np.array([release_uncertainty(r) for r in releases]), 1e-12)
    if kappa is None or len(releases) < 3:
        return weights
    ceilings = np.array([kappa * np.median(np.delete(weights, s)) for s in range(len(weights))])
    return np.minimum(weights, ceilings)
