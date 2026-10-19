"""Read explicitly registered A8 results; absent evidence never becomes a zero score.

This adapter does not run experiments or establish their scientific validity.
The registry binds a reviewed manifest and preregistration by hash. All paths are
derived from validated identifiers, never supplied as filesystem paths by clients.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
PREREG = ROOT / "experiments_prereg"
REGISTRY = ROOT / "evidence_registry" / "a8.json"
DATASETS = ("massive_steps", "olist_brazil", "meituan_trd")
METHODS = ("average", "variance_weighted", "robust_baseline", "privedge")
MethodId = Literal["average", "variance_weighted", "robust_baseline", "privedge"]
Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Registration(StrictModel):
    dataset: Literal["massive_steps", "olist_brazil", "meituan_trd"]
    run_id: str = Field(pattern=r"^a8_[a-z0-9_]+-\d{8}T\d{6}Z-[0-9a-f]{6}$")
    evidence_id: str = Field(pattern=r"^E[1-9][0-9]*$")
    prereg: str = Field(pattern=r"^[A-Za-z0-9_-]+\.md$")
    prereg_sha256: Hash
    manifest_sha256: Hash


class Registry(StrictModel):
    schema_version: Literal[1]
    runs: list[Registration]

    @model_validator(mode="after")
    def unique_datasets(self):
        if len({r.dataset for r in self.runs}) != len(self.runs):
            raise ValueError("每个数据集只允许一条当前登记")
        return self


class Method(StrictModel):
    id: MethodId
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    status: Literal["COMPLETED", "NOT_APPLICABLE"]
    reason: str | None = None

    @model_validator(mode="after")
    def explain_unavailable(self):
        if self.status == "NOT_APPLICABLE" and (self.id != "robust_baseline" or not self.reason or not self.reason.strip()):
            raise ValueError("仅外部鲁棒基线可不适配，且必须说明理由")
        return self


class Cell(StrictModel):
    method: MethodId
    epsilon: float = Field(gt=0, allow_inf_nan=False)
    top_m: int = Field(gt=0)
    scenario: str = Field(min_length=1)
    beta: float = Field(ge=0, le=1, allow_inf_nan=False)
    attackers: int = Field(ge=0)
    target_scope: str = Field(min_length=1)
    seeds: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    sample_count: int = Field(gt=0)
    ndcg: Score | None
    recall: Score | None
    attack_success: Score | None
    ndcg_ci95: tuple[Score, Score] | None = None
    recall_ci95: tuple[Score, Score] | None = None
    attack_success_ci95: tuple[Score, Score] | None = None
    missing_reason: str | None = None

    @model_validator(mode="after")
    def check_missing(self):
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("种子不能重复")
        if self.sample_count < len(self.seeds):
            raise ValueError("样本数不能少于种子数")
        if any(v is None for v in (self.ndcg, self.recall, self.attack_success)) and not (self.missing_reason and self.missing_reason.strip()):
            raise ValueError("缺失指标必须说明原因")
        for metric in ("ndcg", "recall", "attack_success"):
            interval = getattr(self, f"{metric}_ci95")
            mean = getattr(self, metric)
            if interval is not None and (mean is None or not interval[0] <= mean <= interval[1]):
                raise ValueError("区间必须包含对应指标均值")
        return self


class Summary(StrictModel):
    schema_version: Literal[1]
    dataset: Literal["massive_steps", "olist_brazil", "meituan_trd"]
    methods: list[Method]
    cells: list[Cell] = Field(min_length=1)

    @model_validator(mode="after")
    def check_comparison(self):
        if len(self.methods) != 4 or {m.id for m in self.methods} != set(METHODS):
            raise ValueError("必须定义四种方法")
        completed = {m.id for m in self.methods if m.status == "COMPLETED"}
        conditions: dict[tuple, dict[str, tuple]] = {}
        for cell in self.cells:
            if cell.method not in completed:
                raise ValueError("不适配方法不能包含结果")
            key = (cell.epsilon, cell.top_m, cell.scenario, cell.beta, cell.attackers, cell.target_scope)
            group = conditions.setdefault(key, {})
            if cell.method in group:
                raise ValueError("重复结果单元")
            group[cell.method] = (tuple(sorted(cell.seeds)), cell.sample_count)
        for group in conditions.values():
            if set(group) != completed or len(set(group.values())) != 1:
                raise ValueError("同条件方法覆盖、种子或样本数不一致")
        return self


class EvidenceError(ValueError):
    pass


def _read_bound(root: Path, relative: Path, expected: str | None = None) -> bytes:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise EvidenceError("登记路径越界")
    data = path.read_bytes()
    if expected is not None and hashlib.sha256(data).hexdigest() != expected:
        raise EvidenceError("证据文件哈希不一致")
    return data


def _registered(entry: Registration) -> dict:
    experiment = entry.run_id.rsplit("-", 2)[0]
    relative = Path(experiment) / entry.run_id
    manifest = json.loads(_read_bound(RUNS, relative / "manifest.json", entry.manifest_sha256))
    if not isinstance(manifest, dict):
        raise EvidenceError("manifest必须是对象")
    _read_bound(PREREG, Path(entry.prereg), entry.prereg_sha256)
    if manifest.get("run_id") != entry.run_id or manifest.get("experiment") != experiment or not manifest.get("finished_at"):
        raise EvidenceError("运行标识或完成状态不一致")
    config = manifest.get("config", {})
    if not isinstance(config, dict) or not isinstance(config.get("seeds"), list) or not config["seeds"] or any(type(s) is not int or s < 0 for s in config["seeds"]):
        raise EvidenceError("运行配置缺少合法种子列表")
    if config.get("dataset") != entry.dataset or config.get("prereg_sha256") != entry.prereg_sha256:
        raise EvidenceError("运行配置与登记不一致")
    if not all(manifest.get(k) for k in ("data_sha256", "code", "environment")):
        raise EvidenceError("缺少数据、代码或环境指纹")
    outputs = manifest.get("outputs", {})
    if not isinstance(outputs, dict):
        raise EvidenceError("输出哈希必须是对象")
    for name in ("summary.json", "results.csv"):
        digest = outputs.get(name)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise EvidenceError("缺少输出文件哈希")
    _read_bound(RUNS, relative / "results.csv", outputs["results.csv"])
    summary = Summary.model_validate_json(_read_bound(RUNS, relative / "summary.json", outputs["summary.json"]))
    if summary.dataset != entry.dataset or any(sorted(c.seeds) != sorted(config.get("seeds", [])) for c in summary.cells):
        raise EvidenceError("结果数据集或种子与运行配置不一致")
    return {"status": "REGISTERED", **entry.model_dump(), **summary.model_dump(exclude={"schema_version", "dataset"}),
            "provenance": {k: manifest[k] for k in ("started_at", "finished_at", "data_sha256", "code", "environment")}}


def a8_evidence() -> dict:
    """Reload on each request so a newly reviewed registration needs no process restart."""
    datasets = {d: {"status": "NOT_RUN", "reason": "尚未登记A8运行；不显示统计数值", "methods": [], "cells": []} for d in DATASETS}
    try:
        registry = Registry.model_validate_json(REGISTRY.read_bytes())
    except (OSError, ValueError, ValidationError):
        return {"schema_version": 1, "status": "INVALID", "reason": "A8登记表缺失或不合法", "datasets": {
            d: {"status": "INVALID", "reason": "登记表无法读取", "methods": [], "cells": []} for d in DATASETS}}
    for entry in registry.runs:
        try:
            datasets[entry.dataset] = _registered(entry)
        except (OSError, ValueError, TypeError, KeyError):
            datasets[entry.dataset] = {"status": "INVALID", "run_id": entry.run_id, "evidence_id": entry.evidence_id,
                                       "reason": "登记证据缺失、损坏或与接口约定不一致；请核对原文件", "methods": [], "cells": []}
    statuses = {d["status"] for d in datasets.values()}
    status = "INVALID" if "INVALID" in statuses else "READY" if statuses == {"REGISTERED"} else "PARTIAL" if "REGISTERED" in statuses else "NOT_RUN"
    return {"schema_version": 1, "status": status, "datasets": datasets}
