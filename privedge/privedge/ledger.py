"""Append-only hash-chained release ledger with privacy-budget accounting.

Budget model: each source window is one user population. Repeated releases over
the same population compose sequentially, so their epsilons add up; releases in
different windows cover disjoint user sets under the one-event-per-user rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .envelope import ContextEnvelope, ReleaseEnvelope, canonical_bytes, sha256_hex
from .keys import KeyRegistry, check_signed

GENESIS = "0" * 64


class LedgerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class BudgetPolicy:
    max_epsilon_per_window: float = 4.0
    min_users: int = 1000


@dataclass
class Ledger:
    policy: BudgetPolicy = field(default_factory=BudgetPolicy)
    # With a registry, only envelopes signed by the principal's own key can be logged, so a
    # third party cannot burn another source's privacy budget.
    registry: KeyRegistry | None = None
    entries: list[dict] = field(default_factory=list)
    _spent: dict[tuple[str, str], float] = field(default_factory=dict)
    _ids: set[str] = field(default_factory=set)
    _nonces: set[str] = field(default_factory=set)

    @property
    def head(self) -> str:
        return self.entries[-1]["entry_hash"] if self.entries else GENESIS

    def spent(self, source_id: str, window_id: str) -> float:
        return self._spent.get((source_id, window_id), 0.0)

    def check_budget(self, source_id: str, window_id: str, epsilon: float) -> None:
        total = self.spent(source_id, window_id) + epsilon
        if total > self.policy.max_epsilon_per_window + 1e-12:
            raise LedgerError(
                "BUDGET_EXCEEDED",
                f"{source_id}/{window_id} would spend {total:.3f} > {self.policy.max_epsilon_per_window}",
            )

    def append(self, envelope: ReleaseEnvelope | ContextEnvelope) -> dict:
        is_release = isinstance(envelope, ReleaseEnvelope)
        record_id = envelope.release_id if is_release else envelope.context_id
        if self.registry is not None:
            principal = envelope.source_id if is_release else envelope.region_id
            reason = check_signed(envelope, self.registry, principal, "source" if is_release else "context")
            if reason:
                raise LedgerError(reason, record_id)
        if record_id in self._ids:
            raise LedgerError("DUPLICATE_ID", record_id)
        if envelope.nonce in self._nonces:
            raise LedgerError("REPLAYED_NONCE", envelope.nonce)
        if is_release:
            if envelope.n_users < self.policy.min_users:
                raise LedgerError("TOO_FEW_USERS", f"{envelope.n_users} < {self.policy.min_users}")
            self.check_budget(envelope.source_id, envelope.window_id, envelope.epsilon)
        entry = {
            "seq": len(self.entries),
            "kind": "release" if is_release else "context",
            "record_id": record_id,
            "principal": envelope.source_id if is_release else envelope.region_id,
            "window_id": envelope.window_id,
            "epsilon": envelope.epsilon if is_release else 0.0,
            "envelope_digest": envelope.digest(),
            "created_at": envelope.created_at,
            "prev_hash": self.head,
        }
        entry["entry_hash"] = sha256_hex(canonical_bytes(entry))
        self.entries.append(entry)
        self._ids.add(record_id)
        self._nonces.add(envelope.nonce)
        if is_release:
            key = (envelope.source_id, envelope.window_id)
            self._spent[key] = self._spent.get(key, 0.0) + envelope.epsilon
        return entry

    def find(self, record_id: str) -> dict | None:
        for entry in self.entries:
            if entry["record_id"] == record_id:
                return entry
        return None

    def verify_chain(self) -> tuple[bool, int | None]:
        """Return (ok, first_bad_seq)."""
        prev = GENESIS
        for index, entry in enumerate(self.entries):
            body = {k: v for k, v in entry.items() if k != "entry_hash"}
            if entry["prev_hash"] != prev or sha256_hex(canonical_bytes(body)) != entry["entry_hash"]:
                return False, index
            prev = entry["entry_hash"]
        return True, None

    def budget_table(self) -> list[dict]:
        return [
            {"source_id": s, "window_id": w, "spent": round(v, 6),
             "limit": self.policy.max_epsilon_per_window}
            for (s, w), v in sorted(self._spent.items())
        ]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for entry in self.entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
