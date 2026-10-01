"""Pre-registered poisoning attack/defence experiment (experiments_prereg/SECURITY_V1.md, SECURITY_V2.md)."""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from dataclasses import replace

import numpy as np

from ..adapters.standard import load
from ..algorithms import (
    ServerRelease,
    evaluate,
    fuse_average,
    fuse_censor_aware_item_context,
    fuse_variance_weighted,
    top_items,
)
from ..attacks import combine, mga_fake_reports
from ..decision import DecisionPolicy, robust_top_k
from ..ldp import perturb
from ..pipeline import summarize_reports
from ..robust import source_scores
from .runner import Run

EPSILON_GRID = [0.5, 1.0, 2.0, 4.0]  # index used in the recorded seed layout
SEEDS = [101, 211, 307, 401, 503]
USERS, TOP_M, TOP_K, N_TARGETS = 5000, 20, 10, 3
SCENARIOS = [
    ("clean", None, 0, 0.0),
    ("mga_1src_b0.02", "mga", 1, 0.02),
    ("mga_1src_b0.05", "mga", 1, 0.05),
    ("mga_1src_b0.10", "mga", 1, 0.10),
    ("mga_2src_b0.05", "mga", 2, 0.05),
    ("compromised_1src", "compromised", 1, 0.0),
    ("compromised_2src", "compromised", 2, 0.0),
]
DEFENSES = {
    "D0_none": (False, False),
    "D1_publisher": (True, False),
    "D2_gateway": (False, True),
    "D3_both": (True, True),
}


def to_release(index: int, items) -> ServerRelease:
    return ServerRelease(index, "OLH", tuple(i.category for i in items),
                         {i.category: i.frequency for i in items}, {i.category: i.variance for i in items})


def compromise(items, targets: list[int]):
    top_value = max(i.frequency for i in items)
    median_var = float(np.median([i.variance for i in items]))
    from ..envelope import ReleaseItem
    injected = [ReleaseItem(int(t), top_value, median_var) for t in targets]
    kept = [i for i in items if i.category not in targets]
    return tuple(injected + kept)[: len(items)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="massive_steps")
    parser.add_argument("--epsilons", default="1,2")
    parser.add_argument("--max-targets", type=int, default=0, help="smoke-test only")
    parser.add_argument("--max-seeds", type=int, default=0, help="smoke-test only")
    parser.add_argument("--protocol", choices=["v1", "v2"], default="v1")
    parser.add_argument("--v41-policy", action="store_true",
                        help="gateway uses the v4.1 defaults (weight cap 2, clip floor 0); run name gets a _v41 suffix")
    args = parser.parse_args()
    epsilons = [float(e) for e in args.epsilons.split(",")]
    seeds = SEEDS[: args.max_seeds] if args.max_seeds else SEEDS
    v2 = args.protocol == "v2"
    primary = "variance_weighted" if v2 else "censor_aware"

    data = load(args.dataset)
    servers, domain = data.servers, data.domain
    targets_to_run = servers[: args.max_targets] if args.max_targets else servers
    config = {"dataset": args.dataset, "protocol": args.protocol, "primary_fusion": primary,
              "epsilons": epsilons, "seeds": seeds, "targets": targets_to_run,
              "smoke_test": bool(args.max_targets or args.max_seeds), "users_per_source": USERS,
              "top_m": TOP_M, "top_k": TOP_K, "n_targets": N_TARGETS,
              "scenarios": [s[0] for s in SCENARIOS], "defenses": list(DEFENSES),
              "prereg": f"experiments_prereg/SECURITY_{args.protocol.upper()}.md",
              "filter": {"candidate_size": 2 * TOP_M, "z_threshold": 6.0, "retain": 0.7},
              "gateway": {"clip_z": 3.0, "rel_floor": 0.25, "min_item_support": 2,
                          "weight_cap": 2.0 if args.v41_policy else None, "clip_floor": 0.0 if args.v41_policy else None}}
    suffix = "_v41" if args.v41_policy else ""
    run = Run(f"security_{args.protocol}{suffix}_{args.dataset}", config, data.file_sha256)
    policy = DecisionPolicy(k=TOP_K, report_m=TOP_M, min_item_support=2, winsorize=True, clip_z=3.0,
                            weight_cap=config["gateway"]["weight_cap"], clip_floor=config["gateway"]["clip_floor"])
    rows, started = [], time.time()

    for target in targets_to_run:
        t_index = servers.index(target)
        sources = [s for s in servers if s != target]
        truth_dist = data.distribution(target)
        truth = top_items(truth_dist, TOP_K)
        context = None if v2 else data.contexts[target]
        source_mean = np.mean([data.distribution(s) for s in sources], axis=0)
        ranked = np.argsort(-source_mean, kind="stable")
        pool = ranked[30:80]
        for seed in seeds:
            arng = np.random.default_rng(np.random.SeedSequence([seed, t_index, 4242]))
            targets = sorted(int(x) for x in arng.choice(pool, size=N_TARGETS, replace=False))
            order = arng.permutation(len(sources))
            sampled = {}
            for source in sources:
                srng = np.random.default_rng(np.random.SeedSequence([seed, servers.index(source), USERS, 17]))
                sampled[source] = data.events[source][srng.permutation(len(data.events[source]))[:USERS]]
            for epsilon in epsilons:
                e_index = EPSILON_GRID.index(epsilon)
                honest = {
                    s: perturb(sampled[s], domain, epsilon,
                               np.random.default_rng(np.random.SeedSequence([seed, servers.index(s), USERS, e_index, 99])))
                    for s in sources
                }
                for name, kind, n_bad, beta in SCENARIOS:
                    bad = {sources[int(i)] for i in order[:n_bad]}
                    reports, fake_counts = {}, {}
                    for s in sources:
                        if kind == "mga" and s in bad:
                            frng = np.random.default_rng(np.random.SeedSequence([seed, servers.index(s), 7, e_index, int(beta * 1000)]))
                            fake = mga_fake_reports(targets, int(round(beta * USERS)), epsilon, frng)
                            reports[s], fake_counts[s] = combine(honest[s], fake), fake.n
                        else:
                            reports[s], fake_counts[s] = honest[s], 0
                    for filter_on in (False, True):
                        releases, removed_fake, removed_honest, total_fake = [], 0, 0, 0
                        for index, s in enumerate(sources):
                            items, _tail, freport, _n = summarize_reports(reports[s], domain, TOP_M, filter_on)
                            if kind == "compromised" and s in bad:
                                items = compromise(items, targets)
                            releases.append(to_release(index, items))
                            if freport.removed_mask is not None:
                                n_honest = honest[s].n
                                removed_honest += int(freport.removed_mask[:n_honest].sum())
                                removed_fake += int(freport.removed_mask[n_honest:].sum())
                            total_fake += fake_counts[s]
                        scores = source_scores(releases, z_threshold=policy.source_z_threshold)
                        flagged = {sources[sc.index] for sc in scores if sc.flagged}
                        arms = dict(DEFENSES)
                        if v2 and kind != "mga":
                            arms |= {"D3_t1": (True, True), "D3_t3": (True, True)}
                        for defense, (need_filter, gateway_on) in arms.items():
                            if need_filter != filter_on:
                                continue
                            if gateway_on:
                                arm_policy = policy
                                if defense.startswith("D3_t"):
                                    arm_policy = replace(policy, min_item_support=int(defense[-1]))
                                prediction, _ = robust_top_k(releases, context, arm_policy)
                            elif v2:
                                prediction = fuse_variance_weighted(releases, TOP_K)
                            else:
                                prediction = fuse_censor_aware_item_context(releases, context, TOP_M, TOP_K)
                            predictions = {primary: prediction}
                            if defense == "D0_none":
                                predictions["average"] = fuse_average(releases, TOP_K)
                            for method, pred in predictions.items():
                                metrics = evaluate(truth_dist, truth, pred, set(pred))
                                rows.append({
                                    "target_server": target, "seed": seed, "epsilon": epsilon,
                                    "scenario": name, "defense": defense, "method": method,
                                    "attack_targets": ";".join(map(str, targets)),
                                    "bad_sources": ";".join(sorted(bad)),
                                    "attack_success": len(set(targets) & set(pred)) / N_TARGETS,
                                    "recall": metrics["recall"], "ndcg": metrics["ndcg"],
                                    "fake_reports": total_fake, "fake_removed": removed_fake,
                                    "honest_removed": removed_honest,
                                    "honest_reports": sum(honest[s].n for s in sources),
                                    "honest_reports_attacked": sum(honest[s].n for s in bad) if kind == "mga" else 0,
                                    "flagged_sources": ";".join(sorted(flagged)),
                                    "flagged_bad": len(flagged & bad), "flagged_good": len(flagged - bad),
                                })
            print(f"{target} seed={seed} done ({time.time() - started:.0f}s)", flush=True)

    run.write_rows("results.csv", rows)
    run.write_json("summary.json", summarize(rows, primary))
    run.finish(["results.csv", "summary.json"])
    print(run.dir)


def _bootstrap(values: np.ndarray, rounds: int = 2000) -> list[float]:
    rng = np.random.default_rng(0)
    means = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(rounds)]
    return [round(float(x), 4) for x in np.percentile(means, [2.5, 97.5])]


def summarize(rows: list[dict], primary: str = "censor_aware") -> dict:
    per_target = defaultdict(list)
    for r in rows:
        per_target[(r["epsilon"], r["scenario"], r["defense"], r["method"], r["target_server"])].append(r)
    cells = defaultdict(dict)
    for (eps, scen, dfn, method, target), rs in per_target.items():
        cells[(eps, scen, dfn, method)][target] = {
            k: float(np.mean([r[k] for r in rs])) for k in ("attack_success", "recall", "ndcg")
        } | {
            "fake_removed_rate": (sum(r["fake_removed"] for r in rs) / max(1, sum(r["fake_reports"] for r in rs))),
            "honest_removed_rate": sum(r["honest_removed"] for r in rs) / max(1, sum(r["honest_reports"] for r in rs)),
            "honest_removed_rate_attacked_source": sum(r["honest_removed"] for r in rs)
            / max(1, sum(r.get("honest_reports_attacked", 0) for r in rs)),
            "flagged_bad": float(np.mean([r["flagged_bad"] for r in rs])),
            "flagged_good": float(np.mean([r["flagged_good"] for r in rs])),
        }
    table = []
    for (eps, scen, dfn, method), targets in sorted(cells.items()):
        entry = {"epsilon": eps, "scenario": scen, "defense": dfn, "method": method, "targets": len(targets)}
        for k in ("attack_success", "recall", "ndcg", "fake_removed_rate", "honest_removed_rate",
                  "honest_removed_rate_attacked_source", "flagged_bad", "flagged_good"):
            entry[k] = round(float(np.mean([v[k] for v in targets.values()])), 4)
        base = cells.get((eps, scen, "D0_none", primary))
        if base and dfn != "D0_none":
            for k in ("attack_success", "ndcg", "recall"):
                diffs = np.array([targets[t][k] - base[t][k] for t in targets])
                entry[f"d_{k}_vs_D0"] = round(float(diffs.mean()), 4)
                entry[f"d_{k}_vs_D0_ci95"] = _bootstrap(diffs)
        table.append(entry)
    return {"cells": table}


if __name__ == "__main__":
    main()
