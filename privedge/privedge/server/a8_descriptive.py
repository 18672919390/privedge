"""Hash-bound descriptive four-method evidence, separate from preregistration-bound A8.

Original manifests are immutable. A review-time export never supplies a missing
historical preregistration hash or upgrades reused seeds to independent evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .a8_evidence import DATASETS, Cell, EvidenceError, Hash, StrictModel, Summary, _read_bound

ARCHIVE = Path(__file__).resolve().parents[2] / "evidence_registry" / "a8_descriptive"
REGISTRY = ARCHIVE / "registry.json"
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


class DescriptiveCell(Cell):
    refusal_rate: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class DescriptiveSummary(Summary):
    interpretation: Literal["DESCRIPTIVE"]
    source_run_id: str
    target_count: int = Field(gt=0)
    source_count: int = Field(ge=3)
    users_per_source: int = Field(gt=0)
    top_k: int = Field(gt=0)
    interval_unit: Literal["target_region"]
    limitations: list[str] = Field(min_length=3)
    cells: list[DescriptiveCell] = Field(min_length=1)

    @model_validator(mode="after")
    def sample_unit(self):
        if self.source_count != self.target_count - 1:
            raise ValueError("留一来源数与目标数不一致")
        if any(c.sample_count != self.target_count * len(c.seeds) for c in self.cells):
            raise ValueError("目标×种子样本数不一致")
        return self


class Entry(StrictModel):
    dataset: Literal["massive_steps", "olist_brazil", "meituan_trd"]
    source_run_id: str = Field(pattern=r"^compare_v1_[a-z0-9_]+-\d{8}T\d{6}Z-[0-9a-f]{6}$")
    review_id: str = Field(pattern=r"^review-\d{8}T\d{6}Z-[0-9a-f]{6}$")
    evidence_id: str = Field(pattern=r"^E[1-9][0-9]*$")
    source_manifest_sha256: Hash
    review_manifest_sha256: Hash
    summary_sha256: Hash
    audit_sha256: Hash
    exporter_sha256: Hash


class Registry(StrictModel):
    schema_version: Literal[1]
    interpretation: Literal["DESCRIPTIVE"]
    entries: list[Entry]

    @model_validator(mode="after")
    def unique_datasets(self):
        if len({e.dataset for e in self.entries}) != len(self.entries):
            raise ValueError("描述性登记数据集重复")
        return self


def _registered(entry: Entry) -> dict:
    source = Path("source_runs") / entry.source_run_id
    m = json.loads(_read_bound(ARCHIVE, source / "manifest.json", entry.source_manifest_sha256))
    if not isinstance(m, dict) or m.get("run_id") != entry.source_run_id or not m.get("finished_at"):
        raise EvidenceError("历史运行标识或完成状态不符")
    config, outputs = m.get("config"), m.get("outputs")
    if not isinstance(config, dict) or not isinstance(outputs, dict) or config.get("dataset") != entry.dataset:
        raise EvidenceError("历史运行配置不符")
    if entry.source_run_id.rsplit("-", 2)[0] != f"compare_v1_{entry.dataset}":
        raise EvidenceError("历史运行数据集不符")
    if m.get("experiment") != f"compare_v1_{entry.dataset}":
        raise EvidenceError("历史实验名不符")
    for name in ("results.csv", "summary.json"):
        _read_bound(ARCHIVE, source / name, _digest(outputs.get(name)))
    data = m.get("data_sha256")
    if not isinstance(data, dict) or not data or not all(isinstance(k, str) for k in data):
        raise EvidenceError("缺少输入数据指纹")
    for name, expected in data.items():
        _read_bound(DATA_ROOT / entry.dataset, Path(name), _digest(expected))
    review = json.loads(_read_bound(ARCHIVE, Path("source_review") / entry.review_id / "review_manifest.json", entry.review_manifest_sha256))
    if not isinstance(review, dict) or entry.source_run_id not in review.get("source_run_ids", []):
        raise EvidenceError("复核来源不符")
    artifacts = review.get("artifact_sha256")
    if not isinstance(artifacts, dict) or not artifacts:
        raise EvidenceError("复核清单缺失")
    for name, expected in artifacts.items():
        _read_bound(ARCHIVE / "source_review" / entry.review_id, Path(name), _digest(expected))
    audit = json.loads(_read_bound(ARCHIVE, Path("audit.json"), entry.audit_sha256))
    audit_run = audit.get("runs", {}).get(entry.dataset, {})
    if (audit.get("all_reaggregations_match") is not True or audit_run.get("run_id") != entry.source_run_id
            or audit_run.get("raw_csv_sha256") != outputs["results.csv"]):
        raise EvidenceError("独立复算记录不符")
    _read_bound(ARCHIVE, Path("exporter.py"), entry.exporter_sha256)
    summary = DescriptiveSummary.model_validate_json(_read_bound(ARCHIVE, Path("summaries") / f"{entry.dataset}.json", entry.summary_sha256))
    if (summary.dataset != entry.dataset or summary.source_run_id != entry.source_run_id
            or summary.target_count != len(config.get("targets", []))
            or summary.users_per_source != config.get("users_per_source") or summary.top_k != config.get("top_k")
            or any(c.top_m != config.get("top_m") for c in summary.cells)
            or any(sorted(c.seeds) != sorted(config.get("seeds", [])) for c in summary.cells)):
        raise EvidenceError("描述性摘要与历史运行不符")
    expected = {(float(e), s, m) for e in config.get("epsilons", [])
                for s in config.get("scenarios", []) for m in ("average", "variance_weighted", "robust_baseline", "privedge")}
    if {(c.epsilon, c.scenario, c.method) for c in summary.cells} != expected:
        raise EvidenceError("描述性摘要条件覆盖不符")
    return {"status": "DESCRIPTIVE", "evidence_id": entry.evidence_id,
            **summary.model_dump(exclude={"schema_version"}),
            "provenance": {"source_manifest_sha256": entry.source_manifest_sha256,
                           "source_results_sha256": outputs["results.csv"], "review_id": entry.review_id,
                           "summary_sha256": entry.summary_sha256, "audit_sha256": entry.audit_sha256,
                           "historical_preregistration_bound": False,
                           "started_at": m.get("started_at"), "finished_at": m.get("finished_at"),
                           "code_combined": m.get("code", {}).get("combined")}}


def _digest(value) -> str:
    # Apply the same exact digest shape even to untrusted historical metadata.
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise EvidenceError("非法文件指纹")
    return value


def descriptive_evidence() -> dict:
    datasets = {d: {"status": "NOT_REGISTERED", "methods": [], "cells": [],
                    "reason": "尚未登记描述性结果"} for d in DATASETS}
    try:
        registry = Registry.model_validate_json(REGISTRY.read_bytes())
    except (OSError, ValueError):
        return {"schema_version": 1, "interpretation": "DESCRIPTIVE", "status": "INVALID", "datasets": {
            d: {"status": "INVALID", "methods": [], "cells": [], "reason": "描述性登记无法读取"} for d in DATASETS}}
    for entry in registry.entries:
        try:
            datasets[entry.dataset] = _registered(entry)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            datasets[entry.dataset] = {"status": "INVALID", "methods": [], "cells": [],
                "reason": "描述性证据缺失或损坏，不显示数值", "source_run_id": entry.source_run_id}
    states = {d["status"] for d in datasets.values()}
    status = "INVALID" if "INVALID" in states else "AVAILABLE" if states == {"DESCRIPTIVE"} else "PARTIAL" if "DESCRIPTIVE" in states else "NOT_REGISTERED"
    return {"schema_version": 1, "interpretation": "DESCRIPTIVE", "status": status,
            "notice": "已核验原始产物的描述性比较；文件完整性不证明预注册时序或统计结论。", "datasets": datasets}
