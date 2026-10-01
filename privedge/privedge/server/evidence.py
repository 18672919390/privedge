"""Read the registered experiment runs (competition_entry/docs/v4/02_实验证据登记.md) for the console.

Every number shown in the experiment centre comes from these files; nothing is typed in by hand."""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

RUNS = Path(__file__).resolve().parents[2] / "runs"
PREREG = Path(__file__).resolve().parents[2] / "experiments_prereg"

REGISTERED = {
    "utility": {"massive_steps": "utility_v1_massive_steps-20260929T031741Z-50e14d",
                "olist_brazil": "utility_v1_olist_brazil-20260929T031741Z-cf67da",
                "meituan_trd": "utility_v1_meituan_trd-20260929T031741Z-a520ee"},
    "security_v2": {"massive_steps": "security_v2_massive_steps-20260929T031029Z-1bd2f5",
                    "olist_brazil": "security_v2_olist_brazil-20260929T031029Z-1ed46e",
                    "meituan_trd": "security_v2_meituan_trd-20260929T031030Z-fd18bc"},
    "security_v4": {"massive_steps": "security_v4_massive_steps-20260929T145354Z-705ea4",
                    "olist_brazil": "security_v4_olist_brazil-20260929T145354Z-3c22fd",
                    "meituan_trd": "security_v4_meituan_trd-20260929T145355Z-8514ad"},
    "formal": "formal_v1-20260929T145230Z-a095ce",
    "overhead": "overhead_v1-20260928T190545Z-9aa625",
}
TITLES = {"massive_steps": "Massive-STEPS", "olist_brazil": "Olist", "meituan_trd": "美团 TRD"}


def _run_dir(run_id: str) -> Path:
    experiment = run_id.rsplit("-", 2)[0]
    return RUNS / experiment / run_id


def _summary(run_id: str) -> list[dict]:
    return json.loads((_run_dir(run_id) / "summary.json").read_text(encoding="utf-8"))["cells"]


@lru_cache(maxsize=1)
def evidence() -> dict:
    utility = {}
    for name, run_id in REGISTERED["utility"].items():
        cells = _summary(run_id)
        curve = {}
        for c in cells:
            if c["top_m"] == 20 and c["sources"] == "all":
                curve.setdefault(c["method"], {})[c["epsilon"]] = {"recall": c["recall"], "ndcg": c["ndcg"]}
        top_m = {m: {c["epsilon"]: c["recall"] for c in cells
                     if c["method"] == "privedge" and c["top_m"] == m and c["sources"] == "all"} for m in (10, 20, 40)}
        sources = {str(s): {c["epsilon"]: c["recall"] for c in cells
                            if c["method"] == "privedge" and c["top_m"] == 20 and str(c["sources"]) == str(s)}
                   for s in (3, 5, "all")}
        refusal = {f'{c["epsilon"]}|{c["top_m"]}|{c["sources"]}': c["refusal_rate"]
                   for c in cells if c["method"] == "privedge"}
        utility[name] = {"title": TITLES[name], "run_id": run_id, "curve": curve, "top_m": top_m,
                         "sources": sources, "refusal": refusal}

    security = {}
    for name, run_id in REGISTERED["security_v2"].items():
        rows = []
        for c in _summary(run_id):
            if c["method"] == "variance_weighted" and c["defense"] in ("D0_none", "D3_both"):
                rows.append({k: c.get(k) for k in ("epsilon", "scenario", "defense", "attack_success", "ndcg",
                                                    "fake_removed_rate", "honest_removed_rate_attacked_source",
                                                    "d_attack_success_vs_D0_ci95")})
        security[name] = {"title": TITLES[name], "run_id": run_id, "rows": rows}

    hijack = {}
    for name, run_id in REGISTERED["security_v4"].items():
        hijack[name] = {"title": TITLES[name], "run_id": run_id,
                        "rows": [{k: c.get(k) for k in ("epsilon", "scenario", "defense", "attack_success", "ndcg",
                                                         "d_ndcg_vs_D3_both_ci95")} for c in _summary(run_id)]}

    formal = json.loads((_run_dir(REGISTERED["formal"]) / "results.json").read_text(encoding="utf-8"))
    with (_run_dir(REGISTERED["overhead"]) / "results.csv").open(encoding="utf-8") as handle:
        overhead = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]

    return {"utility": utility, "security": security, "hijack": hijack,
            "formal": {"run_id": REGISTERED["formal"], **formal},
            "overhead": {"run_id": REGISTERED["overhead"], "rows": overhead}}


def prereg_documents() -> list[dict]:
    return [{"name": p.name, "text": p.read_text(encoding="utf-8")} for p in sorted(PREREG.glob("*.md"))]
