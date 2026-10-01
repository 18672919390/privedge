"""Publisher key registry: which Ed25519 key may sign for which source or region."""

from __future__ import annotations

from dataclasses import dataclass, field

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def public_hex(key: Ed25519PublicKey) -> str:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


@dataclass
class KeyRegistry:
    """Maps key_id -> (public key, principal it may speak for, role)."""

    _keys: dict[str, tuple[Ed25519PublicKey, str, str]] = field(default_factory=dict)
    _revoked: set[str] = field(default_factory=set)

    def register(self, key_id: str, public_key: Ed25519PublicKey, principal: str, role: str) -> None:
        if key_id in self._keys:
            raise ValueError(f"key already registered: {key_id}")
        self._keys[key_id] = (public_key, principal, role)

    def revoke(self, key_id: str) -> None:
        self._revoked.add(key_id)

    def lookup(self, key_id: str) -> tuple[Ed25519PublicKey, str, str] | None:
        if key_id in self._revoked:
            return None
        return self._keys.get(key_id)

    def describe(self) -> list[dict]:
        return [
            {"key_id": key_id, "principal": principal, "role": role,
             "public_key": public_hex(key), "revoked": key_id in self._revoked}
            for key_id, (key, principal, role) in sorted(self._keys.items())
        ]


def check_signed(envelope, registry: KeyRegistry, principal: str, role: str) -> str | None:
    """Return a rejection code, or None if the key is registered for (principal, role) and the signature verifies."""
    from .envelope import verify_signature

    record = registry.lookup(envelope.key_id)
    if record is None:
        return "UNKNOWN_KEY"
    public_key, allowed_principal, key_role = record
    if allowed_principal != principal or key_role != role:
        return "PRINCIPAL_MISMATCH"
    if not verify_signature(envelope, public_key):
        return "SIGNATURE_INVALID"
    return None


@dataclass
class Identity:
    key_id: str
    principal: str
    role: str
    private_key: Ed25519PrivateKey

    @staticmethod
    def create(principal: str, role: str) -> "Identity":
        return Identity(f"{role}:{principal}", principal, role, Ed25519PrivateKey.generate())

    def enroll(self, registry: KeyRegistry) -> None:
        registry.register(self.key_id, self.private_key.public_key(), self.principal, self.role)
