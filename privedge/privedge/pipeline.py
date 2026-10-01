"""End-to-end roles: region publishers, context publisher, cold-start service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from .envelope import ContextEnvelope, ReleaseEnvelope, ReleaseItem, canonical_bytes, seal, sha256_hex, utc_now
from .gateway import GatewayPolicy, admit
from .keys import Identity, KeyRegistry
from .ldp import HASH_FAMILY, OLHReports, aggregate, perturb
from .ledger import Ledger
from .decision import Decision, DecisionPolicy, decide
from .robust import FilterReport, filter_fake_reports


def summarize_reports(
    reports: OLHReports, domain: int, top_m: int, defense: bool
) -> tuple[tuple[ReleaseItem, ...], float, FilterReport, int]:
    """Publisher-side estimation: optional fake-report filter, then Top-m items."""
    filter_report = FilterReport()
    if defense:
        reports, filter_report = filter_fake_reports(reports, domain, candidate_size=2 * top_m)
    estimate = aggregate(reports, domain)
    n = reports.n
    order = np.argsort(-estimate.counts, kind="stable")
    ids = order[:top_m]
    tail = max(0.0, float(estimate.counts[order[top_m]]) / n) if len(order) > top_m else 0.0
    items = tuple(
        ReleaseItem(int(i), max(0.0, float(estimate.counts[i])) / n, float(estimate.variances[i]) / n**2)
        for i in ids
    )
    return items, tail, filter_report, n


@dataclass
class Publisher:
    """A source region. Holds raw LDP reports; never exports them."""

    identity: Identity
    domain_hash: str
    domain_size: int

    @property
    def source_id(self) -> str:
        return self.identity.principal

    def collect(self, values: np.ndarray, epsilon: float, rng: np.random.Generator) -> OLHReports:
        return perturb(values, self.domain_size, epsilon, rng)

    def release(
        self,
        reports: OLHReports,
        top_m: int,
        window_id: str,
        ledger: Ledger,
        defense: bool = True,
    ) -> ReleaseEnvelope:
        ledger.check_budget(self.source_id, window_id, reports.epsilon)
        items, tail, filter_report, n = summarize_reports(reports, self.domain_size, top_m, defense)
        envelope = ReleaseEnvelope(
            release_id=f"rel-{uuid.uuid4().hex[:12]}",
            source_id=self.source_id,
            window_id=window_id,
            domain_hash=self.domain_hash,
            mechanism="OLH",
            hash_family=HASH_FAMILY,
            epsilon=reports.epsilon,
            n_users=n,
            top_m=top_m,
            items=items,
            tail_bound=tail,
            defense=filter_report.to_json() if defense else {"method": "none"},
        )
        sealed = seal(envelope, self.identity.key_id, self.identity.private_key)
        ledger.append(sealed)
        return sealed


def publish_context(
    identity: Identity,
    window_id: str,
    snapshot_date: str,
    values: np.ndarray,
    source: str,
    domain_hash: str,
    ledger: Ledger,
) -> ContextEnvelope:
    envelope = ContextEnvelope(
        context_id=f"ctx-{uuid.uuid4().hex[:12]}",
        region_id=identity.principal,
        window_id=window_id,
        snapshot_date=snapshot_date,
        source=source,
        domain_hash=domain_hash,
        values=tuple(float(v) for v in values),
    )
    sealed = seal(envelope, identity.key_id, identity.private_key)
    ledger.append(sealed)
    return sealed


@dataclass
class ColdStartService:
    registry: KeyRegistry
    ledger: Ledger
    audit_log: list[dict] = field(default_factory=list)

    def predict(
        self,
        releases: list[ReleaseEnvelope],
        context: ContextEnvelope | None,
        policy: GatewayPolicy,
        decision_policy: DecisionPolicy = DecisionPolicy(),
    ) -> tuple[Decision, dict]:
        admission = admit(releases, context, policy, self.registry, self.ledger)
        decision = decide(admission, decision_policy)
        chain_ok, bad = self.ledger.verify_chain()
        record = {
            "request_id": f"req-{uuid.uuid4().hex[:12]}",
            "at": utc_now(),
            "target_region": policy.target_region,
            "inputs": sorted(env.digest() for env in releases) + ([context.digest()] if context else []),
            "ledger_head": self.ledger.head,
            "ledger_chain_ok": chain_ok,
            "admission": admission.summary(),
            "decision": decision.to_json(),
        }
        record["record_hash"] = sha256_hex(canonical_bytes(record))
        self.audit_log.append(record)
        return decision, record
