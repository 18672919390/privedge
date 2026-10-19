"""B workstream acceptance checks, against the unmodified 2026-10-13 source snapshot.

Run with PRIVEDGE_B_RECORD_DIR to retain observed/expected results as JSON and CSV.
These are functional contract checks, not statistical efficacy experiments.
Known failures are left as ordinary failures so a later fix must actually pass.
"""

from __future__ import annotations

import csv
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import release_all
from privedge.attacks import forge_context_values
from privedge.server.app import app


DATASETS = ("meituan_trd", "olist_brazil", "massive_steps")
MODES = ("none", "mga", "compromised", "hijack", "demote", "negative", "tamper",
         "replay", "equivocation", "impostor", "budget_burn")
REJECTION = {"tamper": "SIGNATURE_INVALID", "replay": "STALE_WINDOW",
             "equivocation": "EQUIVOCATION", "impostor": "UNKNOWN_KEY"}


@pytest.fixture(scope="module")
def api():
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture(scope="module")
def descriptions(api):
    response = api.get("/api/datasets")
    assert response.status_code == 200
    return {row["name"]: row for row in response.json()}


@pytest.fixture(scope="module")
def observations():
    rows = []
    yield rows
    if not os.environ.get("PRIVEDGE_B_RECORD_DIR"):
        return
    output = Path(os.environ["PRIVEDGE_B_RECORD_DIR"])
    output.mkdir(parents=True, exist_ok=True)
    document = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": "23546a1215d0dfc2cd7315e9cea07b79363f7885",
        "scope": "Local TestClient and synthetic core fixtures; no production code edits or full experiment grid",
        "records": rows,
    }
    (output / "api_acceptance_results.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "api_acceptance_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case", "expected", "actual", "status", "retest"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "actual": json.dumps(row["actual"], ensure_ascii=False)})


@pytest.fixture
def check(request, observations):
    def verify(expected, actual, passed):
        row = {"case": request.node.name, "expected": expected, "actual": actual,
               "status": "PASS" if passed else "FAIL", "retest": "not_needed" if passed else "awaiting_fix"}
        observations.append(row)
        assert passed, json.dumps(row, ensure_ascii=False)
    return verify


def payload(descriptions, dataset="meituan_trd", **changes):
    return {"dataset": dataset, "target": descriptions[dataset]["servers"][-1]["id"],
            "epsilon": 2, "top_m": 40, "users": 1000, "seed": 13, **changes}


def response_summary(response):
    try:
        body = response.json()
    except ValueError:
        body = response.text[:300]
    return {"status_code": response.status_code, "body": body}


def contract_errors(result):
    errors = []
    decision = result.get("decision", {})
    state = decision.get("state")
    top = decision.get("top_k", [])
    if state not in {"NORMAL", "DEGRADED", "REFUSED"}:
        errors.append("missing/invalid decision state")
    if state in {"NORMAL", "DEGRADED"} and len(top) != 10:
        errors.append("accepted/degraded output does not contain 10 items")
    if state == "NORMAL" and decision.get("reasons"):
        errors.append("NORMAL unexpectedly has degradation/refusal reasons")
    if state in {"DEGRADED", "REFUSED"} and not decision.get("reasons"):
        errors.append("non-normal output lacks explanation")
    if len(top) != len(set(top)):
        errors.append("duplicate output categories")
    if [row["category"] for row in decision.get("top_k_named", [])] != top:
        errors.append("named output and category ids disagree")
    if any(not isinstance(row.get("name"), str) or not row["name"]
           for row in decision.get("top_k_named", [])):
        errors.append("missing display labels")
    if state != "REFUSED" and any(v < 2 for v in decision.get("support", {}).values()):
        errors.append("output violates two-source support")
    for method in ("privedge", "baseline"):
        for metric in ("recall", "ndcg"):
            value = result.get("evaluation", {}).get(method, {}).get(metric)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                errors.append(f"{method}/{metric} outside [0,1]")
    if not result.get("audit", {}).get("ledger_chain_ok"):
        errors.append("ledger invalid after normal demo execution")
    return errors


def test_b_dataset_catalog(descriptions, check):
    actual = {name: {"source_count": len(row["servers"]), "domain": row["domain"],
                     "modes": sorted(row["attacks"])} for name, row in descriptions.items()}
    check("exactly 3 datasets, at least 4 regions each, all 11 declared modes",
          actual, set(descriptions) == set(DATASETS) and all(
              len(row["servers"]) >= 4 and set(row["attacks"]) == set(MODES)
              for row in descriptions.values()))


@pytest.mark.parametrize("dataset", DATASETS)
@pytest.mark.parametrize("mode", MODES)
def test_b_dataset_mode_matrix(api, descriptions, dataset, mode, check):
    if mode == "replay":
        warmup = api.post("/api/run", json=payload(descriptions, dataset))
        assert warmup.status_code == 200, warmup.text
    response = api.post("/api/run", json=payload(descriptions, dataset, attack=mode))
    if response.status_code != 200:
        check("HTTP 200, coherent output, advertised attack evidence", response_summary(response), False)
    result = response.json()
    errors = contract_errors(result)
    codes = [row["code"] for row in result["events"] if row["type"] == "reject"]
    attack_details = [row["detail"] for row in result["events"] if row["type"] == "attack"]
    if mode in REJECTION and REJECTION[mode] not in codes:
        errors.append(f"expected gateway rejection {REJECTION[mode]}")
    if mode == "budget_burn" and not any("PRINCIPAL_MISMATCH" in text for text in attack_details):
        errors.append("budget burn lacks principal-mismatch rejection")
    if mode != "none" and not result["attackers"]:
        errors.append("selected attack has no attacker")
    actual = {"status_code": response.status_code, "dataset": dataset, "attack": mode,
              "seed": result["seed"], "window": result["window"], "state": result["decision"]["state"],
              "top_count": len(result["decision"]["top_k"]), "reject_codes": codes,
              "attack_details": attack_details, "evaluation": result["evaluation"],
              "elapsed_ms": result["elapsed_ms"], "errors": errors}
    check("HTTP 200, coherent three-state output, advertised attack evidence", actual, not errors)


INVALID = [
    ("epsilon_zero", {"epsilon": 0}, 422), ("epsilon_negative", {"epsilon": -1}, 422),
    ("epsilon_above_cap", {"epsilon": 4.01}, 422), ("epsilon_nan_string", {"epsilon": "NaN"}, 422),
    ("epsilon_inf_string", {"epsilon": "Infinity"}, 422),
    ("top_m_low", {"top_m": 9}, 422), ("top_m_high", {"top_m": 81}, 422),
    ("users_low", {"users": 999}, 422), ("users_high", {"users": 20001}, 422),
    ("attackers_low", {"attackers": 0}, 422), ("attackers_high", {"attackers": 4}, 422),
    ("beta_low", {"beta": -0.01}, 422), ("beta_high", {"beta": 0.31}, 422),
    ("seed_text", {"seed": "not-a-seed"}, 422), ("seed_fraction", {"seed": 1.5}, 422),
    ("seed_negative", {"seed": -1}, 400), ("target_empty", {"target": ""}, 400),
    ("target_unknown", {"target": "not-a-region"}, 400),
    ("dataset_unknown", {"dataset": "not-a-dataset"}, 404),
    ("attack_unknown", {"attack": "not-an-attack"}, 400),
]


@pytest.mark.parametrize("case,changes,status", INVALID, ids=[row[0] for row in INVALID])
def test_b_rest_invalid_parameters(api, descriptions, case, changes, status, check):
    before = api.get("/api/ledger/meituan_trd").json()
    response = api.post("/api/run", json={**payload(descriptions), **changes})
    after = api.get("/api/ledger/meituan_trd").json()
    actual = response_summary(response)
    actual["ledger_unchanged"] = before == after
    check(f"HTTP {status}, readable detail, no ledger mutation", actual,
          response.status_code == status and isinstance(actual["body"], dict)
          and bool(actual["body"].get("detail")) and before == after)


@pytest.mark.parametrize("raw", ['{"epsilon": NaN}', '{"epsilon": 1e309}'], ids=["nan_literal", "overflow_number"])
def test_b_nonfinite_json_returns_client_error(api, descriptions, raw, check):
    # NaN is invalid JSON; 1e309 is a valid JSON number outside finite binary64 range.
    fields = payload(descriptions)
    fields.pop("epsilon")
    request = json.dumps(fields)[:-1] + "," + raw[1:]
    response = api.post("/api/run", content=request, headers={"content-type": "application/json"})
    check("non-finite/invalid numeric input returns 400 or 422, never 500", response_summary(response),
          response.status_code in {400, 422})


def test_b_missing_target_rest(api, check):
    response = api.post("/api/run", json={"dataset": "meituan_trd"})
    check("missing required target returns HTTP 422", response_summary(response), response.status_code == 422)


@pytest.mark.parametrize("epsilon,top_m", [(0.5, 10), (0.5, 80), (4.0, 10), (4.0, 80)])
def test_b_valid_numeric_boundaries(api, descriptions, epsilon, top_m, check):
    response = api.post("/api/run", json=payload(descriptions, epsilon=epsilon, top_m=top_m, beta=0, attackers=3))
    errors = contract_errors(response.json()) if response.status_code == 200 else [response.text]
    check("documented numeric bounds execute or produce an explained decision", {
        "status_code": response.status_code, "epsilon": epsilon, "top_m": top_m,
        "state": response.json().get("decision", {}).get("state") if response.status_code == 200 else None,
        "errors": errors}, response.status_code == 200 and not errors)


def test_b_near_zero_epsilon_fails_cleanly(api, descriptions, check):
    response = api.post("/api/run", json=payload(descriptions, epsilon=1e-20))
    check("positive epsilon near machine precision must be rejected cleanly or execute, never HTTP 500",
          response_summary(response), response.status_code in {200, 400, 422})


@pytest.mark.parametrize("case,changes", [
    ("missing_target", {"target": None}), ("epsilon_zero", {"epsilon": 0}),
    ("seed_text", {"seed": "invalid"}), ("unknown_target", {"target": "unknown"}),
    ("unknown_dataset", {"dataset": "unknown"}), ("seed_negative", {"seed": -1}),
])
def test_b_websocket_bad_input_has_error_feedback(api, descriptions, case, changes, check):
    request = {**payload(descriptions), **changes}
    if case == "missing_target":
        request.pop("target")
    try:
        with api.websocket_connect("/ws/run") as socket:
            socket.send_json(request)
            messages = []
            while True:
                message = socket.receive_json()
                messages.append(message)
                if message.get("kind") != "event":
                    break
            actual = {"messages": messages}
    except Exception as err:  # the failure itself is the observed protocol result
        actual = {"exception": type(err).__name__, "detail": str(err)[:1000]}
    terminal = actual.get("messages", [{}])[-1]
    check("invalid WebSocket request produces a kind=error message with a readable explanation",
          actual, terminal.get("kind") == "error" and bool(terminal.get("error")))


def test_b_websocket_events_and_result(api, descriptions, check):
    with api.websocket_connect("/ws/run") as socket:
        socket.send_json(payload(descriptions, attack="hijack"))
        messages = []
        while True:
            message = socket.receive_json()
            messages.append(message)
            if message["kind"] != "event":
                break
    events = [m["event"] for m in messages if m["kind"] == "event"]
    final = messages[-1]
    actual = {"event_count": len(events), "types": sorted({e["type"] for e in events}),
              "terminal_kind": final["kind"]}
    passed = final["kind"] == "result" and events == final["result"]["events"]
    passed = passed and {"start", "collect", "release", "ledger", "admit", "decision"} <= set(actual["types"])
    check("ordered stream includes all pipeline events and identical final event history", actual, passed)


@pytest.mark.parametrize("dataset", DATASETS)
def test_b_tamper_drill_preserves_original(api, descriptions, dataset, check):
    assert api.post("/api/run", json=payload(descriptions, dataset)).status_code == 200
    before = api.get(f"/api/ledger/{dataset}").json()
    observations = []
    for seq in [0, 2, before["total"] - 1]:
        result = api.post(f"/api/ledger/{dataset}/tamper-drill", params={"seq": seq}).json()
        observations.append(result)
    after = api.get(f"/api/ledger/{dataset}").json()
    passed = before == after and after["chain_ok"] and all(
        row["first_bad"] == seq and not row["chain_ok"] and row["decision_state"] == "REFUSED"
        and row["decision_reason"] == "LEDGER_CORRUPTED"
        for row, seq in zip(observations, [0, 2, before["total"] - 1]))
    check("first/middle/final ledger tampering is located, refuses prediction, and leaves live ledger unchanged",
          {"drills": observations, "original_unchanged": before == after}, passed)


def test_b_windows_are_server_generated(api, descriptions, check):
    request = payload(descriptions)
    first = api.post("/api/run", json=request).json()
    second = api.post("/api/run", json=request).json()
    actual = {"first_window": first["window"], "second_window": second["window"],
              "same_top_k": first["decision"]["top_k"] == second["decision"]["top_k"],
              "same_metrics": first["evaluation"] == second["evaluation"]}
    check("repeated fixed-seed requests use fresh windows but reproduce statistical output", actual,
          first["window"] != second["window"] and actual["same_top_k"] and actual["same_metrics"])


@pytest.mark.parametrize("condition,expected", [
    ("valid", "NORMAL"), ("unverified_context", "DEGRADED"),
    ("insufficient_sources", "REFUSED"), ("corrupted_ledger", "REFUSED"),
])
def test_b_three_state_contract(world, condition, expected, check):
    releases = release_all(world)
    context = world["target_context"]
    if condition == "unverified_context":
        context = forge_context_values(context, tuple(reversed(context.values)))
    elif condition == "insufficient_sources":
        releases = releases[:2]
    elif condition == "corrupted_ledger":
        world["ledger"].entries[1]["epsilon"] = 0
    decision, audit = world["service"].predict(releases, context, world["policy"])
    actual = {"state": decision.state, "top_count": len(decision.top_k), "reasons": decision.reasons,
              "chain_ok": audit["ledger_chain_ok"], "admission": audit["admission"]}
    passed = decision.state == expected
    passed = passed and (len(decision.top_k) == 10 if expected != "REFUSED" else not decision.top_k)
    passed = passed and (not decision.reasons if expected == "NORMAL" else bool(decision.reasons))
    if condition == "corrupted_ledger":
        passed = passed and audit["admission"]["accepted"] == [] and audit["ledger_first_bad"] == 1
    check(f"{condition} yields {expected} with appropriate output and explanation", actual, passed)
