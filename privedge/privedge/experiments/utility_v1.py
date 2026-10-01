"""Pre-registered privacy-utility and parameter sensitivity experiment (experiments_prereg/UTILITY_V1.md).

Signing and gateway admission do not change release contents (verified end-to-end in CONTEXT_V1), so this
experiment feeds unsigned envelopes straight into decide()."""

from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict

import numpy as np

from ..adapters.standard import load
from ..algorithms import candidate_recall_upper_bound, candidate_set, evaluate, fuse_average, fuse_variance_weighted, top_items
from ..decision import REFUSED, DecisionPolicy, decide
from ..envelope import ReleaseEnvelope
from ..gateway import AdmissionResult
from ..ldp import HASH_FAMILY, perturb
from ..pipeline import summarize_reports
from .runner import Run
from .security_v1 import EPSILON_GRID, SEEDS, TOP_K, USERS, _bootstrap, to_release

TOP_MS = [10, 20, 40]
SOURCE_COUNTS = [3, 5, 0]  # 0 = all sources


def envelope(source: str, items, epsilon: float, n: int, top_m: int) -> ReleaseEnvelope:
    return ReleaseEnvelope(f"rel-{source}", source, "W", "", "OLH", HASH_FAMILY, epsilon, n, top_m, items, 0.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="massive_steps")
    parser.add_argument("--max-targets", type=int, default=0, help="smoke-test only")
    parser.add_argument("--max-seeds", type=int, default=0, help="smoke-test only")
    parser.add_argument("--weight-cap", type=float, default=None,
                        help="supplementary run with the SECURITY_V4 fusion; default reproduces UTILITY_V1")
    args = parser.parse_args()
    seeds = SEEDS[: args.max_seeds] if args.max_seeds else SEEDS
    suffix = "" if args.weight_cap is None else "_capped"
    data = load(args.dataset)
    servers, domain = data.servers, data.domain
    targets_to_run = servers[: args.max_targets] if args.max_targets else servers
    config = {"dataset": args.dataset, "seeds": seeds, "targets": targets_to_run, "users_per_source": USERS,
              "epsilons": EPSILON_GRID, "top_ms": TOP_MS, "source_counts": ["3", "5", "all"],
              "source_count_grid": {"epsilons": [1.0, 2.0], "top_m": 20}, "top_k": TOP_K,
              "smoke_test": bool(args.max_targets or args.max_seeds), "prereg": "experiments_prereg/UTILITY_V1.md",
              "weight_cap": args.weight_cap}
    run = Run(f"utility_v1{suffix}_{args.dataset}", config, data.file_sha256)

    sampled, reports, summaries = {}, {}, {}

    def get_summary(source: str, seed: int, epsilon: float, top_m: int, defense: bool):
        key = (source, seed, epsilon, top_m, defense)
        if key not in summaries:
            rkey = (source, seed, epsilon)
            if rkey not in reports:
                skey = (source, seed)
                if skey not in sampled:
                    srng = np.random.default_rng(np.random.SeedSequence([seed, servers.index(source), USERS, 17]))
                    sampled[skey] = data.events[source][srng.permutation(len(data.events[source]))[:USERS]]
                prng = np.random.default_rng(
                    np.random.SeedSequence([seed, servers.index(source), USERS, EPSILON_GRID.index(epsilon), 99]))
                reports[rkey] = perturb(sampled[skey], domain, epsilon, prng)
            items, _tail, _f, n = summarize_reports(reports[rkey], domain, top_m, defense)
            summaries[key] = (items, n)
        return summaries[key]

    rows, started = [], time.time()
    for target in targets_to_run:
        t_index = servers.index(target)
        all_sources = [s for s in servers if s != target]
        truth_dist = data.distribution(target)
        truth = top_items(truth_dist, TOP_K)
        for seed in seeds:
            order = np.random.default_rng(np.random.SeedSequence([seed, t_index, 777])).permutation(len(all_sources))
            cells = [(e, m, 0) for e in EPSILON_GRID for m in TOP_MS]
            cells += [(e, 20, r) for e in (1.0, 2.0) for r in SOURCE_COUNTS if r]
            for epsilon, top_m, r in cells:
                sources = [all_sources[int(i)] for i in order[:r]] if r else all_sources
                reference = top_items(np.mean([data.distribution(s) for s in sources], axis=0), TOP_K)
                raw = [to_release(i, get_summary(s, seed, epsilon, top_m, False)[0]) for i, s in enumerate(sources)]
                envs = []
                for s in sources:
                    items, n = get_summary(s, seed, epsilon, top_m, True)
                    envs.append(envelope(s, items, epsilon, n, top_m))
                decision = decide(AdmissionResult(accepted=envs), DecisionPolicy(k=TOP_K, report_m=top_m, weight_cap=args.weight_cap, clip_floor=None))
                predictions = {
                    "nonprivate_source_mean": reference,
                    "average": fuse_average(raw, TOP_K),
                    "variance_weighted": fuse_variance_weighted(raw, TOP_K),
                    "privedge": [] if decision.state == REFUSED else decision.top_k,
                }
                upper = candidate_recall_upper_bound(truth, candidate_set(raw))
                for method, pred in predictions.items():
                    pred = [int(i) for i in pred]
                    metrics = evaluate(truth_dist, truth, pred, set(pred)) if pred else {"recall": 0.0, "ndcg": 0.0}
                    rows.append({
                        "target_server": target, "seed": seed, "epsilon": epsilon, "top_m": top_m,
                        "sources": r or len(all_sources), "source_grid": "all" if not r else str(r),
                        "method": method, "recall": metrics["recall"], "ndcg": metrics["ndcg"],
                        "candidate_recall_upper_bound": upper,
                        "state": decision.state if method == "privedge" else "n/a",
                        "reasons": ";".join(x["code"] for x in decision.reasons) if method == "privedge" else "",
                    })
        print(f"{target} done ({time.time() - started:.0f}s)", flush=True)

    run.write_rows("results.csv", rows)
    run.write_json("summary.json", summarize(rows))
    run.finish(["results.csv", "summary.json"])
    print(run.dir)


def summarize(rows: list[dict]) -> dict:
    per_target = defaultdict(list)
    for r in rows:
        per_target[(r["epsilon"], r["top_m"], r["source_grid"], r["method"], r["target_server"])].append(r)
    cells = defaultdict(dict)
    states = defaultdict(Counter)
    answered = defaultdict(lambda: defaultdict(list))
    for (eps, m, grid, method, target), rs in per_target.items():
        cells[(eps, m, grid, method)][target] = {k: float(np.mean([r[k] for r in rs]))
                                                 for k in ("recall", "ndcg", "candidate_recall_upper_bound")}
        if method == "privedge":
            for r in rs:
                states[(eps, m, grid)][r["state"]] += 1
                if r["state"] != REFUSED:
                    answered[(eps, m, grid)]["recall"].append(r["recall"])
                    answered[(eps, m, grid)]["ndcg"].append(r["ndcg"])
    table = []
    for (eps, m, grid, method), targets in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3])):
        entry = {"epsilon": eps, "top_m": m, "sources": grid, "method": method, "targets": len(targets)}
        for k in ("recall", "ndcg", "candidate_recall_upper_bound"):
            entry[k] = round(float(np.mean([v[k] for v in targets.values()])), 4)
        if method == "privedge":
            entry["states"] = dict(states[(eps, m, grid)])
            total = sum(entry["states"].values())
            entry["refusal_rate"] = round(entry["states"].get(REFUSED, 0) / total, 4)
            ans = answered[(eps, m, grid)]
            entry["answered_recall"] = round(float(np.mean(ans["recall"])), 4) if ans["recall"] else None
            entry["answered_ndcg"] = round(float(np.mean(ans["ndcg"])), 4) if ans["ndcg"] else None
            for base, metric in (("nonprivate_source_mean", "recall"), ("variance_weighted", "ndcg")):
                ref = cells[(eps, m, grid, base)]
                diffs = np.array([targets[t][metric] - ref[t][metric] for t in targets])
                entry[f"d_{metric}_vs_{base}"] = round(float(diffs.mean()), 4)
                entry[f"d_{metric}_vs_{base}_ci95"] = _bootstrap(diffs)
        table.append(entry)
    return {"cells": table}


if __name__ == "__main__":
    main()
