"""Pre-registered context-attack / three-state decision experiment (experiments_prereg/CONTEXT_V1.md)."""

from __future__ import annotations

import argparse
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import replace

import numpy as np

from ..adapters.standard import load
from ..algorithms import evaluate, fuse_censor_aware_item_context, fuse_robust_adaptive_context, top_items
from ..attacks import forge_context_values, swap_context
from ..decision import DecisionPolicy
from ..envelope import domain_hash, seal
from ..gateway import GatewayPolicy, to_server_release
from ..keys import Identity, KeyRegistry
from ..ldp import perturb
from ..ledger import BudgetPolicy, Ledger
from ..pipeline import ColdStartService, Publisher, publish_context
from .runner import Run
from .security_v1 import EPSILON_GRID, N_TARGETS, SEEDS, TOP_K, TOP_M, USERS, _bootstrap

WINDOW_START = {
    "massive_steps": {"2012-04-03": "2012-04-03T00:00:00Z", "2017-10-03": "2017-10-03T00:00:00Z"},
    "olist_brazil": {"2016-12-31": "2017-01-01", "2017-12-31": "2018-01-01"},
}
SNAPSHOT_STAMP = {"massive_steps": "{}T00:00:00Z", "olist_brazil": "{}"}
SCENARIOS = ["C0_correct", "C1_swapped", "C2_forged_unsigned", "C3_forged_signed", "C4_none",
             "R2_two_sources", "R3_three_sources"]
STALE_WINDOW = "previous-window"


def forged_values(context: np.ndarray, targets: list[int]) -> np.ndarray:
    values = context.copy()
    values[targets] = 1.5 * values.max()
    return values / values.sum()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="massive_steps")
    parser.add_argument("--epsilons", default="1,2")
    parser.add_argument("--max-targets", type=int, default=0, help="smoke-test only")
    parser.add_argument("--max-seeds", type=int, default=0, help="smoke-test only")
    args = parser.parse_args()
    epsilons = [float(e) for e in args.epsilons.split(",")]
    seeds = SEEDS[: args.max_seeds] if args.max_seeds else SEEDS

    data = load(args.dataset)
    servers, domain = data.servers, data.domain
    targets_to_run = servers[: args.max_targets] if args.max_targets else servers
    dhash = domain_hash(data.categories, f"{args.dataset}-v1")
    window_of = {s["server_id"]: s.get("window", s["snapshot_date"]) for s in data.meta["servers"]}
    snapshot_of = {s: SNAPSHOT_STAMP[args.dataset].format(d) for s, d in data.snapshot_dates.items()}
    start_of = {s: WINDOW_START[args.dataset][d] for s, d in data.snapshot_dates.items()}

    registry = KeyRegistry()
    sources_id = {s: Identity.create(s, "source") for s in servers}
    context_id = {s: Identity.create(s, "context") for s in servers}
    for identity in [*sources_id.values(), *context_id.values()]:
        identity.enroll(registry)
    publishers = {s: Publisher(sources_id[s], dhash, domain) for s in servers}
    decision_policy = DecisionPolicy(k=TOP_K, report_m=TOP_M, weight_cap=None, clip_floor=None)

    config = {"dataset": args.dataset, "epsilons": epsilons, "seeds": seeds, "targets": targets_to_run,
              "smoke_test": bool(args.max_targets or args.max_seeds), "users_per_source": USERS,
              "top_m": TOP_M, "top_k": TOP_K, "scenarios": SCENARIOS, "window_start": start_of,
              "decision_policy": decision_policy.__dict__, "prereg": "experiments_prereg/CONTEXT_V1.md",
              "publisher_defense": True}
    run = Run(f"context_v1_{args.dataset}", config, data.file_sha256)
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
            attack = sorted(int(x) for x in arng.choice(pool, size=N_TARGETS, replace=False))
            order = arng.permutation(len(sources))
            sampled = {}
            for source in sources:
                srng = np.random.default_rng(np.random.SeedSequence([seed, servers.index(source), USERS, 17]))
                sampled[source] = data.events[source][srng.permutation(len(data.events[source]))[:USERS]]
            for epsilon in epsilons:
                e_index = EPSILON_GRID.index(epsilon)
                ledger = Ledger(BudgetPolicy(max_epsilon_per_window=4.0, min_users=1000))
                service = ColdStartService(registry, ledger)
                releases = []
                for s in sources:
                    rng = np.random.default_rng(np.random.SeedSequence([seed, servers.index(s), USERS, e_index, 99]))
                    reports = perturb(sampled[s], domain, epsilon, rng)
                    releases.append(publishers[s].release(reports, TOP_M, window_of[s], ledger, defense=True))
                stale = {}
                for env in releases:
                    old = seal(replace(env, release_id=f"rel-{uuid.uuid4().hex[:12]}", window_id=STALE_WINDOW,
                                       nonce="", signature=""),
                               sources_id[env.source_id].key_id, sources_id[env.source_id].private_key)
                    ledger.append(old)
                    stale[env.source_id] = old
                contexts = {
                    s: publish_context(context_id[s], window_of[s], snapshot_of[s], data.contexts[s],
                                       "OpenStreetMap via ohsome (ODbL)", dhash, ledger)
                    for s in (target, data.swapped[target])
                }
                correct = contexts[target]
                bad_values = forged_values(data.contexts[target], attack)
                presented = {
                    "C0_correct": correct,
                    "C1_swapped": swap_context(correct, contexts[data.swapped[target]]),
                    "C2_forged_unsigned": forge_context_values(correct, tuple(float(v) for v in bad_values)),
                    "C3_forged_signed": publish_context(context_id[target], window_of[target], snapshot_of[target],
                                                        bad_values, "compromised context key", dhash, ledger),
                    "C4_none": None,
                    "R2_two_sources": correct,
                    "R3_three_sources": correct,
                }
                policy = GatewayPolicy(dhash, domain, frozenset(set(window_of.values())), target, start_of[target],
                                       max_epsilon=4.0, min_users=1000)
                all_releases = [to_server_release(i, env) for i, env in enumerate(releases)]
                for scenario in SCENARIOS:
                    ctx_env = presented[scenario]
                    submitted = releases
                    if scenario.startswith("R"):
                        keep = {sources[int(i)] for i in order[: int(scenario[1])]}
                        submitted = [env if env.source_id in keep else stale[env.source_id] for env in releases]
                    decision, _record = service.predict(submitted, ctx_env, policy, decision_policy)
                    admitted_ctx_status = _record["admission"]["context_status"]
                    outputs = {"privedge": decision.top_k}
                    if ctx_env is not None and not scenario.startswith("R"):
                        naive_ctx = np.maximum(np.asarray(ctx_env.values, dtype=float), 0.0)
                        naive_ctx = naive_ctx / naive_ctx.sum()
                        outputs["naive_censor_aware"] = fuse_censor_aware_item_context(all_releases, naive_ctx, TOP_M, TOP_K)
                        outputs["naive_robust_context"] = fuse_robust_adaptive_context(
                            all_releases, naive_ctx, TOP_M, TOP_K, min(3, len(all_releases)))
                    for system, pred in outputs.items():
                        pred = [int(i) for i in pred]
                        metrics = evaluate(truth_dist, truth, pred, set(pred)) if pred else {"recall": 0.0, "ndcg": 0.0}
                        rows.append({
                            "target_server": target, "seed": seed, "epsilon": epsilon, "scenario": scenario,
                            "system": system, "state": decision.state if system == "privedge" else "n/a",
                            "reasons": ";".join(r["code"] for r in decision.reasons) if system == "privedge" else "",
                            "alerts": ";".join(r["code"] for r in decision.alerts) if system == "privedge" else "",
                            "context_status": admitted_ctx_status,
                            "sources_accepted": len(_record["admission"]["accepted"]),
                            "rejected_codes": ";".join(sorted(r["code"] for r in _record["admission"]["rejected"])),
                            "attack_targets": ";".join(map(str, attack)),
                            "attack_success": len(set(attack) & set(pred)) / N_TARGETS,
                            "recall": metrics["recall"], "ndcg": metrics["ndcg"],
                            "ledger_chain_ok": _record["ledger_chain_ok"],
                        })
            print(f"{target} seed={seed} done ({time.time() - started:.0f}s)", flush=True)

    run.write_rows("results.csv", rows)
    run.write_json("summary.json", summarize(rows))
    run.finish(["results.csv", "summary.json"])
    print(run.dir)


def summarize(rows: list[dict]) -> dict:
    per_target = defaultdict(list)
    for r in rows:
        per_target[(r["epsilon"], r["scenario"], r["system"], r["target_server"])].append(r)
    cells = defaultdict(dict)
    states = defaultdict(Counter)
    for (eps, scen, system, target), rs in per_target.items():
        cells[(eps, scen, system)][target] = {k: float(np.mean([r[k] for r in rs])) for k in ("attack_success", "recall", "ndcg")}
        for r in rs:
            if system == "privedge":
                states[(eps, scen)][f"{r['state']}|{r['reasons']}|ctx={r['context_status']}"] += 1
    table = []
    for (eps, scen, system), targets in sorted(cells.items()):
        entry = {"epsilon": eps, "scenario": scen, "system": system, "targets": len(targets)}
        for k in ("attack_success", "recall", "ndcg"):
            entry[k] = round(float(np.mean([v[k] for v in targets.values()])), 4)
        if system == "privedge":
            entry["states"] = dict(states[(eps, scen)])
            for naive in ("naive_censor_aware", "naive_robust_context"):
                base = cells.get((eps, scen, naive))
                if base:
                    for k in ("ndcg", "attack_success"):
                        diffs = np.array([targets[t][k] - base[t][k] for t in targets])
                        entry[f"d_{k}_vs_{naive}"] = round(float(diffs.mean()), 4)
                        entry[f"d_{k}_vs_{naive}_ci95"] = _bootstrap(diffs)
        table.append(entry)
    return {"cells": table}


if __name__ == "__main__":
    main()
