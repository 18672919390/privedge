"""Pre-registered adaptive weight-hijack experiment (experiments_prereg/SECURITY_V3.md)."""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from dataclasses import replace

import numpy as np

from ..adapters.standard import load
from ..algorithms import evaluate, fuse_variance_weighted, top_items
from ..attacks import combine, mga_fake_reports, weight_hijack_items
from ..decision import DecisionPolicy, robust_top_k
from ..ldp import perturb
from ..pipeline import summarize_reports
from .runner import Run
from .security_v1 import EPSILON_GRID, N_TARGETS, SEEDS, TOP_K, TOP_M, USERS, _bootstrap, compromise, to_release

SCENARIOS = [
    ("clean", None, 0, 0.0),
    ("compromised_1src", "compromised", 1, 0.0),
    ("compromised_2src", "compromised", 2, 0.0),
    ("hijack_1src", "hijack", 1, 0.0),
    ("hijack_2src", "hijack", 2, 0.0),
    ("demote_1src", "demote", 1, 0.0),
    ("mga_1src_b0.10", "mga", 1, 0.10),
]
VARIANCE_SCALE, DEMOTE, KAPPA = 1e-4, 7, 2.0


def poison_items(kind: str, items, targets):
    if kind == "compromised":
        return compromise(items, targets)
    if kind == "hijack":
        return weight_hijack_items(items, targets, VARIANCE_SCALE)
    if kind == "demote":
        return weight_hijack_items(items, targets, VARIANCE_SCALE, demote=DEMOTE)
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="massive_steps")
    parser.add_argument("--epsilons", default="1,2")
    parser.add_argument("--max-targets", type=int, default=0, help="smoke-test only")
    parser.add_argument("--max-seeds", type=int, default=0, help="smoke-test only")
    parser.add_argument("--seeds", default="", help="comma-separated; default is the v2/v3 seed list")
    parser.add_argument("--tag", default="v3", help="run name prefix and prereg file (SECURITY_<TAG>.md)")
    parser.add_argument("--clip-floor", type=float, default=None, help="D4 clip floor (v4.1 default 0); adds a _floor suffix")
    args = parser.parse_args()
    epsilons = [float(e) for e in args.epsilons.split(",")]
    base_seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else SEEDS
    seeds = base_seeds[: args.max_seeds] if args.max_seeds else base_seeds

    data = load(args.dataset)
    servers, domain = data.servers, data.domain
    targets_to_run = servers[: args.max_targets] if args.max_targets else servers
    config = {"dataset": args.dataset, "epsilons": epsilons, "seeds": seeds, "targets": targets_to_run,
              "smoke_test": bool(args.max_targets or args.max_seeds), "users_per_source": USERS,
              "top_m": TOP_M, "top_k": TOP_K, "n_targets": N_TARGETS,
              "scenarios": [s[0] for s in SCENARIOS], "defenses": ["D0_none", "D3_both", "D4_capped"],
              "variance_scale": VARIANCE_SCALE, "demote": DEMOTE, "kappa": KAPPA, "d4_clip_floor": args.clip_floor,
              "prereg": f"experiments_prereg/SECURITY_{args.tag.upper()}.md"}
    suffix = "_floor" if args.clip_floor is not None else ""
    run = Run(f"security_{args.tag}{suffix}_{args.dataset}", config, data.file_sha256)
    d3 = DecisionPolicy(k=TOP_K, report_m=TOP_M, min_item_support=2, winsorize=True, clip_z=3.0, weight_cap=None, clip_floor=None)
    d4 = replace(d3, weight_cap=KAPPA, clip_floor=args.clip_floor)
    rows, started = [], time.time()

    for target in targets_to_run:
        t_index = servers.index(target)
        sources = [s for s in servers if s != target]
        truth_dist = data.distribution(target)
        truth = top_items(truth_dist, TOP_K)
        source_mean = np.mean([data.distribution(s) for s in sources], axis=0)
        pool = np.argsort(-source_mean, kind="stable")[30:80]
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
                summaries = {}
                for name, kind, n_bad, beta in SCENARIOS:
                    bad = {sources[int(i)] for i in order[:n_bad]}
                    for filter_on in (False, True):
                        releases = []
                        for index, s in enumerate(sources):
                            if kind == "mga" and s in bad:
                                frng = np.random.default_rng(np.random.SeedSequence(
                                    [seed, servers.index(s), 7, e_index, int(beta * 1000)]))
                                reports = combine(honest[s], mga_fake_reports(targets, int(round(beta * USERS)), epsilon, frng))
                                items = summarize_reports(reports, domain, TOP_M, filter_on)[0]
                            else:
                                key = (s, filter_on)
                                if key not in summaries:
                                    summaries[key] = summarize_reports(honest[s], domain, TOP_M, filter_on)[0]
                                items = summaries[key]
                            if s in bad:
                                items = poison_items(kind, items, targets)
                            releases.append(to_release(index, items))
                        arms = {"D0_none": None} if not filter_on else {"D3_both": d3, "D4_capped": d4}
                        for defense, policy in arms.items():
                            if policy is None:
                                prediction = fuse_variance_weighted(releases, TOP_K)
                            else:
                                prediction, _ = robust_top_k(releases, None, policy)
                            metrics = evaluate(truth_dist, truth, prediction, set(prediction))
                            rows.append({
                                "target_server": target, "seed": seed, "epsilon": epsilon, "scenario": name,
                                "defense": defense, "attack_targets": ";".join(map(str, targets)),
                                "bad_sources": ";".join(sorted(bad)),
                                "attack_success": len(set(targets) & set(prediction)) / N_TARGETS,
                                "recall": metrics["recall"], "ndcg": metrics["ndcg"],
                            })
            print(f"{target} seed={seed} done ({time.time() - started:.0f}s)", flush=True)

    run.write_rows("results.csv", rows)
    run.write_json("summary.json", summarize(rows))
    run.finish(["results.csv", "summary.json"])
    print(run.dir)


def summarize(rows: list[dict]) -> dict:
    per_target = defaultdict(lambda: defaultdict(list))
    for r in rows:
        per_target[(r["epsilon"], r["scenario"], r["defense"])][r["target_server"]].append(r)
    cells = {
        key: {t: {m: float(np.mean([r[m] for r in rs])) for m in ("attack_success", "recall", "ndcg")}
              for t, rs in targets.items()}
        for key, targets in per_target.items()
    }
    table = []
    for (eps, scen, dfn), targets in sorted(cells.items()):
        entry = {"epsilon": eps, "scenario": scen, "defense": dfn, "targets": len(targets)}
        for m in ("attack_success", "recall", "ndcg"):
            entry[m] = round(float(np.mean([v[m] for v in targets.values()])), 4)
        for ref in ("D0_none", "D3_both"):
            base = cells.get((eps, scen, ref))
            if base is None or ref == dfn:
                continue
            for m in ("attack_success", "ndcg", "recall"):
                diffs = np.array([targets[t][m] - base[t][m] for t in targets])
                entry[f"d_{m}_vs_{ref}"] = round(float(diffs.mean()), 4)
                entry[f"d_{m}_vs_{ref}_ci95"] = _bootstrap(diffs)
        clean = cells.get((eps, "clean", "D3_both"))
        if clean is not None and scen != "clean":
            diffs = np.array([targets[t]["ndcg"] - clean[t]["ndcg"] for t in targets])
            entry["d_ndcg_vs_clean_D3"] = round(float(diffs.mean()), 4)
            entry["d_ndcg_vs_clean_D3_ci95"] = _bootstrap(diffs)
        table.append(entry)
    return {"cells": table}


if __name__ == "__main__":
    main()
