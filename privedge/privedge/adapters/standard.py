"""Loader for datasets exported to the standard three-table layout."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


@dataclass
class StandardDataset:
    name: str
    categories: list[str]
    servers: list[str]
    events: dict[str, np.ndarray]
    contexts: dict[str, np.ndarray]
    snapshot_dates: dict[str, str]
    swapped: dict[str, str]
    meta: dict
    file_sha256: dict[str, str]

    @property
    def domain(self) -> int:
        return len(self.categories)

    def distribution(self, server: str) -> np.ndarray:
        counts = np.bincount(self.events[server], minlength=self.domain).astype(float)
        return counts / counts.sum()


def load(name: str) -> StandardDataset:
    folder = DATA_ROOT / name
    meta = json.loads((folder / "domain.json").read_text(encoding="utf-8"))
    categories = meta["categories"]
    index = {c: i for i, c in enumerate(categories)}
    servers = [s["server_id"] for s in meta["servers"]]
    hashes = {
        f: hashlib.sha256((folder / f).read_bytes()).hexdigest()
        for f in ("private_events.csv.gz", "public_context.csv")
        if (folder / f).exists()
    }
    if meta.get("file_sha256") and meta["file_sha256"] != hashes:
        raise ValueError(f"{name}: data files do not match recorded SHA-256")

    raw: dict[str, list[int]] = defaultdict(list)
    with gzip.open(folder / "private_events.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            raw[row["server_id"]].append(index[row["category"]])
    contexts: dict[str, np.ndarray] = {}
    if (folder / "public_context.csv").exists():
        contexts = {s: np.zeros(len(categories)) for s in servers}
        with (folder / "public_context.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                contexts[row["server_id"]][index[row["category"]]] = float(row["value"])
        for server, vector in contexts.items():
            total = vector.sum()
            contexts[server] = vector / total if total > 0 else vector
    return StandardDataset(
        name=name,
        categories=categories,
        servers=servers,
        events={s: np.asarray(raw[s], dtype=np.int64) for s in servers},
        contexts=contexts,
        snapshot_dates={s["server_id"]: s["snapshot_date"] for s in meta["servers"] if "snapshot_date" in s},
        swapped=meta.get("swapped_context", {}),
        meta=meta,
        file_sha256=hashes,
    )
