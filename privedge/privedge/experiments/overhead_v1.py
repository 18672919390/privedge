"""Latency / size overhead of each PrivEdge stage (synthetic Zipf data; no utility claims)."""

from __future__ import annotations

import argparse
import platform
import time
import tracemalloc

import numpy as np

from ..decision import DecisionPolicy
from ..envelope import canonical_bytes, domain_hash, verify_signature
from ..gateway import GatewayPolicy
from ..keys import Identity, KeyRegistry
from ..ldp import aggregate, perturb
from ..ledger import BudgetPolicy, Ledger
from ..pipeline import ColdStartService, Publisher, publish_context, summarize_reports
from ..robust import filter_fake_reports
from .runner import Run


def zipf(domain: int, rng: np.random.Generator) -> np.ndarray:
    weights = 1.0 / (np.arange(domain) + 1.0) ** 1.1
    weights *= rng.uniform(0.8, 1.2, size=domain)
    return weights / weights.sum()


def timed(fn, repeat: int):
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        out = fn()
        samples.append(time.perf_counter() - start)
    return out, float(np.median(samples)) * 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    grid_users = [5_000, 20_000, 100_000]
    grid_domain = [71, 156, 500]
    epsilon, top_m, n_sources = 1.0, 20, 6
    run = Run("overhead_v1", {"users": grid_users, "domain": grid_domain, "epsilon": epsilon, "top_m": top_m,
                              "sources": n_sources, "repeat": args.repeat,
                              "machine": {"platform": platform.platform(), "processor": platform.processor(),
                                          "python": platform.python_version()}}, {})
    rows = []
    for domain in grid_domain:
        for users in grid_users:
            rng = np.random.default_rng(0)
            dist = zipf(domain, rng)
            values = rng.choice(domain, size=users, p=dist)
            reports, t_perturb = timed(lambda: perturb(values, domain, epsilon, np.random.default_rng(1)), args.repeat)
            _, t_aggregate = timed(lambda: aggregate(reports, domain), args.repeat)
            _, t_filter = timed(lambda: filter_fake_reports(reports, domain, candidate_size=2 * top_m), args.repeat)
            tracemalloc.start()
            summarize_reports(reports, domain, top_m, True)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            dhash = domain_hash([f"c{i}" for i in range(domain)], "bench")
            registry, ledger = KeyRegistry(), Ledger(BudgetPolicy(max_epsilon_per_window=1e9, min_users=1000))
            publishers = []
            for s in range(n_sources):
                identity = Identity.create(f"src-{s}", "source")
                identity.enroll(registry)
                publishers.append(Publisher(identity, dhash, domain))
            ctx_identity = Identity.create("target", "context")
            ctx_identity.enroll(registry)
            env, t_release = timed(lambda: publishers[0].release(reports, top_m, "W1", ledger, defense=True), args.repeat)
            public_key = registry.lookup(env.key_id)[0]
            _, t_verify = timed(lambda: verify_signature(env, public_key), max(args.repeat, 50))
            envs = [p.release(reports, top_m, "W1", ledger, defense=False) for p in publishers]
            context = publish_context(ctx_identity, "W1", "2016-12-31", dist, "bench", dhash, ledger)
            policy = GatewayPolicy(dhash, domain, frozenset({"W1"}), "target", "2017-01-01", min_users=1000)
            service = ColdStartService(registry, ledger)
            _, t_predict = timed(lambda: service.predict(envs, context, policy, DecisionPolicy(k=10, report_m=top_m)),
                                 args.repeat)
            rows.append({
                "domain": domain, "users": users,
                "client_perturb_us_per_user": round(t_perturb * 1000 / users, 3),
                "publisher_aggregate_ms": round(t_aggregate, 2),
                "publisher_filter_ms": round(t_filter, 2),
                "publisher_release_total_ms": round(t_release, 2),
                "publisher_peak_mem_mb": round(peak / 2**20, 1),
                "raw_reports_bytes": int(reports.n * 12),
                "release_envelope_bytes": len(canonical_bytes(env.to_json())),
                "context_envelope_bytes": len(canonical_bytes(context.to_json())),
                "verify_signature_ms": round(t_verify, 3),
                "gateway_predict_6_sources_ms": round(t_predict, 2),
                "ledger_entries_at_predict": len(ledger.entries),
            })
            print(rows[-1], flush=True)
    run.write_rows("results.csv", rows)
    run.finish(["results.csv"])
    print(run.dir)


if __name__ == "__main__":
    main()
