"""Independent validation and export for explicitly selected compare_v1 runs.

This module reads immutable source runs and writes all review artifacts under
``runs/compare_v1_review``. It does not import or modify experiment code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

RUNS = Path(__file__).resolve().parents[2] / "runs"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PREREG_RELATIVE = "experiments_prereg/COMPARE_V1.md"
PREREG_PATH = PACKAGE_ROOT / PREREG_RELATIVE
METHODS = ("simple_average", "variance_weighted", "trimmed_frequency", "privedge")
BASELINES = METHODS[:-1]
SEEDS = (101, 211, 307, 401, 503)
EPSILONS = (1.0, 2.0)
SCENARIOS = (
    "clean",
    "mga_1src_b0.02",
    "mga_1src_b0.05",
    "mga_1src_b0.10",
    "mga_2src_b0.05",
    "compromised_1src",
    "compromised_2src",
    "weight_hijack_1src",
    "weight_hijack_2src",
)
METRICS = ("attack_success", "recall", "ndcg", "candidate_recall_upper_bound")
PAIRED_METRICS = ("attack_success", "recall", "ndcg")
N_BOOTSTRAP = 2000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def preregistration_bound(config: dict) -> bool:
    """A path alone cannot bind a historical run to the reviewed preregistration.

    This necessary integrity check does not independently establish freeze time.
    Never add a digest to an old manifest to make this check pass.
    """
    expected = config.get("prereg_sha256")
    return (config.get("prereg") == PREREG_RELATIVE
            and isinstance(expected, str) and len(expected) == 64
            and PREREG_PATH.is_file() and sha256(PREREG_PATH) == expected)


def locate_run(run_id: str) -> Path:
    matches = list(RUNS.glob(f"compare_v1_*/{run_id}"))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one compare_v1 run named {run_id!r}; found {len(matches)}")
    return matches[0]


def bootstrap_ci(values: list[float] | np.ndarray) -> list[float | None]:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return [None, None]
    rng = np.random.default_rng(0)
    means = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(N_BOOTSTRAP)]
    return [float(x) for x in np.percentile(means, [2.5, 97.5])]


def read_source(run_id: str) -> tuple[Path, dict, list[dict], dict]:
    run_dir = locate_run(run_id)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"{run_id}: manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("run_id") != run_id:
        raise ValueError(f"{run_id}: manifest run_id does not match directory")
    if not manifest.get("finished_at"):
        raise ValueError(f"{run_id}: run is not marked finished")
    if manifest.get("experiment") != run_dir.parent.name:
        raise ValueError(f"{run_id}: experiment name does not match parent directory")
    config = manifest.get("config", {})
    if config.get("dataset") not in {"meituan_trd", "olist_brazil", "massive_steps"}:
        raise ValueError(f"{run_id}: unsupported or missing dataset in config")
    if not manifest.get("outputs", {}).get("results.csv"):
        raise ValueError(f"{run_id}: manifest has no results.csv digest")
    if not manifest.get("outputs", {}).get("summary.json"):
        raise ValueError(f"{run_id}: manifest has no summary.json digest")

    hash_checks = {}
    for name in ("results.csv", "summary.json"):
        path = run_dir / name
        actual = sha256(path) if path.is_file() else None
        expected = manifest["outputs"].get(name)
        hash_checks[name] = {"expected": expected, "actual": actual, "match": actual == expected}

    with (run_dir / "results.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "target_server", "seed", "epsilon", "scenario", "method", "attack_success",
        "recall", "ndcg", "candidate_recall_upper_bound", "state",
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"{run_id}: results.csv is empty or missing required columns")
    for line, row in enumerate(rows, start=2):
        try:
            row["seed"] = int(row["seed"])
            row["epsilon"] = float(row["epsilon"])
            for metric in METRICS:
                row[metric] = float(row[metric])
                if not math.isfinite(row[metric]):
                    raise ValueError(f"non-finite {metric}")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{run_id}: invalid numeric value at results.csv line {line}: {exc}") from exc
    original_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    return run_dir, manifest, rows, {"hashes": hash_checks, "original_summary": original_summary}


def check_grid(manifest: dict, rows: list[dict], allow_smoke: bool) -> dict:
    config = manifest["config"]
    expected = {
        "methods": list(METHODS),
        "seeds": list(SEEDS),
        "epsilons": list(EPSILONS),
        "scenarios": list(SCENARIOS),
    }
    checks = {key: {"expected": value, "actual": config.get(key), "match": config.get(key) == value}
              for key, value in expected.items()}
    targets = config.get("targets", [])
    dataset_meta_path = PACKAGE_ROOT / "data" / config["dataset"] / "domain.json"
    if dataset_meta_path.is_file():
        dataset_servers = [item["server_id"] for item in json.loads(dataset_meta_path.read_text(encoding="utf-8"))["servers"]]
    else:
        dataset_servers = []
    target_duplicates = len(targets) != len(set(targets))
    checks["targets"] = {
        "expected": dataset_servers,
        "actual": targets,
        "missing": sorted(set(dataset_servers) - set(targets)),
        "unexpected": sorted(set(targets) - set(dataset_servers)),
        "duplicate_count": len(targets) - len(set(targets)),
        "match": bool(dataset_servers) and not target_duplicates and set(targets) == set(dataset_servers),
    }
    smoke = bool(config.get("smoke_test"))
    checks["smoke_test"] = {"actual": smoke, "allowed": allow_smoke, "match": not smoke or allow_smoke}

    expected_keys = {
        (target, seed, epsilon, scenario, method)
        for target in targets for seed in config.get("seeds", [])
        for epsilon in config.get("epsilons", []) for scenario in config.get("scenarios", [])
        for method in config.get("methods", [])
    }
    actual_keys = [
        (row["target_server"], row["seed"], row["epsilon"], row["scenario"], row["method"])
        for row in rows
    ]
    actual_set = set(actual_keys)
    duplicates = len(actual_keys) - len(actual_set)
    missing = expected_keys - actual_set
    unexpected = actual_set - expected_keys
    checks["grid_rows"] = {
        "expected": len(expected_keys), "actual": len(rows), "duplicates": duplicates,
        "missing_count": len(missing), "unexpected_count": len(unexpected),
        "missing_examples": [list(k) for k in sorted(missing, key=str)[:10]],
        "unexpected_examples": [list(k) for k in sorted(unexpected, key=str)[:10]],
        "match": len(rows) == len(expected_keys) and not duplicates and not missing and not unexpected,
    }
    pair_counts: dict[tuple, set] = defaultdict(set)
    for row in rows:
        pair_counts[(row["target_server"], row["seed"], row["epsilon"], row["scenario"])].add(row["method"])
    broken_pairs = [(key, sorted(methods)) for key, methods in pair_counts.items() if methods != set(METHODS)]
    checks["paired_methods"] = {
        "expected_cells": len(targets) * len(config.get("seeds", [])) * len(config.get("epsilons", [])) * len(config.get("scenarios", [])),
        "actual_cells": len(pair_counts), "broken_count": len(broken_pairs),
        "examples": [{"cell": list(k), "methods": methods} for k, methods in broken_pairs[:10]],
        "match": not broken_pairs and len(pair_counts) == len(targets) * len(config.get("seeds", [])) * len(config.get("epsilons", [])) * len(config.get("scenarios", [])),
    }
    state_errors = []
    for row in rows:
        state = row["state"]
        if row["method"] == "privedge":
            if state not in {"NORMAL", "DEGRADED", "REFUSED"}:
                state_errors.append((row, "invalid PrivEdge state"))
            elif state == "REFUSED" and any(row[m] != 0.0 for m in ("recall", "ndcg", "attack_success")):
                state_errors.append((row, "refusal metrics are not zero"))
        elif state != "n/a":
            state_errors.append((row, "baseline state must be n/a"))
    checks["state_and_refusal_scoring"] = {
        "errors": len(state_errors),
        "examples": [{"target": r["target_server"], "seed": r["seed"], "scenario": r["scenario"], "reason": why}
                     for r, why in state_errors[:10]],
        "match": not state_errors,
    }
    checks["formal_grid"] = {
        "match": not smoke and all(checks[k]["match"] for k in expected) and checks["targets"]["match"] and checks["grid_rows"]["match"],
    }
    checks["valid_for_confirmatory_decision"] = (
        checks["formal_grid"]["match"] and checks["paired_methods"]["match"]
        and checks["state_and_refusal_scoring"]["match"] and not smoke
    )
    return checks


def build_statistics(rows: list[dict]) -> tuple[dict, list[dict], list[dict], list[dict]]:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    states: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        grouped[(row["epsilon"], row["scenario"], row["method"], row["target_server"])].append(row)
        if row["method"] == "privedge":
            states[(row["epsilon"], row["scenario"])][row["state"]] += 1

    target_cells: dict[tuple, dict[str, dict]] = defaultdict(dict)
    target_export = []
    for key, target_rows in grouped.items():
        epsilon, scenario, method, target = key
        entry = {
            "epsilon": epsilon, "scenario": scenario, "method": method, "target_server": target,
            "n_seeds": len(target_rows),
        }
        for metric in METRICS:
            entry[metric] = float(np.mean([r[metric] for r in target_rows]))
        if method == "privedge":
            answered = [r for r in target_rows if r["state"] != "REFUSED"]
            entry["refusal_rate"] = sum(r["state"] == "REFUSED" for r in target_rows) / max(1, len(target_rows))
            entry["answered_seeds"] = len(answered)
            entry["answered_recall"] = float(np.mean([r["recall"] for r in answered])) if answered else None
            entry["answered_ndcg"] = float(np.mean([r["ndcg"] for r in answered])) if answered else None
        else:
            entry["refusal_rate"] = None
            entry["answered_seeds"] = None
            entry["answered_recall"] = None
            entry["answered_ndcg"] = None
        target_cells[(epsilon, scenario, method)][target] = entry
        target_export.append(entry)

    summary_cells = []
    summary_csv = []
    paired_export = []
    for epsilon in sorted({r["epsilon"] for r in rows}):
        for scenario in sorted({r["scenario"] for r in rows}):
            for method in METHODS:
                by_target = target_cells.get((epsilon, scenario, method), {})
                if not by_target:
                    continue
                entry = {"epsilon": epsilon, "scenario": scenario, "method": method, "targets": len(by_target)}
                csv_entry = dict(entry)
                for metric in METRICS:
                    vals = [by_target[t][metric] for t in sorted(by_target)]
                    mean = float(np.mean(vals))
                    ci = bootstrap_ci(vals)
                    entry[metric] = round(mean, 4)
                    csv_entry[metric] = mean
                    csv_entry[f"{metric}_ci95_low"] = ci[0]
                    csv_entry[f"{metric}_ci95_high"] = ci[1]
                if method == "privedge":
                    state_counts = dict(states[(epsilon, scenario)])
                    total = sum(state_counts.values())
                    refusal_rows = [r for r in rows if r["epsilon"] == epsilon and r["scenario"] == scenario
                                    and r["method"] == "privedge"]
                    refusal_rate = sum(r["state"] == "REFUSED" for r in refusal_rows) / max(1, len(refusal_rows))
                    entry["states"] = state_counts
                    entry["refusal_rate"] = round(refusal_rate, 4)
                    csv_entry["refusal_rate"] = refusal_rate
                    answered_by_target = [by_target[t] for t in sorted(by_target) if by_target[t]["answered_seeds"]]
                    answered_seed_count = sum(item["answered_seeds"] for item in answered_by_target)
                    answered_target_means = {
                        "answered_recall": float(np.mean([item["answered_recall"] for item in answered_by_target])) if answered_by_target else None,
                        "answered_ndcg": float(np.mean([item["answered_ndcg"] for item in answered_by_target])) if answered_by_target else None,
                    }
                    entry.update({key: round(value, 4) if value is not None else None
                                  for key, value in answered_target_means.items()})
                    csv_entry.update(answered_target_means)
                    csv_entry["answered_seed_rows"] = answered_seed_count
                    csv_entry["answered_targets"] = len(answered_by_target)
                    for key, metric in (("answered_recall_ci95", "answered_recall"), ("answered_ndcg_ci95", "answered_ndcg")):
                        ci = bootstrap_ci([item[metric] for item in answered_by_target]) if answered_by_target else [None, None]
                        entry[key] = [round(x, 4) for x in ci] if ci[0] is not None else ci
                        csv_entry[f"{metric}_ci95_low"] = ci[0]
                        csv_entry[f"{metric}_ci95_high"] = ci[1]
                    for baseline in BASELINES:
                        base = target_cells.get((epsilon, scenario, baseline), {})
                        common = sorted(set(by_target) & set(base))
                        if not common:
                            continue
                        for metric in PAIRED_METRICS:
                            diffs = np.asarray([by_target[t][metric] - base[t][metric] for t in common])
                            entry[f"d_{metric}_vs_{baseline}"] = round(float(diffs.mean()), 4)
                            entry[f"d_{metric}_vs_{baseline}_ci95"] = [round(x, 4) for x in bootstrap_ci(diffs)]
                            csv_entry[f"d_{metric}_vs_{baseline}"] = float(diffs.mean())
                            ci = bootstrap_ci(diffs)
                            csv_entry[f"d_{metric}_vs_{baseline}_ci95_low"] = ci[0]
                            csv_entry[f"d_{metric}_vs_{baseline}_ci95_high"] = ci[1]
                            for target in common:
                                paired_export.append({
                                    "epsilon": epsilon, "scenario": scenario, "target_server": target,
                                    "metric": metric, "baseline": baseline,
                                    "privedge": by_target[target][metric], "baseline_value": base[target][metric],
                                    "difference": by_target[target][metric] - base[target][metric],
                                })
                summary_cells.append(entry)
                summary_csv.append(csv_entry)
    return {"cells": summary_cells}, target_export, summary_csv, paired_export


def compare_summaries(actual: dict, recomputed: dict) -> dict:
    actual_cells = actual.get("cells", [])
    expected_cells = recomputed.get("cells", [])
    keyed_actual = {(r.get("epsilon"), r.get("scenario"), r.get("method")): r for r in actual_cells}
    keyed_expected = {(r.get("epsilon"), r.get("scenario"), r.get("method")): r for r in expected_cells}
    issues = []
    if set(keyed_actual) != set(keyed_expected):
        issues.append({"kind": "cell_keys", "actual_count": len(keyed_actual), "recomputed_count": len(keyed_expected)})
    for key in sorted(set(keyed_actual) & set(keyed_expected), key=str):
        left, right = keyed_actual[key], keyed_expected[key]
        for field, value in right.items():
            if field.startswith("answered_"):
                continue
            if field not in left:
                issues.append({"kind": "missing_field", "key": list(key), "field": field})
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if left[field] != value:
                    issues.append({"kind": "value", "key": list(key), "field": field,
                                   "manifest_summary": left[field], "recomputed": value})
            elif left[field] != value:
                issues.append({"kind": "value", "key": list(key), "field": field,
                               "manifest_summary": left[field], "recomputed": value})
    return {"match": not issues, "issue_count": len(issues), "issues": issues[:30]}


def decisions(summary: dict, paired_rows: list[dict], admissible: bool) -> dict:
    by_key = {(r["epsilon"], r["scenario"], r["method"]): r for r in summary["cells"]}
    specs = [
        ("clean_utility_noninferiority", "clean", "trimmed_frequency", "ndcg", "lower_at_least", -0.02),
        ("mga_1src_b0.10_attack_reduction", "mga_1src_b0.10", "variance_weighted", "attack_success", "upper_below", 0.0),
        ("weight_hijack_1src_attack_reduction", "weight_hijack_1src", "variance_weighted", "attack_success", "upper_below", 0.0),
        ("weight_hijack_2src_attack_reduction", "weight_hijack_2src", "variance_weighted", "attack_success", "upper_below", 0.0),
    ]
    out = []
    for name, scenario, baseline, metric, criterion, threshold in specs:
        ours = by_key.get((2.0, scenario, "privedge"))
        theirs = by_key.get((2.0, scenario, baseline))
        if ours is None or theirs is None:
            out.append({"name": name, "status": "not_evaluable", "reason": "required result cell is missing"})
            continue
        diffs = [r["difference"] for r in paired_rows
                 if r["epsilon"] == 2.0 and r["scenario"] == scenario
                 and r["metric"] == metric and r["baseline"] == baseline]
        ci = bootstrap_ci(diffs) if diffs else None
        mean = float(np.mean(diffs)) if diffs else None
        passed = ci is not None and (ci[0] >= threshold if criterion == "lower_at_least" else ci[1] < threshold)
        out.append({
            "name": name, "epsilon": 2.0, "scenario": scenario, "metric": metric,
            "contrast": f"privedge - {baseline}", "mean_difference": mean, "ci95": ci,
            "criterion": f"{criterion} {threshold}",
            "status": ("supported" if passed else "not_supported_or_uncertain") if admissible else "inadmissible",
        })
    return {
        "source": "experiments_prereg/COMPARE_V1.md",
        "bootstrap": {"unit": "target_server", "rounds": N_BOOTSTRAP, "seed": 0, "interval": "percentile 95%"},
        "admissible": admissible,
        "note": "Answered-only utility is descriptive and is not used for confirmatory decisions.",
        "decisions": out,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def draw_svg(summary_rows: list[dict], dataset: str, path: Path) -> None:
    """Render epsilon=2 method means and target-bootstrap intervals with stdlib SVG."""
    scenarios = list(SCENARIOS)
    methods = list(METHODS)
    colors = {"simple_average": "#2563eb", "variance_weighted": "#dc2626",
              "trimmed_frequency": "#059669", "privedge": "#7c3aed"}
    labels = {"simple_average": "Simple average", "variance_weighted": "Variance weighted",
              "trimmed_frequency": "Trimmed frequency", "privedge": "PrivEdge"}
    scenario_labels = {
        "clean": "clean", "mga_1src_b0.02": "MGA1 b=.02", "mga_1src_b0.05": "MGA1 b=.05",
        "mga_1src_b0.10": "MGA1 b=.10", "mga_2src_b0.05": "MGA2 b=.05",
        "compromised_1src": "compromised1", "compromised_2src": "compromised2",
        "weight_hijack_1src": "hijack1", "weight_hijack_2src": "hijack2",
    }
    rows = [r for r in summary_rows if r["epsilon"] == 2.0]
    width, height = 1280, 780
    left, right = 80, 1220
    plot_w = right - left
    panel_top = (82, 420)
    panel_h = 240
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
              '<rect width="100%" height="100%" fill="white"/>',
              '<style>text{font-family:Arial,sans-serif;fill:#222} .small{font-size:11px} .axis{stroke:#555;stroke-width:1} .grid{stroke:#ddd;stroke-width:1}</style>',
              f'<text x="{width/2}" y="32" text-anchor="middle" font-size="20" font-weight="bold">{escape(dataset)}: four-method comparison (epsilon=2)</text>']
    for panel_idx, (metric, title) in enumerate((("ndcg", "NDCG@10"), ("attack_success", "Attack success rate"))):
        top = panel_top[panel_idx]
        bottom = top + panel_h
        pieces.append(f'<text x="{left}" y="{top-18}" font-size="15" font-weight="bold">{title}</text>')
        for tick in range(6):
            value = tick / 5
            y = bottom - value * panel_h
            pieces.append(f'<line class="grid" x1="{left}" x2="{right}" y1="{y:.1f}" y2="{y:.1f}"/>')
            pieces.append(f'<text class="small" x="{left-12}" y="{y+4:.1f}" text-anchor="end">{value:.1f}</text>')
        pieces.append(f'<line class="axis" x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}"/>')
        pieces.append(f'<line class="axis" x1="{left}" x2="{left}" y1="{top}" y2="{bottom}"/>')
        positions = [left + (i + 0.5) * plot_w / len(scenarios) for i in range(len(scenarios))]
        for x, scenario in zip(positions, scenarios):
            pieces.append(f'<text class="small" x="{x:.1f}" y="{bottom+18}" text-anchor="end" transform="rotate(-35 {x:.1f} {bottom+18})">{escape(scenario_labels[scenario])}</text>')
        for method in methods:
            points = []
            for i, scenario in enumerate(scenarios):
                row = next((r for r in rows if r["scenario"] == scenario and r["method"] == method), None)
                if row is None:
                    continue
                mean = float(row[metric])
                low = float(row[f"{metric}_ci95_low"])
                high = float(row[f"{metric}_ci95_high"])
                x = positions[i]
                y = bottom - max(0.0, min(1.0, mean)) * panel_h
                y_low = bottom - max(0.0, min(1.0, low)) * panel_h
                y_high = bottom - max(0.0, min(1.0, high)) * panel_h
                points.append((x, y))
                pieces.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y_low:.1f}" y2="{y_high:.1f}" stroke="{colors[method]}" stroke-width="1.5"/>')
                pieces.append(f'<line x1="{x-4:.1f}" x2="{x+4:.1f}" y1="{y_low:.1f}" y2="{y_low:.1f}" stroke="{colors[method]}"/>')
                pieces.append(f'<line x1="{x-4:.1f}" x2="{x+4:.1f}" y1="{y_high:.1f}" y2="{y_high:.1f}" stroke="{colors[method]}"/>')
                pieces.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{colors[method]}"/>')
            if points:
                coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
                pieces.append(f'<polyline points="{coords}" fill="none" stroke="{colors[method]}" stroke-width="2"/>')
    legend_y = 752
    legend_x = 330
    for method in methods:
        pieces.append(f'<line x1="{legend_x}" x2="{legend_x+24}" y1="{legend_y}" y2="{legend_y}" stroke="{colors[method]}" stroke-width="3"/>')
        pieces.append(f'<text x="{legend_x+30}" y="{legend_y+4}" font-size="12">{labels[method]}</text>')
        legend_x += 235
    pieces.append('<text x="80" y="775" class="small">Points: target means; whiskers: 2000 target-cluster bootstrap percentile 95% CI (seed=0). Refusal scores are zero.</text>')
    pieces.append("</svg>")
    path.write_text("\n".join(pieces), encoding="utf-8")


def process(run_id: str, out_dir: Path, allow_smoke: bool) -> dict:
    source_dir, manifest, rows, loaded = read_source(run_id)
    config = manifest["config"]
    grid = check_grid(manifest, rows, allow_smoke)
    recomputed, target_rows, summary_rows, paired_rows = build_statistics(rows)
    summary_check = compare_summaries(loaded["original_summary"], recomputed)
    hashes_ok = all(item["match"] for item in loaded["hashes"].values())
    dataset = config["dataset"]
    data_hash_checks = {}
    for name, expected_hash in manifest.get("data_sha256", {}).items():
        data_path = PACKAGE_ROOT / "data" / dataset / name
        actual_hash = sha256(data_path) if data_path.is_file() else None
        data_hash_checks[name] = {"expected": expected_hash, "actual": actual_hash, "match": actual_hash == expected_hash}
    data_hashes_ok = bool(data_hash_checks) and all(item["match"] for item in data_hash_checks.values())
    folder = out_dir / dataset
    folder.mkdir(parents=True, exist_ok=False)
    if PREREG_PATH.is_file():
        snapshot_path = folder / "preregistration_snapshot.md"
        snapshot_path.write_text(PREREG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        prereg_hash = sha256(snapshot_path)
    else:
        prereg_hash = None
    prereg_path_ok = preregistration_bound(config)
    admissible = bool(grid["valid_for_confirmatory_decision"] and hashes_ok and data_hashes_ok
                      and summary_check["match"] and prereg_path_ok)
    (folder / "independent_summary.json").write_text(json.dumps(recomputed, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(folder / "method_summary.csv", summary_rows)
    write_csv(folder / "target_method_summary.csv", target_rows)
    write_csv(folder / "paired_target_differences.csv", paired_rows)
    decision_report = decisions(recomputed, paired_rows, admissible)
    (folder / "confirmatory_decisions.json").write_text(json.dumps(decision_report, ensure_ascii=False, indent=2), encoding="utf-8")
    draw_svg(summary_rows, dataset, folder / "fig_epsilon2_comparison.svg")
    decision_lines = [
        f"| {d['name']} | {d.get('mean_difference')} | {d.get('ci95')} | {d['status']} |"
        for d in decision_report["decisions"]
    ]
    handoff = (
        f"# compare_v1 review handoff: {dataset}\n\n"
        f"Source run: `{run_id}`. Result hashes: `{hashes_ok}`; data hashes: `{data_hashes_ok}`; full registered grid: `{"true" if grid['formal_grid']['match'] else "false"}`; "
        f"original summary independently recomputed: `{summary_check['match']}`; confirmatory use: `{admissible}`.\n\n"
        f"Preregistration path in source manifest: `{config.get('prereg')}`; review-time SHA-256: `{prereg_hash}`. "
        f"Manifest preregistration digest: `{config.get('prereg_sha256')}`; binding matches: `{prereg_path_ok}`. "
        "A review-time snapshot does not independently prove pre-run freezing.\n\n"
        "`method_summary.csv` reports target-weighted means and target-cluster bootstrap intervals. "
        "`target_method_summary.csv` contains target-level, seed-averaged values and per-target refusal/answered-only statistics. "
        "`paired_target_differences.csv` contains the target-level paired contrasts for every method and metric. "
        "`independent_summary.json` reproduces the run summary and adds answered-only fields. "
        "The SVG plots epsilon=2 NDCG and attack success with target-cluster 95% intervals.\n\n"
        "Answered-only Recall/NDCG first average non-REFUSED seeds within each target, then average those targets equally. "
        "These values condition on PrivEdge answering and are descriptive only; they are excluded from confirmatory decisions. "
        "The registered headline utility still scores refusals as zero.\n\n"
        "## Preregistered decisions\n\n"
        "| Contrast | Mean difference | 95% CI | Decision |\n|---|---:|---:|---|\n"
        + "\n".join(decision_lines)
        + "\n\nAll decisions use unrounded target-level differences, 2,000 bootstrap replicates, seed 0. "
        "The full machine-readable checks and decisions are in `validation.json` and `confirmatory_decisions.json`.\n"
    )
    (folder / "handoff.md").write_text(handoff, encoding="utf-8")
    validation = {
        "source_run_id": run_id,
        "source_run_dir": str(source_dir),
        "dataset": dataset,
        "preregistration": {
            "manifest_config_path": config.get("prereg"),
            "manifest_config_sha256": config.get("prereg_sha256"),
            "binding_matches": prereg_path_ok,
            "expected_path": PREREG_RELATIVE,
            "current_file_sha256": sha256(PREREG_PATH) if PREREG_PATH.is_file() else None,
            "snapshot_sha256": prereg_hash,
            "path_matches": config.get("prereg") == PREREG_RELATIVE,
            "note": "A run must bind its preregistration digest. This check alone does not prove freeze time; never backfill a historical manifest.",
        },
        "source_hashes": loaded["hashes"],
        "data_hashes": data_hash_checks,
        "grid_checks": grid,
        "original_summary_recomputed_check": summary_check,
        "confirmatory_admissible": admissible,
        "answered_only_note": "Answered-only Recall/NDCG condition on non-REFUSED PrivEdge seeds. Descriptive only; not a preregistered confirmatory result.",
        "plot_dependency": "stdlib SVG; no matplotlib required",
        "artifact_files": ["independent_summary.json", "method_summary.csv", "target_method_summary.csv",
                           "paired_target_differences.csv", "confirmatory_decisions.json", "fig_epsilon2_comparison.svg",
                           "handoff.md", "preregistration_snapshot.md"],
    }
    (folder / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    return validation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_ids", nargs="+", help="explicit completed compare_v1 run IDs")
    parser.add_argument("--out-root", default=str(RUNS / "compare_v1_review"))
    parser.add_argument("--allow-smoke", action="store_true", help="export smoke runs, but mark all decisions inadmissible")
    args = parser.parse_args()
    if len(set(args.run_ids)) != len(args.run_ids):
        parser.error("run IDs must be unique")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    review_id = f"review-{stamp}-{uuid.uuid4().hex[:6]}"
    out_root = Path(args.out_root).resolve()
    review_dir = out_root / review_id
    review_dir.mkdir(parents=True, exist_ok=False)
    reports = []
    try:
        datasets = set()
        for run_id in args.run_ids:
            report = process(run_id, review_dir, args.allow_smoke)
            if report["dataset"] in datasets:
                raise ValueError(f"multiple runs for dataset {report['dataset']!r} in one review are ambiguous")
            datasets.add(report["dataset"])
            reports.append(report)
    except Exception as exc:
        (review_dir / "review_error.json").write_text(json.dumps({"error": str(exc), "processed": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    artifact_hashes = {}
    for path in sorted(review_dir.rglob("*")):
        if path.is_file() and path.name != "review_manifest.json":
            artifact_hashes[str(path.relative_to(review_dir)).replace("\\", "/")] = sha256(path)
    top_manifest = {
        "review_id": review_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_run_ids": args.run_ids,
        "preregistration": {
            "path": PREREG_RELATIVE,
            "current_file_sha256": sha256(PREREG_PATH) if PREREG_PATH.is_file() else None,
            "note": "Review-time hashing does not independently prove pre-run freezing; source manifests must bind the preregistration.",
        },
        "confirmatory_admissible_all": all(r["confirmatory_admissible"] for r in reports),
        "runs": [{"run_id": r["source_run_id"], "dataset": r["dataset"],
                  "confirmatory_admissible": r["confirmatory_admissible"]} for r in reports],
        "artifact_sha256": artifact_hashes,
    }
    (review_dir / "review_manifest.json").write_text(json.dumps(top_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(review_dir)
    for report in reports:
        print(f"{report['source_run_id']}: hashes={all(x['match'] for x in report['source_hashes'].values())}; "
              f"grid={report['grid_checks']['grid_rows']['match']}; summary={report['original_summary_recomputed_check']['match']}; "
              f"confirmatory_admissible={report['confirmatory_admissible']}")


if __name__ == "__main__":
    main()
