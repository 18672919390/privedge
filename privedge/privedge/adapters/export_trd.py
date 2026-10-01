"""Export Meituan TRD into PrivEdge's standard layout, following
dataset_research/TRD_PREREGISTRATION_20260929.md section 1. No context file (Gate C/D not applicable).
User identifiers are never written."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "dataset_research" / "downloads" / "candidates_20260929" / "meituan_trd"
OUT = Path(__file__).resolve().parents[2] / "data" / "meituan_trd"
UNKNOWN = "未知"
MIN_USERS = 5000


def main() -> None:
    read = lambda name: pd.read_csv(RAW / name, sep="\t", dtype=str)
    cols = ["user_id", "wm_order_id", "wm_poi_id", "aor_id", "order_timestamp"]
    train = read("orders_train.txt")
    test = read("orders_test_poi.txt").merge(read("orders_poi_test_label.txt")[["wm_order_id", "wm_poi_id"]],
                                             on="wm_order_id", how="left")
    orders = pd.concat([train[cols], test[cols]], ignore_index=True)
    pois = read("pois.txt")[["wm_poi_id", "primary_third_tag_name"]]
    categories = sorted(c for c in pois["primary_third_tag_name"].dropna().unique() if c != UNKNOWN)

    audit = {"order_rows": int(len(orders))}
    orders = orders[orders["aor_id"].notna() & (orders["aor_id"] != "NULL")].copy()
    audit["order_rows_with_aor"] = int(len(orders))
    orders["ts"] = pd.to_numeric(orders["order_timestamp"], errors="raise")
    first = orders.sort_values(["user_id", "ts", "wm_order_id"], kind="mergesort").drop_duplicates("user_id")
    audit["users_with_first_order"] = int(len(first))
    first = first.merge(pois.drop_duplicates("wm_poi_id"), on="wm_poi_id", how="left")
    category = first["primary_third_tag_name"]
    audit["dropped_poi_or_category_missing"] = int(category.isna().sum())
    audit["dropped_unknown_category"] = int((category == UNKNOWN).sum())
    first = first[category.notna() & (category != UNKNOWN)]
    audit["users_kept"] = int(len(first))

    sizes = first.groupby("aor_id").size()
    audit["users_per_aor"] = {k: int(v) for k, v in sizes.sort_index(key=lambda s: s.astype(int)).items()}
    servers = sorted((a for a in sizes.index if sizes[a] >= MIN_USERS), key=int)
    first = first[first["aor_id"].isin(servers)].sort_values(["aor_id", "user_id"], kind="mergesort")
    name = {a: f"商圈{a}" for a in servers}

    OUT.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT / "private_events.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["server_id", "category"])
        for aor, cat in zip(first["aor_id"], first["primary_third_tag_name"]):
            writer.writerow([name[aor], cat])
    meta = {
        "dataset": "Meituan Takeout Recommendation Dataset (Zenodo 8025855, CC BY 4.0), Beijing, 2021-03-01..28",
        "categories": categories,
        "servers": [{"server_id": name[a], "aor_id": a, "window": "2021-03", "users": int(sizes[a])} for a in servers],
        "swapped_context": {},
        "event_rule": "earliest order per user_id (order_timestamp, then wm_order_id); category = restaurant "
                      "primary_third_tag_name; user dropped if missing or 未知",
        "prereg": "dataset_research/TRD_PREREGISTRATION_20260929.md",
        "audit": audit,
        "user_identifiers_exported": False,
    }
    meta["file_sha256"] = {"private_events.csv.gz": hashlib.sha256((OUT / "private_events.csv.gz").read_bytes()).hexdigest()}
    (OUT / "domain.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"servers": len(servers), "domain": len(categories), **audit}, ensure_ascii=False))


if __name__ == "__main__":
    main()
