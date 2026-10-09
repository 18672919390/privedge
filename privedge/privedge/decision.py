"""Three-state output: NORMAL / DEGRADED / REFUSED, always with reason codes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np

from .algorithms import (
    ServerRelease,
    candidate_set,
    fuse_censor_aware_item_context,
    fuse_variance_weighted,
    fuse_weighted,
)
from .gateway import AdmissionResult
from .robust import capped_weights, source_scores, winsorize_releases

NORMAL, DEGRADED, REFUSED = "NORMAL", "DEGRADED", "REFUSED"

REASONS = {
    "LEDGER_CORRUPTED": "账本哈希链校验失败（已登记记录被修改），停止预测",
    "INSUFFICIENT_SOURCES": "通过验证的数据源不足，拒绝输出",
    "INSUFFICIENT_CANDIDATES": "满足多源支持规则的候选类别不足 k 个",
    "SOURCE_ANOMALY": "数据源偏离共识（仅告警：区域间真实差异也会触发，影响由截尾与多源支持规则限制）",
    "CONTEXT_UNVERIFIED": "提交的公开上下文未通过验证，已弃用并改用仅摘要融合",
    "LOW_AGREEMENT": "数据源之间分歧过大，结果可信度低",
}


@dataclass(frozen=True)
class DecisionPolicy:
    k: int = 10
    report_m: int = 20
    min_sources: int = 3
    min_item_support: int = 2
    min_agreement: float = 0.2
    source_z_threshold: float = 4.0
    winsorize: bool = True
    clip_z: float = 3.0
    # SECURITY_V3/V4: kappa=2 cap on fusion weights; None reproduces the v2 fusion.
    weight_cap: float | None = 2.0
    # Lower clip for published frequencies; None reproduces the v2-v4 runs.
    clip_floor: float | None = 0.0


@dataclass
class Decision:
    state: str
    top_k: list[int] = field(default_factory=list)
    method: str = ""
    reasons: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    support: dict[int, int] = field(default_factory=dict)
    agreement: float = 0.0
    source_scores: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "state": self.state, "top_k": self.top_k, "method": self.method,
            "reasons": self.reasons, "alerts": self.alerts,
            "support": {str(k): v for k, v in self.support.items()},
            "agreement": round(self.agreement, 4), "source_scores": self.source_scores,
        }


def _reason(code: str) -> dict:
    return {"code": code, "reason": REASONS[code]}


def mean_agreement(releases: list[ServerRelease]) -> float:
    pairs = [
        len(set(a.top_items) & set(b.top_items)) / max(1, len(set(a.top_items) | set(b.top_items)))
        for a, b in combinations(releases, 2)
    ]
    return float(np.mean(pairs)) if pairs else 0.0


def item_support(releases: list[ServerRelease]) -> Counter:
    return Counter(item for release in releases for item in release.top_items)


def robust_top_k(
    releases: list[ServerRelease],
    context: np.ndarray | None,
    policy: DecisionPolicy,
) -> tuple[list[int], str]:
    """Consensus-winsorised fusion restricted to items published by >= min_item_support sources."""
    support = item_support(releases)
    if policy.winsorize:
        releases, _ = winsorize_releases(releases, clip_z=policy.clip_z, floor=policy.clip_floor)
    allowed = {item for item, count in support.items() if count >= policy.min_item_support}
    if context is not None:
        top = fuse_censor_aware_item_context(
            releases, context, policy.report_m, policy.k, candidate_items=allowed
        )
        return [int(i) for i in top], "censor_aware"
    if policy.weight_cap is None:
        ranked, method = fuse_variance_weighted(releases, len(candidate_set(releases))), "variance_weighted"
    else:
        weights = capped_weights(releases, policy.weight_cap)
        ranked, method = fuse_weighted(releases, weights, len(candidate_set(releases))), "variance_weighted_capped"
    return [int(i) for i in ranked if i in allowed][: policy.k], method


def decide(admission: AdmissionResult, policy: DecisionPolicy = DecisionPolicy()) -> Decision:
    releases = admission.server_releases()
    if len(releases) < policy.min_sources:
        return Decision(REFUSED, reasons=[_reason("INSUFFICIENT_SOURCES")])

    scores = source_scores(releases, z_threshold=policy.source_z_threshold)
    # Uncalibrated on heterogeneous regions (security_v1: ~2-4 of 6 honest Massive sources flagged),
    # so it must not change the output state.
    alerts = [_reason("SOURCE_ANOMALY")] if any(score.flagged for score in scores) else []
    reasons = []
    agreement = mean_agreement(releases)
    if agreement < policy.min_agreement:
        reasons.append(_reason("LOW_AGREEMENT"))
    if admission.context_status not in ("OK", "CONTEXT_MISSING"):
        reasons.append(_reason("CONTEXT_UNVERIFIED"))

    top, method = robust_top_k(releases, admission.context, policy)
    if len(top) < policy.k:
        return Decision(REFUSED, top_k=top, method=method,
                        reasons=reasons + [_reason("INSUFFICIENT_CANDIDATES")], alerts=alerts)
    support = item_support(releases)
    return Decision(
        DEGRADED if reasons else NORMAL,
        top_k=top,
        method=method,
        reasons=reasons,
        alerts=alerts,
        support={item: support[item] for item in top},
        agreement=agreement,
        source_scores=[
            {"source": admission.accepted[s.index].source_id, "score": round(s.score, 3),
             "worst_item": s.worst_item, "flagged": s.flagged}
            for s in scores
        ],
    )
