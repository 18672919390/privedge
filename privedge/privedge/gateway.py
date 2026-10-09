"""Target-side admission control for release and context envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .algorithms import ServerRelease
from .envelope import ContextEnvelope, ReleaseEnvelope
from .keys import KeyRegistry, check_signed
from .ledger import Ledger, valid_epsilon, valid_user_count

REASONS = {
    "SIGNATURE_INVALID": "签名校验失败（内容被篡改或伪造）",
    "UNKNOWN_KEY": "发布密钥未注册或已吊销",
    "PRINCIPAL_MISMATCH": "密钥无权代表该数据源/区域，或密钥角色不符",
    "DOMAIN_MISMATCH": "类别域版本不一致",
    "STALE_WINDOW": "窗口不在允许范围（过期或重放旧摘要）",
    "REPLAYED": "同一摘要在本次请求中重复出现",
    "EQUIVOCATION": "同一数据源在本次请求中提交了多份不同摘要，全部拒收",
    "NOT_IN_LEDGER": "摘要未登记在账本中",
    "LEDGER_MISMATCH": "摘要内容与账本记录的摘要值不一致",
    "BUDGET_EXCEEDED": "该数据源该窗口的隐私预算已超限",
    "EPSILON_INVALID": "ε 不是正的有限数（负数、0、NaN 或无穷）",
    "EPSILON_TOO_LARGE": "单次发布 ε 超过策略上限",
    "TOO_FEW_USERS": "参与用户数低于下限",
    "MALFORMED": "字段不合法",
    "CONTEXT_REGION_MISMATCH": "公开上下文不属于目标区域",
    "CONTEXT_NOT_CAUSAL": "公开上下文快照晚于目标窗口开始时刻",
    "CONTEXT_MISSING": "未提供公开上下文",
}


@dataclass(frozen=True)
class GatewayPolicy:
    domain_hash: str
    domain_size: int
    allowed_windows: frozenset[str]
    target_region: str
    target_window_start: str
    max_epsilon: float = 4.0
    min_users: int = 1000


@dataclass
class AdmissionResult:
    accepted: list[ReleaseEnvelope] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    context: np.ndarray | None = None
    context_status: str = "CONTEXT_MISSING"

    def server_releases(self) -> list[ServerRelease]:
        return [to_server_release(index, env) for index, env in enumerate(self.accepted)]

    def summary(self) -> dict:
        return {
            "accepted": [env.source_id for env in self.accepted],
            "rejected": self.rejected,
            "context_status": self.context_status,
        }


def to_server_release(index: int, env: ReleaseEnvelope) -> ServerRelease:
    ordered = sorted(env.items, key=lambda item: (-item.frequency, item.category))
    return ServerRelease(
        index,
        env.mechanism,
        tuple(item.category for item in ordered),
        {item.category: item.frequency for item in ordered},
        {item.category: item.variance for item in ordered},
    )


def _check_release(env: ReleaseEnvelope, policy: GatewayPolicy, registry: KeyRegistry, ledger: Ledger) -> str | None:
    reason = check_signed(env, registry, env.source_id, "source")
    if reason:
        return reason
    if env.domain_hash != policy.domain_hash:
        return "DOMAIN_MISMATCH"
    if env.window_id not in policy.allowed_windows:
        return "STALE_WINDOW"
    if not valid_epsilon(env.epsilon):
        return "EPSILON_INVALID"
    if env.epsilon > policy.max_epsilon + 1e-12:
        return "EPSILON_TOO_LARGE"
    if not valid_user_count(env.n_users):
        return "MALFORMED"
    if env.n_users < policy.min_users:
        return "TOO_FEW_USERS"
    categories = [item.category for item in env.items]
    if not env.items or len(env.items) > policy.domain_size or len(set(categories)) != len(categories) or any(
        not (0 <= item.category < policy.domain_size) or not np.isfinite(item.frequency)
        or not np.isfinite(item.variance) or item.variance <= 0
        for item in env.items
    ):
        return "MALFORMED"
    entry = ledger.find(env.release_id)
    if entry is None:
        return "NOT_IN_LEDGER"
    if entry["envelope_digest"] != env.digest():
        return "LEDGER_MISMATCH"
    if not ledger.spent(env.source_id, env.window_id) <= ledger.policy.max_epsilon_per_window + 1e-12:
        return "BUDGET_EXCEEDED"
    return None


def _check_context(env: ContextEnvelope | None, policy: GatewayPolicy, registry: KeyRegistry, ledger: Ledger) -> str:
    if env is None:
        return "CONTEXT_MISSING"
    reason = check_signed(env, registry, env.region_id, "context")
    if reason:
        return reason
    if env.region_id != policy.target_region:
        return "CONTEXT_REGION_MISMATCH"
    if env.domain_hash != policy.domain_hash or len(env.values) != policy.domain_size:
        return "DOMAIN_MISMATCH"
    if env.snapshot_date > policy.target_window_start:
        return "CONTEXT_NOT_CAUSAL"
    entry = ledger.find(env.context_id)
    if entry is None:
        return "NOT_IN_LEDGER"
    if entry["envelope_digest"] != env.digest():
        return "LEDGER_MISMATCH"
    return "OK"


def admit(
    releases: list[ReleaseEnvelope],
    context: ContextEnvelope | None,
    policy: GatewayPolicy,
    registry: KeyRegistry,
    ledger: Ledger,
) -> AdmissionResult:
    result = AdmissionResult()
    seen_ids: set[str] = set()
    seen_nonces: set[str] = set()
    valid: list[ReleaseEnvelope] = []
    for env in releases:
        if env.release_id in seen_ids or env.nonce in seen_nonces:
            reason = "REPLAYED"
        else:
            reason = _check_release(env, policy, registry, ledger)
        seen_ids.add(env.release_id)
        seen_nonces.add(env.nonce)
        if reason:
            result.rejected.append({"release_id": env.release_id, "source_id": env.source_id,
                                    "code": reason, "reason": REASONS[reason]})
        else:
            valid.append(env)
    # Multi-source support counts principals, so a source may contribute at most one release.
    per_source: dict[str, int] = {}
    for env in valid:
        per_source[env.source_id] = per_source.get(env.source_id, 0) + 1
    for env in valid:
        if per_source[env.source_id] > 1:
            result.rejected.append({"release_id": env.release_id, "source_id": env.source_id,
                                    "code": "EQUIVOCATION", "reason": REASONS["EQUIVOCATION"]})
        else:
            result.accepted.append(env)
    result.context_status = _check_context(context, policy, registry, ledger)
    if result.context_status == "OK":
        vector = np.maximum(np.asarray(context.values, dtype=float), 0.0)
        total = vector.sum()
        result.context = vector / total if total > 0 else vector
    return result
