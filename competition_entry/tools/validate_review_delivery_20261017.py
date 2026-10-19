"""E34 predeclared API/seed/ledger verification; writes only a new evidence file."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "privedge"))
from fastapi.testclient import TestClient
from privedge.server.app import app

BASE = ROOT / "competition_entry/docs/v4/backend_validation/20261017_frontend_final"
OUT = ROOT / "competition_entry/docs/v4/backend_validation/20261017_review_delivery"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    destination = OUT / "api_acceptance.json"
    if destination.exists():
        raise FileExistsError(destination)
    checks = []
    result = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": checks,
              "purpose": "E34 engineering acceptance; no new statistical conclusion"}

    def check(name, passed, **detail):
        checks.append({"name": name, "passed": bool(passed), **detail})

    with TestClient(app) as client:
        result["version"] = client.get("/api/version").json()
        result["legal_inputs"] = {}
        for dataset, previous in read(BASE / "legal_input_comparison.json").items():
            response = client.post("/api/run", json=previous["request"])
            current = response.json()
            check(f"legal:{dataset}", response.status_code == 200 and all(
                current[key] == previous["response"][key] for key in ("decision", "evaluation")))
            result["legal_inputs"][dataset] = {"request": previous["request"], "response": current}
        result["evidence"] = {}
        for route, previous in read(BASE / "experiments-real-api.json").items():
            response = client.get(route)
            value = response.json()
            # New preregistrations are expected; registered scientific responses
            # stay identical, while every historical prereg must remain intact.
            unchanged = (all(item in value for item in previous)
                         if route == "/api/prereg" else value == previous)
            check(f"evidence:{route}", response.status_code == 200 and unchanged)
            result["evidence"][route] = {"identical": value == previous,
                "canonical_sha256": hashlib.sha256(json.dumps(value, sort_keys=True,
                    ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()}
        request = {"dataset": "meituan_trd", "target": "商圈3", "epsilon": 1,
                   "top_m": 20, "users": 5000, "seed": 20260929, "attackers": 1, "beta": .1}
        result["demo"] = {}
        for attack in ("none", "hijack", "tamper"):
            payload = {**request, "attack": attack}
            first = client.post("/api/run", json=payload).json()
            second = client.post("/api/run", json=payload).json()
            check(f"seed_replay:{attack}", all(first[key] == second[key]
                  for key in ("seed", "decision", "baseline", "evaluation")))
            result["demo"][attack] = {"request": payload, "first": first, "replay": second}
        check("tamper_gateway_rejection", any(e.get("code") == "SIGNATURE_INVALID"
              for e in result["demo"]["tamper"]["first"]["events"]))
        result["sweep"] = {}
        for attack in ("mga", "compromised", "hijack", "demote", "negative", "tamper",
                       "replay", "equivocation", "impostor", "budget_burn"):
            response = client.post("/api/run", json={**request, "attack": attack})
            value = response.json()
            check(f"sweep:{attack}", response.status_code == 200 and
                  value.get("decision", {}).get("state") in {"NORMAL", "DEGRADED", "REFUSED"})
            result["sweep"][attack] = value
        before = client.get("/api/ledger/meituan_trd").json()
        drill = client.post("/api/ledger/meituan_trd/tamper-drill?seq=0").json()
        after = client.get("/api/ledger/meituan_trd").json()
        check("ledger_copy_fail_closed", drill.get("decision_state") == "REFUSED" and
              drill.get("decision_reason") == "LEDGER_CORRUPTED")
        check("ledger_original_unchanged", before == after and after.get("chain_ok"))
        result["ledger_drill"] = {"before": before, "drill": drill, "after": after}
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    result["passed"] = all(item["passed"] for item in checks)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "checks": len(checks),
                      "failures": [c for c in checks if not c["passed"]],
                      "output": str(destination)}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
