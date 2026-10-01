"""One-off export of the preregistered Olist state x window servers into PrivEdge's standard tables.

Reuses the frozen selection and context functions of dataset_research/scripts/olist_*.py
(category order, event order and context vectors are identical to the recorded Gate E
diagnostic). Context is read from the cached ohsome responses; no network access.
User identifiers are never written.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "dataset_research" / "scripts"
OUT = Path(__file__).resolve().parents[2] / "data" / "olist_brazil"
sys.path.insert(0, str(SCRIPTS))

from olist_common import build_servers, load_frozen_mapping, load_tables  # noqa: E402
from olist_ldp_diagnostic import SWAPPED  # noqa: E402
from olist_phase2_context import fetch_context  # noqa: E402


def main() -> None:
    mapping = load_frozen_mapping()
    tables = load_tables()
    built = build_servers(tables)
    config = built["servers"]
    servers = [row["server"] for row in config]
    categories = sorted(tables["catalog"]["product_category_name_english"])
    events = built["events"]
    raw_scores, _audit, _meta = fetch_context(sorted({row["state"] for row in config}), mapping)

    OUT.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT / "private_events.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["server_id", "category"])
        for server in servers:
            for category in events[events["server"] == server]["category"]:
                writer.writerow([server, category])
    with (OUT / "public_context.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["server_id", "category", "value", "source", "snapshot_date"])
        for row in config:
            raw = raw_scores[(row["state"], row["snapshot"])]
            for category in categories:
                writer.writerow([row["server"], category, raw.get(category, 0.0),
                                 "OpenStreetMap via ohsome (ODbL)", row["snapshot"]])
    meta = {
        "dataset": "Olist Brazilian E-Commerce, state x window (CC BY-NC-SA 4.0)",
        "categories": categories,
        "servers": [
            {"server_id": row["server"], "state": row["state"], "window": row["window"],
             "snapshot_date": row["snapshot"], "users": int((events["server"] == row["server"]).sum())}
            for row in config
        ],
        "swapped_context": SWAPPED,
        "event_rule": "earliest non-cancelled order per customer_unique_id in window, category of order_item_id=1",
        "exported_from": "dataset_research/scripts/olist_common.py + olist_phase2_context.py",
        "gate_status": {"A": "conditional (Kaggle SHA-256 not yet verified)", "B": "pass", "C": "pass",
                        "D": "fail (context-specific gain may not be claimed)"},
        "user_identifiers_exported": False,
    }
    meta["file_sha256"] = {
        name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
        for name in ("private_events.csv.gz", "public_context.csv")
    }
    (OUT / "domain.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({s["server_id"]: s["users"] for s in meta["servers"]}), len(categories))


if __name__ == "__main__":
    main()
