"""Bridge to the team's original research core (byte-identical copies in research_core/)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent / "research_core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from fusion import (  # noqa: E402
    ServerRelease,
    _weighted_fusion as fuse_weighted,
    candidate_set,
    fuse_average,
    fuse_censor_aware_item_context,
    fuse_public_context_weighted,
    fuse_robust_adaptive_context,
    fuse_variance_weighted,
    release_consensus,
    release_uncertainty,
)
from ldp_protocols import olh as research_olh  # noqa: E402
from metrics import candidate_recall_upper_bound, evaluate, top_items  # noqa: E402

__all__ = [
    "ServerRelease",
    "candidate_set",
    "fuse_average",
    "fuse_censor_aware_item_context",
    "fuse_public_context_weighted",
    "fuse_robust_adaptive_context",
    "fuse_variance_weighted",
    "fuse_weighted",
    "release_consensus",
    "release_uncertainty",
    "research_olh",
    "candidate_recall_upper_bound",
    "evaluate",
    "top_items",
    "verify_core_integrity",
]


def verify_core_integrity() -> dict[str, bool]:
    """Check that research_core files still match the recorded SHA-256 values."""
    manifest = json.loads((CORE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    return {
        name: hashlib.sha256((CORE_DIR / name).read_bytes()).hexdigest() == digest
        for name, digest in manifest["files"].items()
    }
