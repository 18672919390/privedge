"""Immutable run directories with a reproducibility manifest."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PACKAGE = Path(__file__).resolve().parents[1]
RUNS = PACKAGE.parent / "runs"


def code_fingerprint() -> dict[str, str]:
    files = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)
    per_file = {str(p.relative_to(PACKAGE.parent)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    combined = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in per_file.items()).encode()).hexdigest()
    return {"combined": combined, "files": per_file}


class Run:
    def __init__(self, experiment: str, config: dict, data_hashes: dict[str, str]):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{experiment}-{stamp}-{uuid.uuid4().hex[:6]}"
        self.dir = RUNS / experiment / self.run_id
        self.dir.mkdir(parents=True, exist_ok=False)
        self.manifest = {
            "run_id": self.run_id,
            "experiment": experiment,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "config": config,
            "data_sha256": data_hashes,
            "code": code_fingerprint(),
            "environment": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform()},
        }
        self._write_manifest()

    def _write_manifest(self) -> None:
        (self.dir / "manifest.json").write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_rows(self, name: str, rows: list[dict]) -> Path:
        path = self.dir / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def write_json(self, name: str, payload) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def finish(self, outputs: list[str]) -> None:
        self.manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.manifest["outputs"] = {
            name: hashlib.sha256((self.dir / name).read_bytes()).hexdigest() for name in outputs
        }
        self._write_manifest()
