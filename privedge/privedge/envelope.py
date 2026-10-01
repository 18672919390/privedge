"""Signed release and context envelopes (canonical JSON + Ed25519)."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ENVELOPE_VERSION = "release-envelope-v1"
CONTEXT_VERSION = "context-envelope-v1"


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def domain_hash(categories: list[str] | tuple[str, ...], version: str) -> str:
    return sha256_hex(canonical_bytes({"categories": list(categories), "version": version}))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ReleaseItem:
    category: int
    frequency: float
    variance: float


@dataclass(frozen=True)
class ReleaseEnvelope:
    release_id: str
    source_id: str
    window_id: str
    domain_hash: str
    mechanism: str
    hash_family: str
    epsilon: float
    n_users: int
    top_m: int
    items: tuple[ReleaseItem, ...]
    tail_bound: float
    defense: dict = field(default_factory=dict)
    created_at: str = ""
    nonce: str = ""
    key_id: str = ""
    version: str = ENVELOPE_VERSION
    signature: str = ""

    def body(self) -> dict:
        data = asdict(self)
        data.pop("signature")
        data["items"] = [asdict(item) for item in self.items]
        return data

    def digest(self) -> str:
        return sha256_hex(canonical_bytes({**self.body(), "signature": self.signature}))

    def to_json(self) -> dict:
        return {**self.body(), "signature": self.signature}

    @staticmethod
    def from_json(data: dict) -> "ReleaseEnvelope":
        items = tuple(ReleaseItem(**item) for item in data["items"])
        return ReleaseEnvelope(**{**data, "items": items})


@dataclass(frozen=True)
class ContextEnvelope:
    context_id: str
    region_id: str
    window_id: str
    snapshot_date: str
    source: str
    domain_hash: str
    values: tuple[float, ...]
    created_at: str = ""
    nonce: str = ""
    key_id: str = ""
    version: str = CONTEXT_VERSION
    signature: str = ""

    def body(self) -> dict:
        data = asdict(self)
        data.pop("signature")
        data["values"] = list(self.values)
        return data

    def digest(self) -> str:
        return sha256_hex(canonical_bytes({**self.body(), "signature": self.signature}))

    def to_json(self) -> dict:
        return {**self.body(), "signature": self.signature}

    @staticmethod
    def from_json(data: dict) -> "ContextEnvelope":
        return ContextEnvelope(**{**data, "values": tuple(data["values"])})


Envelope = ReleaseEnvelope | ContextEnvelope


def seal(envelope: Envelope, key_id: str, private_key: Ed25519PrivateKey) -> Envelope:
    stamped = replace(
        envelope,
        key_id=key_id,
        created_at=envelope.created_at or utc_now(),
        nonce=envelope.nonce or secrets.token_hex(16),
        signature="",
    )
    signature = private_key.sign(canonical_bytes(stamped.body())).hex()
    return replace(stamped, signature=signature)


def verify_signature(envelope: Envelope, public_key: Ed25519PublicKey) -> bool:
    try:
        public_key.verify(bytes.fromhex(envelope.signature), canonical_bytes(envelope.body()))
        return True
    except (InvalidSignature, ValueError):
        return False
