"""Public, content-derived identifiers for exported demo evidence.

This identifies a local payload, not its author or a trusted signature. Only
explicit program/data paths are read; credentials and internal notes are absent.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tomllib

PROJECT = Path(__file__).resolve().parents[2]
DATA_FILES = {
    "meituan_trd": ("domain.json", "private_events.csv.gz"),
    "olist_brazil": ("domain.json", "private_events.csv.gz", "public_context.csv"),
    "massive_steps": ("domain.json", "private_events.csv.gz", "public_context.csv"),
}


def public_version(root: Path = PROJECT) -> dict:
    paths = list((root / "privedge").rglob("*.py"))
    paths += [p for p in (root / "web" / "dist").rglob("*") if p.is_file()]
    paths += [root / "pyproject.toml", root / "requirements.lock"]
    files = {}
    for path in sorted(paths):
        if path.is_file() and path.resolve().is_relative_to(root.resolve()):
            relative = path.relative_to(root).as_posix()
            if "__pycache__" not in path.parts:
                files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    data_hashes = {}
    for dataset, names in DATA_FILES.items():
        for name in names:
            path = root / "data" / dataset / name
            if path.is_file() and path.resolve().is_relative_to(root.resolve()):
                data_hashes[f"{dataset}/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with (root / "pyproject.toml").open("rb") as stream:
        application_version = tomllib.load(stream)["project"]["version"]
    return {
        "release_id": "E34",
        "application_version": application_version,
        "source_fingerprint_sha256": hashlib.sha256(encoded).hexdigest(),
        "fingerprint_file_count": len(files),
        "fingerprint_scope": "privedge/**/*.py + web/dist/** + pyproject.toml + requirements.lock; sorted relative-path SHA-256 map",
        "data_sha256": data_hashes,
    }
