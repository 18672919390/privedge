"""CPU-only, resumable validation on independent seeds for a 6-core desktop.

Run from any directory. Defaults: 512 items, 5,000 users/source, 8 sources,
20 independent one-round seeds, four processes. Original G1-G8 are preserved.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

# Set before importing NumPy, including in Windows spawn workers.
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np

from experiment import ExperimentConfig, run
from experiments.validation.validate_independent_seeds import _write_csv
from ldp_protocols import xxhash
from metrics import evaluate, top_items
from problem_definition import VisibilityContract
from simulation import make_problem

METRICS = ("recall", "ndcg", "coverage", "candidate_miss_mass")
METHODS = ("average", "variance_weighted", "trimmed_frequency", "rank_frequency", "context_only", "context_mixture", "context_weighted",
           "adaptive_context", "item_context", "adaptive_item_context",
           "censor_aware_item_context", "adaptive_censor_aware_item_context",
           "robust_adaptive_context", "censor_aware_item_context_augmented",
           "adaptive_censor_aware_item_context_augmented")
BASELINES = ("average", "variance_weighted", "trimmed_frequency", "rank_frequency", "context_mixture", "context_only")
BOOTSTRAPS = 10000


def build_cases(suite: str = "core") -> dict[str, ExperimentConfig]:
    base = ExperimentConfig(domain=512, users_per_server=5000, server_count=8,
                            top_k=10, adaptive_server_budget=4, rounds=1,
                            context_quality=0.25, mechanisms=("OLH", "MIXED"))
    cases = {
        "laptop_reference": replace(base, domain=128, users_per_server=1500,
                                    server_count=6, adaptive_server_budget=3),
        "desktop_weak": base,
        "desktop_strong": replace(base, context_quality=0.75),
        "desktop_no_context": replace(base, visibility=VisibilityContract(public_target_context=False)),
        "desktop_augmented": replace(base, context_candidate_ratio=2.0),
    }
    if suite == "extended":
        laptop = cases["laptop_reference"]
        cases.update({
            "users_only": replace(laptop, users_per_server=5000),
            "domain_only": replace(laptop, domain=512),
            "servers_only": replace(laptop, server_count=8, adaptive_server_budget=4),
            "desktop_budget_2": replace(base, adaptive_server_budget=2),
            "desktop_budget_8": replace(base, adaptive_server_budget=8),
            "desktop_misleading": replace(base, context_condition="misleading"),
            "desktop_poisoned": replace(base, source_condition="adversarial", affected_source_fraction=0.25),
            "desktop_report_3k": replace(base, report_ratio=3.0),
            "protocol_epsilon_1": replace(base, epsilon=1.0, mechanisms=("PEM", "GRR", "OUE", "OLH")),
            "protocol_epsilon_2": replace(base, mechanisms=("PEM", "GRR", "OUE", "OLH")),
            "protocol_epsilon_4": replace(base, epsilon=4.0, mechanisms=("PEM", "GRR", "OUE", "OLH")),
        })
    return cases


def independent_seeds(count: int) -> list[int]:
    # Fresh confirmatory seeds, unrelated to the old tuning/validation lists.
    return [int(s.generate_state(1)[0]) for s in np.random.SeedSequence(20260914).spawn(count)]


def run_seed(case: str, config: ExperimentConfig, seed: int) -> dict:
    started = time.perf_counter()
    # One fixed mechanism per call gives each mechanism the same initial RNG
    # seed regardless of scenario position. Methods within a scenario share releases.
    rows = []
    for scenario in config.mechanisms:
        rows.extend(run(replace(config, seed=seed, mechanisms=(scenario,))))
    if config.visibility.public_target_context:
        problem = make_problem(config.domain, config.server_count, config.context_quality,
                               np.random.default_rng(seed),
                               context_condition=config.context_condition,
                               source_condition=config.source_condition if config.source_condition in {"clean", "unrelated", "stale"} else "clean",
                               affected_source_fraction=config.affected_source_fraction)
        context_prediction = top_items(problem.public_target_context, config.top_k)
        for scenario in config.mechanisms:
            template = next(r for r in rows if r["scenario"] == scenario)
            candidates = set(context_prediction)
            # This baseline may use public catalog items outside source releases.
            scores = evaluate(problem.target, top_items(problem.target, config.top_k), context_prediction, candidates)
            rows.append({**template, "method": "context_only", **scores,
                         "candidate_size": len(candidates),
                         "source_candidate_size": 0, "context_added_candidate_count": len(candidates),
                         "reported_item_count": 0, "estimated_payload_bytes": 0,
                         "candidate_recall_upper_bound": scores["coverage"],
                         "candidate_miss_mass": float(1.0 - problem.target[context_prediction].sum())})
    return {"case": case, "seed": seed, "seconds": time.perf_counter() - started,
            "rows": [{"case": case, "seed": seed, **r} for r in rows]}


def interval(values: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    means = values[rng.integers(len(values), size=(BOOTSTRAPS, len(values)))].mean(axis=1)
    return tuple(float(x) for x in np.quantile(means, [0.025, 0.975]))


def sign_flip(deltas: np.ndarray, rng: np.random.Generator) -> float:
    """Exact for <=16 nonzero pairs, otherwise bounded Monte Carlo with +1 correction."""
    values = deltas[np.abs(deltas) > 1e-15]
    if not len(values):
        return 1.0
    observed = abs(values.sum())
    if len(values) <= 16:
        masks = np.arange(1 << len(values), dtype=np.uint64)[:, None]
        signs = 2.0 * ((masks >> np.arange(len(values), dtype=np.uint64)) & 1) - 1.0
        return float(np.mean(np.abs(signs @ values) >= observed - 1e-12))
    exceed = 0
    for _ in range(20):
        signs = 2 * rng.integers(2, size=(5000, len(values))) - 1
        exceed += int(np.sum(np.abs(signs @ values) >= observed - 1e-12))
    return (exceed + 1) / 100001


def analyze(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    rng = np.random.default_rng(2026091401)
    groups = {}
    for row in rows:
        if row["method"] in METHODS:
            key = (row["case"], row["scenario"], row["method"])
            records = groups.setdefault(key, {})
            if row["seed"] in records:
                raise ValueError("Each seed must have exactly one round per method/scenario")
            records[row["seed"]] = row
    summary, paired = [], []
    for (case, scenario, method), records in sorted(groups.items()):
        ordered = sorted(records)
        result = {"case": case, "scenario": scenario, "method": method, "independent_seeds": len(records)}
        for metric in METRICS:
            values = np.array([records[s][metric] for s in ordered])
            low, high = interval(values, rng)
            result.update({f"{metric}_mean": float(values.mean()), f"{metric}_ci95_low": low, f"{metric}_ci95_high": high})
        summary.append(result)
        for baseline in BASELINES:
            comparison = groups.get((case, scenario, baseline))
            if baseline == method or comparison is None:
                continue
            if set(records) != set(comparison):
                raise ValueError("Incomplete paired seeds")
            for metric in ("recall", "ndcg"):
                delta = np.array([records[s][metric] - comparison[s][metric] for s in ordered])
                low, high = interval(delta, rng)
                paired.append({"case": case, "scenario": scenario, "method": method,
                               "baseline": baseline, "metric": metric, "seed_pairs": len(delta),
                               "mean_delta": float(delta.mean()), "ci95_low": low, "ci95_high": high,
                               "wins": int(np.sum(delta > 1e-12)), "ties": int(np.sum(np.abs(delta) <= 1e-12)),
                               "losses": int(np.sum(delta < -1e-12)), "pvalue": sign_flip(delta, rng)})
    # One conservative family across all reported method/baseline/case/metric comparisons.
    previous = 0.0
    for rank, row in enumerate(sorted(paired, key=lambda x: x["pvalue"])):
        previous = max(previous, min(1.0, (len(paired) - rank) * row["pvalue"]))
        row["pvalue_holm"] = previous
    return summary, paired


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def execute(output: Path, cases: dict[str, ExperimentConfig], seeds: list[int], workers: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    sources = sorted(ROOT.glob("*.py")) + [Path(__file__).resolve(), ROOT / "experiments/validation/validate_independent_seeds.py", ROOT / "experiments/G1_competitive_baselines.py"]
    design = {"cases": {name: asdict(config) for name, config in cases.items()}, "seeds": seeds,
              "numpy": np.__version__, "python": platform.python_version(),
              "hash_backend": "xxhash-" + xxhash.VERSION if xxhash is not None else "fallback",
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "independent_unit": "one independently generated target/source problem per seed; scenarios are not pooled",
              "primary_comparison": "desktop_weak: censor_aware_item_context versus average; recall and NDCG",
              "inference": "10000 paired bootstrap resamples; exact sign flip <=16 nonzero pairs, else 100000 Monte Carlo; global Holm correction",
              "competitive_baselines": {"alpha": 0.5, "trim": 1, "gamma": 1.0, "parameter_selection": "fixed, not development-tuned", "trim_fallback_below_three_sources": "average"}}
    # Round-trip tuples into JSON arrays before comparing a resumed manifest.
    design = json.loads(json.dumps(design))
    manifest = output / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) != design:
        raise ValueError("Output belongs to different code/config/environment. Choose a fresh --output directory.")
    atomic_json(manifest, design)
    checkpoint = output / "checkpoints"
    checkpoint.mkdir(exist_ok=True)
    jobs, results = [], []
    for case, config in cases.items():
        config.validate()
        if config.rounds != 1:
            raise ValueError("Desktop statistical unit requires rounds=1")
        for seed in seeds:
            path = checkpoint / f"{case}_{seed}.json"
            if path.exists():
                results.append(json.loads(path.read_text(encoding="utf-8")))
            else:
                jobs.append((case, config, seed, path))
    started = time.perf_counter()
    total = len(jobs) + len(results)
    print(f"{total} seed/case jobs; {len(results)} cached; {workers} workers", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_seed, case, config, seed): path for case, config, seed, path in jobs}
        for future in as_completed(futures):
            result = future.result()
            atomic_json(futures[future], result)
            results.append(result)
            print(f"{len(results)}/{total}: {result['case']} seed={result['seed']} {result['seconds']:.1f}s", flush=True)
    raw = [r for result in sorted(results, key=lambda x: (x["case"], x["seed"])) for r in result["rows"]]
    summary, comparisons = analyze(raw)
    _write_csv(output / "round_results.csv", raw)
    _write_csv(output / "method_summary.csv", summary)
    _write_csv(output / "paired_comparisons.csv", comparisons)
    atomic_json(output / "runtime.json", {"workers": workers, "cpu": platform.processor(),
                                         "logical_cpus": os.cpu_count(), "elapsed_this_invocation_seconds": time.perf_counter() - started,
                                         "total_job_seconds": sum(r["seconds"] for r in results), "completed_jobs": len(results)})
    print(f"Complete: {output.resolve()}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("core", "extended"), default="core")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/desktop_core")
    args = parser.parse_args()
    if not 2 <= args.seeds <= 100 or not 1 <= args.workers <= 6:
        parser.error("Use 2..100 seeds and 1..6 workers (recommended: 20 seeds, 4 workers)")
    cases = build_cases(args.suite)
    if args.cases:
        if set(args.cases) - cases.keys():
            parser.error(f"Unknown cases. Available: {list(cases)}")
        cases = {name: cases[name] for name in args.cases}
    execute(args.output.resolve(), cases, independent_seeds(args.seeds), args.workers)


if __name__ == "__main__":
    main()
