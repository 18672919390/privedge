"""One-off export of Massive-STEPS into PrivEdge's standard tables.

Reuses the event-selection and OSM-context functions of the recorded diagnostic
(dataset_research/scripts/massive_steps_ldp_diagnostic.py) so the exported data is
exactly what the recorded experiments used. Run with the research runtime that
has duckdb available. User identifiers are never written.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "dataset_research" / "scripts" / "massive_steps_ldp_diagnostic.py"
OUT = Path(__file__).resolve().parents[2] / "data" / "massive_steps"


def main() -> None:
    spec = importlib.util.spec_from_file_location("massive_diag", SCRIPT)
    diag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diag)

    events = diag.load_selected_events()
    contexts = diag.load_context_counts()
    categories = sorted({c for values in events.values() for c in values} | {c for v in contexts.values() for c in v})
    servers = [row["server"] for row in diag.SERVER_CONFIG]

    OUT.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT / "private_events.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["server_id", "category"])
        for server in servers:
            for category in events[server]:
                writer.writerow([server, category])
    with (OUT / "public_context.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["server_id", "category", "value", "source", "snapshot_date"])
        for row in diag.SERVER_CONFIG:
            for category in categories:
                writer.writerow([row["server"], category, contexts[row["server"]].get(category, 0),
                                 "OpenStreetMap via ohsome (ODbL)", row["snapshot"]])
    meta = {
        "dataset": "Massive-STEPS city x period (Foursquare check-ins)",
        "categories": categories,
        "servers": [
            {"server_id": row["server"], "city": row["city"], "window": row["collection"],
             "snapshot_date": row["snapshot"], "users": len(events[row["server"]])}
            for row in diag.SERVER_CONFIG
        ],
        "swapped_context": diag.SWAPPED,
        "event_rule": "one hash-selected check-in per user key (selection seed massive-steps-city-period-v1)",
        "exported_from": str(SCRIPT.relative_to(ROOT)),
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
