"""Pre-registered four-method comparison (experiments_prereg/COMPARE_V1.md).

The three non-PrivEdge arms consume the same unsigned Top-m releases.  PrivEdge
consumes a second, publisher-filtered copy of those releases and applies the
v4.1 gateway policy.  Target truth is read only by the offline metric code.
"""

from __future__ import annotations

import argparse
import hashlib
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from ..adapters.standard import load
from ..algorithms import (
    ServerRelease,
    candidate_recall_upper_bound,
    candidate_set,
    evaluate,
    fuse_average,
    fuse_variance_weighted,
    top_items,
)
from ..attacks import combine, mga_fake_reports, weight_hijack_items
from ..decision import DecisionPolicy, decide
from ..envelope import ReleaseEnvelope, ReleaseItem
from ..gateway import AdmissionResult
from ..ldp import HASH_FAMILY, perturb
from ..pipeline import summarize_reports
from ..research_core.competitive_baselines import trimmed_frequency
from .runner import Run

EPSILON_GRID = [1.0, 2.0]
SEEDS = [101, 211, 307, 401, 503]
USERS, TOP_M, TOP_K, N_TARGETS = 5000, 20, 10, 3
KAPPA = 2.0
SCENARIOS = [
    ("clean", None, 0, 0.0),
    ("mga_1src_b0.02", "mga", 1, 0.02),
    ("mga_1src_b0.05", "mga", 1, 0.05),
    ("mga_1src_b0.10", "mga", 1, 0.10),
    ("mga_2src_b0.05", "mga", 2, 0.05),
    ("compromised_1src", "compromised", 1, 0.0),
    ("compromised_2src", "compromised", 2, 0.0),
    ("weight_hijack_1src", "hijack", 1, 0.0),
    ("weight_hijack_2src", "hijack", 2, 0.0),
]


def _to_release(index: int, items) -> ServerRelease:
    return ServerRelease(
        index,
        "OLH",
        tuple(int(item.category) for item in items),
        {int(item.category): float(item.frequency) for item in items},
        {int(item.category): float(item.variance) for item in items},
    )


def _to_envelope(source: str, items, epsilon: float, n_users: int) -> ReleaseEnvelope:
    return ReleaseEnvelope(
        release_id=f"rel-{source}",
        source_id=source,
        window_id="W",
        domain_hash="",
        mechanism="OLH",
        hash_family=HASH_FAMILY,
        epsilon=epsilon,
        n_users=n_users,
        top_m=TOP_M,
        items=tuple(items),
        tail_bound=0.0,
    )


def _compromise(items, targets: list[int]):
    """Replace target categories with a validly signing publisher's high values."""
    if not items:
        return tuple(items)
    top_value = max(float(item.frequency) for item in items)
    median_var = float(np.median([item.variance for item in items]))
    injected = [ReleaseItem(int(target), top_value, median_var) for target in targets]
    kept = [item for item in items if item.category not in targets]
    return tuple((injected + kept)[: len(items)])


def _bootstrap(values: np.ndarray, rounds: int = 2000) -> list[float]:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return [None, None]
    rng = np.random.default_rng(0)
    means = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(rounds)]
    return [round(float(x), 4) for x in np.percentile(means, [2.5, 97.5])]


def _attack_targets(data, sources: list[str], seed: int, target_index: int) -> list[int]:
    source_mean = np.mean([data.distribution(source) for source in sources], axis=0)
    pool = np.argsort(-source_mean, kind="stable")[30:80]
    rng = np.random.default_rng(np.random.SeedSequence([seed, target_index, 4242]))
    return sorted(int(x) for x in rng.choice(pool, size=N_TARGETS, replace=False))


def _poison_items(kind: str | None, items, targets: list[int]):
    if kind == "compromised":
        return _compromise(items, targets)
    if kind == "hijack":
        return weight_hijack_items(items, targets, variance_scale=1e-4)
    return items


def _predict_privedge(releases: list[ServerRelease], epsilon: float, user_counts: list[int]):
    envelopes = [
        _to_envelope(str(release.server_id), _release_items(release), epsilon, n_users)
        for release, n_users in zip(releases, user_counts)
    ]
    policy = DecisionPolicy(
        k=TOP_K,
        report_m=TOP_M,
        min_sources=3,
        min_item_support=2,
        winsorize=True,
        clip_z=3.0,
        weight_cap=KAPPA,
        clip_floor=0.0,
    )
    decision = decide(AdmissionResult(accepted=envelopes), policy)
    prediction = [] if decision.state == "REFUSED" else [int(item) for item in decision.top_k]
    return prediction, decision.state, [r["code"] for r in decision.reasons]


def _release_items(release: ServerRelease) -> tuple[ReleaseItem, ...]:
    return tuple(
        ReleaseItem(int(item), float(release.frequencies[item]), float(release.variances[item]))
        for item in release.top_items
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="massive_steps")
    parser.add_argument("--epsilons", default="1,2")
    parser.add_argument("--max-targets", type=int, default=0, help="smoke-test only")
    parser.add_argument("--max-seeds", type=int, default=0, help="smoke-test only")
    parser.add_argument("--seeds", default="", help="comma-separated replacement for the preregistered list")
    args = parser.parse_args()
    epsilons = [float(e) for e in args.epsilons.split(",")]
    if not epsilons or any(epsilon not in EPSILON_GRID for epsilon in epsilons):
        parser.error(f"--epsilons must be selected from {EPSILON_GRID}")
    base_seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else SEEDS
    seeds = base_seeds[: args.max_seeds] if args.max_seeds else base_seeds

    data = load(args.dataset)
    servers, domain = data.servers, data.domain
    targets_to_run = servers[: args.max_targets] if args.max_targets else servers
    config = {
        "dataset": args.dataset,
        "epsilons": epsilons,
        "seeds": seeds,
        "targets": targets_to_run,
        "users_per_source": USERS,
        "top_m": TOP_M,
        "top_k": TOP_K,
        "n_targets": N_TARGETS,
        "methods": ["simple_average", "variance_weighted", "trimmed_frequency", "privedge"],
        "trim": 1,
        "kappa": KAPPA,
        "scenarios": [s[0] for s in SCENARIOS],
        "smoke_test": bool(args.max_targets or args.max_seeds),
        "prereg": "experiments_prereg/COMPARE_V1.md",
        "prereg_sha256": hashlib.sha256((Path(__file__).resolve().parents[2]
                                        / "experiments_prereg/COMPARE_V1.md").read_bytes()).hexdigest(),
    }
    run = Run(f"compare_v1_{args.dataset}", config, data.file_sha256)
    rows, started = [], time.time()

    for target in targets_to_run:
        target_index = servers.index(target)
        sources = [source for source in servers if source != target]
        truth_dist = data.distribution(target)
        truth = top_items(truth_dist, TOP_K)
        for seed in seeds:
            attack_targets = _attack_targets(data, sources, seed, target_index)
            order = np.random.default_rng(np.random.SeedSequence([seed, target_index, 777])).permutation(len(sources))
            sampled = {}
            for source in sources:
                srng = np.random.default_rng(np.random.SeedSequence([seed, servers.index(source), USERS, 17]))
                sampled[source] = data.events[source][srng.permutation(len(data.events[source]))[:USERS]]
            for epsilon in epsilons:
                epsilon_index = EPSILON_GRID.index(epsilon) if epsilon in EPSILON_GRID else epsilons.index(epsilon)
                honest = {
                    source: perturb(
                        sampled[source],
                        domain,
                        epsilon,
                        np.random.default_rng(np.random.SeedSequence([seed, servers.index(source), USERS, epsilon_index, 99])),
                    )
                    for source in sources
                }
                for scenario_name, kind, n_bad, beta in SCENARIOS:
                    bad = {sources[int(index)] for index in order[:n_bad]}
                    reports = {}
                    for source in sources:
                        if kind == "mga" and source in bad:
                            attack_rng = np.random.default_rng(
                                np.random.SeedSequence([seed, servers.index(source), 7, epsilon_index, int(beta * 1000)])
                            )
                            fake = mga_fake_reports(attack_targets, int(round(beta * USERS)), epsilon, attack_rng)
                            reports[source] = combine(honest[source], fake)
                        else:
                            reports[source] = honest[source]

                    raw_releases, defended_releases, defended_user_counts = [], [], []
                    for index, source in enumerate(sources):
                        raw_items, _raw_tail, _raw_filter, _raw_n = summarize_reports(
                            reports[source], domain, TOP_M, False
                        )
                        defended_items, _tail, _filter_report, defended_n = summarize_reports(
                            reports[source], domain, TOP_M, True
                        )
                        if source in bad and kind in {"compromised", "hijack"}:
                            raw_items = _poison_items(kind, raw_items, attack_targets)
                            defended_items = _poison_items(kind, defended_items, attack_targets)
                        raw_releases.append(_to_release(index, raw_items))
                        defended_releases.append(_to_release(index, defended_items))
                        defended_user_counts.append(defended_n)

                    baseline_predictions = {
                        "simple_average": fuse_average(raw_releases, TOP_K),
                        "variance_weighted": fuse_variance_weighted(raw_releases, TOP_K),
                        "trimmed_frequency": trimmed_frequency(raw_releases, TOP_K, trim=1),
                    }
                    privedge_prediction, state, reasons = _predict_privedge(
                        defended_releases, epsilon, defended_user_counts
                    )
                    predictions = baseline_predictions | {"privedge": privedge_prediction}
                    for method, prediction in predictions.items():
                        releases = defended_releases if method == "privedge" else raw_releases
                        metrics = evaluate(truth_dist, truth, prediction, set(prediction))
                        rows.append(
                            {
                                "target_server": target,
                                "seed": seed,
                                "epsilon": epsilon,
                                "scenario": scenario_name,
                                "method": method,
                                "attack_targets": ";".join(map(str, attack_targets)),
                                "bad_sources": ";".join(sorted(bad)),
                                "attack_success": len(set(attack_targets) & set(prediction)) / N_TARGETS,
                                "recall": metrics["recall"],
                                "ndcg": metrics["ndcg"],
                                "candidate_recall_upper_bound": candidate_recall_upper_bound(truth, candidate_set(releases)),
                                "state": state if method == "privedge" else "n/a",
                                "reasons": ";".join(reasons) if method == "privedge" else "",
                            }
                        )
            print(f"{target} seed={seed} done ({time.time() - started:.0f}s)", flush=True)

    run.write_rows("results.csv", rows)
    run.write_json("summary.json", summarize(rows))
    run.finish(["results.csv", "summary.json"])
    print(run.dir)


def summarize(rows: list[dict]) -> dict:
    per_target = defaultdict(list)
    for row in rows:
        per_target[(row["epsilon"], row["scenario"], row["method"], row["target_server"])].append(row)
    cells = defaultdict(dict)
    states = defaultdict(lambda: defaultdict(int))
    for (epsilon, scenario, method, target), target_rows in per_target.items():
        cells[(epsilon, scenario, method)][target] = {
            key: float(np.mean([row[key] for row in target_rows]))
            for key in ("attack_success", "recall", "ndcg", "candidate_recall_upper_bound")
        }
        if method == "privedge":
            for row in target_rows:
                states[(epsilon, scenario)][row["state"]] += 1

    table = []
    methods = ("simple_average", "variance_weighted", "trimmed_frequency", "privedge")
    for (epsilon, scenario), _ in sorted(states.items()):
        for method in methods:
            target_values = cells.get((epsilon, scenario, method), {})
            if not target_values:
                continue
            entry = {"epsilon": epsilon, "scenario": scenario, "method": method, "targets": len(target_values)}
            for key in ("attack_success", "recall", "ndcg", "candidate_recall_upper_bound"):
                entry[key] = round(float(np.mean([values[key] for values in target_values.values()])), 4)
            if method == "privedge":
                method_states = states[(epsilon, scenario)]
                total = sum(method_states.values())
                entry["states"] = dict(method_states)
                entry["refusal_rate"] = round(method_states.get("REFUSED", 0) / max(1, total), 4)
                for baseline in methods[:-1]:
                    baseline_values = cells.get((epsilon, scenario, baseline), {})
                    common = sorted(set(target_values) & set(baseline_values))
                    if not common:
                        continue
                    for key in ("attack_success", "recall", "ndcg"):
                        diffs = np.asarray([target_values[t][key] - baseline_values[t][key] for t in common])
                        entry[f"d_{key}_vs_{baseline}"] = round(float(diffs.mean()), 4)
                        entry[f"d_{key}_vs_{baseline}_ci95"] = _bootstrap(diffs)
            table.append(entry)
    return {"cells": table}


if __name__ == "__main__":
    main()
