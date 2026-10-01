"""Experiment orchestration for target-distribution top-k transfer."""

from __future__ import annotations

from dataclasses import dataclass
import csv
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np

from fusion import (
    ServerRelease,
    candidate_set,
    context_augmented_candidate_set,
    fuse_censor_aware_item_context,
    fuse_adaptive_public_context,
    fuse_adaptive_item_context,
    fuse_average,
    fuse_oracle,
    fuse_item_level_context,
    fuse_public_context_weighted,
    fuse_robust_adaptive_context,
    fuse_variance_weighted,
    fuse_vote,
)
from ldp_protocols import estimate_frequency
from metrics import (
    candidate_miss_mass,
    candidate_recall_upper_bound,
    evaluate,
    migration_error,
    top_items,
)
from pem import pem
from competitive_baselines import context_mixture, trimmed_frequency, rank_frequency
from problem_definition import DEFAULT_VISIBILITY, VisibilityContract
from simulation import CONTEXT_CONDITIONS, SyntheticProblem, make_problem


ALLOWED_MECHANISMS = ("PEM", "GRR", "OUE", "OLH", "MIXED")
SOURCE_CONDITIONS = ("clean", "unrelated", "stale", "adversarial", "missing")


@dataclass(frozen=True)
class ExperimentConfig:
    domain: int = 128
    users_per_server: int = 1500
    server_count: int = 6
    top_k: int = 10
    epsilon: float = 2.0
    rounds: int = 3
    context_quality: float = 0.7
    adaptive_server_budget: int = 3
    seed: int = 20260902
    mechanisms: tuple[str, ...] = ALLOWED_MECHANISMS
    visibility: VisibilityContract = DEFAULT_VISIBILITY
    server_epsilons: tuple[float, ...] | None = None
    server_user_counts: tuple[int, ...] | None = None
    context_condition: str = "clean"
    source_condition: str = "clean"
    affected_source_fraction: float = 0.34
    report_ratio: float = 2.0
    context_candidate_ratio: float = 0.0
    censor_prior_strength: float = 0.10
    censor_transfer_scale: float = 1.0
    target_concentration: float = 24.0
    latent_exponent: float = 0.9
    source_exponent: float = 1.08
    source_mix_min: float = 0.15
    source_mix_max: float = 0.9

    def validate(self) -> None:
        self.visibility.validate()
        if self.rounds < 1:
            raise ValueError("rounds must be positive")
        if self.top_k < 1 or 2 * self.top_k > self.domain:
            raise ValueError("top_k must satisfy 1 <= 2k <= domain")
        if self.users_per_server < 10 or self.server_count < 2:
            raise ValueError("need at least 10 users/server and two servers")
        if self.epsilon <= 0:
            raise ValueError("epsilon must be positive")
        unknown = set(self.mechanisms).difference(ALLOWED_MECHANISMS)
        if unknown:
            raise ValueError(f"unknown mechanisms: {sorted(unknown)}")
        if self.server_epsilons is not None and len(self.server_epsilons) != self.server_count:
            raise ValueError("server_epsilons must have one value per server")
        if self.server_user_counts is not None and len(self.server_user_counts) != self.server_count:
            raise ValueError("server_user_counts must have one value per server")
        if self.server_epsilons is not None and any(value <= 0 for value in self.server_epsilons):
            raise ValueError("all server_epsilons must be positive")
        if self.server_user_counts is not None and any(value < 10 for value in self.server_user_counts):
            raise ValueError("all server_user_counts must be at least 10")
        if self.context_condition not in CONTEXT_CONDITIONS:
            raise ValueError(f"unknown context_condition: {self.context_condition}")
        if self.source_condition not in SOURCE_CONDITIONS:
            raise ValueError(f"unknown source_condition: {self.source_condition}")
        if not 0 <= self.affected_source_fraction <= 1:
            raise ValueError("affected_source_fraction must be in [0, 1]")
        if self.report_ratio < 1 or math.ceil(self.report_ratio * self.top_k) > self.domain:
            raise ValueError("report_ratio must satisfy k <= ceil(report_ratio*k) <= domain")
        if self.context_candidate_ratio < 0 or math.ceil(self.context_candidate_ratio * self.top_k) > self.domain:
            raise ValueError(
                "context_candidate_ratio must satisfy 0 <= ceil(r*k) <= domain"
            )
        if self.censor_prior_strength < 0 or self.censor_transfer_scale < 0:
            raise ValueError("censor-aware hyperparameters must be non-negative")
        if self.target_concentration <= 0 or self.latent_exponent <= 0 or self.source_exponent <= 0:
            raise ValueError("distribution parameters must be positive")
        if not 0 <= self.source_mix_min <= self.source_mix_max <= 1:
            raise ValueError("source mix range must satisfy 0 <= min <= max <= 1")


def _mechanism_for_server(scenario: str, server_id: int) -> str:
    if scenario != "MIXED":
        return scenario
    choices = ("PEM", "GRR", "OUE", "OLH")
    return choices[server_id % len(choices)]


def _release(
    server_id: int,
    distribution: np.ndarray,
    mechanism: str,
    config: ExperimentConfig,
    rng: np.random.Generator,
    epsilon: float | None = None,
    user_count: int | None = None,
) -> ServerRelease:
    epsilon = config.epsilon if epsilon is None else epsilon
    user_count = config.users_per_server if user_count is None else user_count
    data = rng.choice(config.domain, size=user_count, p=distribution)
    report_k = min(config.domain, int(math.ceil(config.report_ratio * config.top_k)))
    if mechanism == "PEM":
        result = pem(data, config.domain, report_k, epsilon, rng)
        items = result.items[:report_k]
        counts = result.counts[:report_k]
        variances = result.variances[:report_k]
    else:
        result = estimate_frequency(mechanism, data, config.domain, epsilon, rng)
        items = np.argsort(-result.counts, kind="stable")[:report_k]
        counts = result.counts[items]
        variances = result.variances[items]

    frequencies = {
        int(item): max(0.0, float(count)) / user_count
        for item, count in zip(items, counts)
    }
    normalized_variances = {
        int(item): float(variance) / user_count**2
        for item, variance in zip(items, variances)
    }
    return ServerRelease(
        server_id,
        mechanism,
        tuple(int(item) for item in items),
        frequencies,
        normalized_variances,
    )


def _adversarial_release(
    release: ServerRelease,
    public_context: np.ndarray,
    report_k: int,
) -> ServerRelease:
    """Create a strong, simulation-only summary-poisoning attack."""
    items = np.argsort(public_context, kind="stable")[:report_k].astype(int)
    frequencies = {
        int(item): 1.0 - 0.4 * rank / max(1, report_k - 1)
        for rank, item in enumerate(items)
    }
    variances = {int(item): 1e-12 for item in items}
    return ServerRelease(
        release.server_id,
        f"ADVERSARIAL({release.mechanism})",
        tuple(items.tolist()),
        frequencies,
        variances,
    )


def _predictions(
    releases: list[ServerRelease],
    problem: SyntheticProblem,
    config: ExperimentConfig,
    visible_context: np.ndarray | None,
) -> dict[str, list[int]]:
    report_k = min(config.domain, int(math.ceil(config.report_ratio * config.top_k)))
    available_distributions = [problem.servers[release.server_id] for release in releases]
    global_distribution = np.mean(available_distributions, axis=0)
    oracle_weights = np.asarray(
        [problem.similarities[release.server_id] for release in releases]
    )
    baseline_predictions = {
        "vote": fuse_vote(releases, config.top_k),
        "average": fuse_average(releases, config.top_k),
        "variance_weighted": fuse_variance_weighted(releases, config.top_k),
        "oracle_weighted": fuse_oracle(releases, oracle_weights, config.top_k),
        "global_true_average": top_items(global_distribution, config.top_k),
        "trimmed_frequency": trimmed_frequency(releases, config.top_k, trim=1) if len(releases) >= 3 else fuse_average(releases, config.top_k),
        "rank_frequency": rank_frequency(releases, config.top_k, frequency_weight=1.0),
    }
    if visible_context is None:
        # No-context is a genuine identifiability baseline. A uniform vector
        # would create arbitrary item-ID ranking and a false target signal.
        baseline_predictions.update(
            {
                "context_weighted": baseline_predictions["average"],
                "adaptive_context": baseline_predictions["average"],
                "item_context": baseline_predictions["average"],
                "adaptive_item_context": baseline_predictions["average"],
                "censor_aware_item_context": baseline_predictions["average"],
                "adaptive_censor_aware_item_context": baseline_predictions["average"],
                "robust_adaptive_context": baseline_predictions["average"],
                "context_mixture": baseline_predictions["average"],
            }
        )
    else:
        context_candidates = context_augmented_candidate_set(
            releases,
            visible_context,
            int(math.ceil(config.context_candidate_ratio * config.top_k)),
        )
        baseline_predictions.update(
            {
                "context_weighted": fuse_public_context_weighted(
                    releases, visible_context, report_k, config.top_k
                ),
                "adaptive_context": fuse_adaptive_public_context(
                    releases,
                    visible_context,
                    report_k,
                    config.top_k,
                    config.adaptive_server_budget,
                ),
                "item_context": fuse_item_level_context(
                    releases, visible_context, config.top_k
                ),
                "adaptive_item_context": fuse_adaptive_item_context(
                    releases,
                    visible_context,
                    config.top_k,
                    config.adaptive_server_budget,
                ),
                "censor_aware_item_context": fuse_censor_aware_item_context(
                    releases,
                    visible_context,
                    report_k,
                    config.top_k,
                    prior_strength=config.censor_prior_strength,
                    transfer_scale=config.censor_transfer_scale,
                ),
                "adaptive_censor_aware_item_context": fuse_censor_aware_item_context(
                    releases,
                    visible_context,
                    report_k,
                    config.top_k,
                    server_budget=config.adaptive_server_budget,
                    prior_strength=config.censor_prior_strength,
                    transfer_scale=config.censor_transfer_scale,
                ),
                "robust_adaptive_context": fuse_robust_adaptive_context(
                    releases,
                    visible_context,
                    report_k,
                    config.top_k,
                    config.adaptive_server_budget,
                ),
                "context_mixture": context_mixture(releases, visible_context, config.top_k, alpha=0.5),
            }
        )
        if config.context_candidate_ratio > 0:
            baseline_predictions.update(
                {
                    "censor_aware_item_context_augmented": fuse_censor_aware_item_context(
                        releases,
                        visible_context,
                        report_k,
                        config.top_k,
                        prior_strength=config.censor_prior_strength,
                        transfer_scale=config.censor_transfer_scale,
                        candidate_items=context_candidates,
                    ),
                    "adaptive_censor_aware_item_context_augmented": fuse_censor_aware_item_context(
                        releases,
                        visible_context,
                        report_k,
                        config.top_k,
                        server_budget=config.adaptive_server_budget,
                        prior_strength=config.censor_prior_strength,
                        transfer_scale=config.censor_transfer_scale,
                        candidate_items=context_candidates,
                    ),
                }
            )
    return baseline_predictions


def run(config: ExperimentConfig) -> list[dict[str, object]]:
    config.validate()
    rows: list[dict[str, object]] = []
    for round_id in range(config.rounds):
        problem_rng = np.random.default_rng(config.seed + round_id * 100_003)
        problem = make_problem(
            config.domain,
            config.server_count,
            config.context_quality,
            problem_rng,
            context_condition=config.context_condition,
            source_condition=(
                config.source_condition
                if config.source_condition in {"clean", "unrelated", "stale"}
                else "clean"
            ),
            affected_source_fraction=config.affected_source_fraction,
            target_concentration=config.target_concentration,
            latent_exponent=config.latent_exponent,
            source_exponent=config.source_exponent,
            source_mix_min=config.source_mix_min,
            source_mix_max=config.source_mix_max,
        )
        truth = top_items(problem.target, config.top_k)
        visible_context = (
            problem.public_target_context
            if config.visibility.public_target_context
            else None
        )

        for scenario_id, scenario in enumerate(config.mechanisms):
            scenario_rng = np.random.default_rng(
                config.seed + round_id * 100_003 + (scenario_id + 1) * 7_919
            )
            releases = [
                _release(
                    server_id,
                    distribution,
                    _mechanism_for_server(scenario, server_id),
                    config,
                    scenario_rng,
                    epsilon=(config.server_epsilons[server_id] if config.server_epsilons else config.epsilon),
                    user_count=(config.server_user_counts[server_id] if config.server_user_counts else config.users_per_server),
                )
                for server_id, distribution in enumerate(problem.servers)
            ]
            affected_count = (
                max(1, int(round(config.server_count * config.affected_source_fraction)))
                if config.affected_source_fraction > 0
                else 0
            )
            effective_affected_count = (
                affected_count if config.source_condition != "clean" else 0
            )
            if config.source_condition == "adversarial":
                report_k = min(
                    config.domain, int(math.ceil(config.report_ratio * config.top_k))
                )
                releases = [
                    _adversarial_release(
                        release, problem.public_target_context, report_k
                    )
                    if index < affected_count
                    else release
                    for index, release in enumerate(releases)
                ]
            elif config.source_condition == "missing" and affected_count:
                releases = releases[min(affected_count, len(releases) - 1):]
            source_candidates = candidate_set(releases)
            augmented_candidates = context_augmented_candidate_set(
                releases,
                visible_context,
                int(math.ceil(config.context_candidate_ratio * config.top_k))
                if visible_context is not None
                else 0,
            )
            migration = migration_error(problem.target, problem.servers)
            for method, prediction in _predictions(
                releases, problem, config, visible_context
            ).items():
                method_candidates = (
                    augmented_candidates
                    if method.endswith("_augmented")
                    else source_candidates
                )
                candidate_upper = candidate_recall_upper_bound(truth, method_candidates)
                miss_mass = candidate_miss_mass(problem.target, method_candidates)
                result = evaluate(problem.target, truth, prediction, method_candidates)
                rows.append(
                    {
                        "round": round_id + 1,
                        "scenario": scenario,
                        "method": method,
                        "candidate_size": len(method_candidates),
                        "source_candidate_size": len(source_candidates),
                        "context_added_candidate_count": len(
                            augmented_candidates - source_candidates
                        ),
                        "reported_item_count": sum(len(release.top_items) for release in releases),
                        "estimated_payload_bytes": 24 * sum(len(release.top_items) for release in releases),
                        "context_quality": config.context_quality,
                        "context_condition": config.context_condition,
                        "public_context_visible": config.visibility.public_target_context,
                        "source_condition": config.source_condition,
                        "affected_source_fraction": config.affected_source_fraction,
                        "affected_source_count": effective_affected_count,
                        "effective_affected_source_fraction": (
                            effective_affected_count / config.server_count
                        ),
                        "report_ratio": config.report_ratio,
                        "context_candidate_ratio": config.context_candidate_ratio,
                        "candidate_recall_upper_bound": candidate_upper,
                        "candidate_miss_mass": miss_mass,
                        **migration,
                        **result,
                    }
                )
    return rows


def summarize(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (str(row["scenario"]), str(row["method"]))
        groups.setdefault(key, []).append(row)
    summary: list[dict[str, object]] = []
    for (scenario, method), records in sorted(groups.items()):
        metric_names = (
            "precision",
            "recall",
            "coverage",
            "ndcg",
            "candidate_recall_upper_bound",
            "candidate_miss_mass",
            "source_target_tv_mean",
            "source_target_tv_best",
            "source_mean_bias_l1",
        )
        metric_values = {
            metric: np.asarray(
                [float(record[metric]) for record in records], dtype=float
            )
            for metric in metric_names
        }
        summary.append(
            {
                "scenario": scenario,
                "method": method,
                "rounds": len(records),
                **{
                    metric: float(np.mean(values))
                    for metric, values in metric_values.items()
                },
                **{
                    f"{metric}_std": (
                        float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
                    )
                    for metric, values in metric_values.items()
                },
                "candidate_size": float(
                    np.mean([int(record["candidate_size"]) for record in records])
                ),
                "source_candidate_size": float(
                    np.mean([int(record["source_candidate_size"]) for record in records])
                ),
                "context_added_candidate_count": float(
                    np.mean(
                        [int(record["context_added_candidate_count"]) for record in records]
                    )
                ),
                "reported_item_count": float(
                    np.mean([int(record["reported_item_count"]) for record in records])
                ),
                "estimated_payload_bytes": float(
                    np.mean([int(record["estimated_payload_bytes"]) for record in records])
                ),
            }
        )
    return summary


def write_results(rows: list[dict[str, object]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "round",
        "scenario",
        "method",
        "candidate_size",
        "source_candidate_size",
        "context_added_candidate_count",
        "reported_item_count",
        "estimated_payload_bytes",
        "context_quality",
        "context_condition",
        "public_context_visible",
        "source_condition",
        "affected_source_fraction",
        "affected_source_count",
        "effective_affected_source_fraction",
        "report_ratio",
        "context_candidate_ratio",
        "candidate_recall_upper_bound",
        "candidate_miss_mass",
        "source_target_tv_mean",
        "source_target_tv_best",
        "source_mean_bias_l1",
        "precision",
        "recall",
        "coverage",
        "ndcg",
    ]
    with (output_dir / "round_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summarize(rows), handle, ensure_ascii=False, indent=2)
