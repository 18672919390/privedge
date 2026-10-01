"""Shared runner for paper experiment groups; files contain configuration only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path
import re
from typing import Iterable

from experiment import ExperimentConfig, run, summarize, write_results


@dataclass(frozen=True)
class ExperimentCase:
    name: str
    description: str
    config: ExperimentConfig


def run_group(
    name: str, cases: Iterable[ExperimentCase], output_root: str = "outputs"
) -> None:
    root = Path(output_root) / name
    case_list = list(cases)
    group_rows: list[dict[str, object]] = []
    for case in case_list:
        if not re.fullmatch(r"[a-z0-9_]+", case.name):
            raise ValueError(f"invalid experiment case name: {case.name}")
        rows = run(case.config)
        output_dir = root / case.name
        write_results(rows, output_dir)
        metadata = {
            "group": name,
            "case": case.name,
            "description": case.description,
            "config": asdict(case.config),
        }
        with (output_dir / "config.json").open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2)
        print(f"{name}/{case.name}: {output_dir.resolve()}")
        case_summary = summarize(rows)
        for row in case_summary:
            group_rows.append(
                {
                    "group": name,
                    "case": case.name,
                    "description": case.description,
                    **row,
                }
            )
            if row["method"] in {
                "average",
                "adaptive_context",
                "robust_adaptive_context",
                "adaptive_item_context",
                "censor_aware_item_context",
                "adaptive_censor_aware_item_context",
            }:
                print(
                    f"  {row['scenario']:<6} {row['method']:<22} "
                    f"recall={row['recall']:.3f} ndcg={row['ndcg']:.3f} "
                    f"upper={row['candidate_recall_upper_bound']:.3f}"
                )

    root.mkdir(parents=True, exist_ok=True)
    with (root / "group_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(group_rows, handle, ensure_ascii=False, indent=2)
    if group_rows:
        with (root / "group_summary.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(group_rows[0]))
            writer.writeheader()
            writer.writerows(group_rows)

    manifest = {
        "group": name,
        "case_count": len(case_list),
        "cases": [
            {
                "name": case.name,
                "description": case.description,
                "config": asdict(case.config),
            }
            for case in case_list
        ],
    }
    with (root / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
