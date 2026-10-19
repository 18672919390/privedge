"""Real HTTP/WebSocket regression checks for B-API-001 and B-API-002.

The fixture starts Uvicorn on a loopback ephemeral port. No transport, engine,
or ledger is mocked. Set PRIVEDGE_API_RECORD_DIR to retain protocol observations.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import uvicorn
from websockets.sync.client import connect

from privedge.server.app import app


VALID = {"target": "商圈5", "epsilon": 2, "users": 1000, "seed": 13}
INVALID_NUMBERS = ("NaN", "Infinity", "-Infinity", "1e309", "-1e309")


@pytest.fixture(scope="module")
def live_server():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Uvicorn did not start on the loopback test socket"
        yield f"127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive(), "Uvicorn did not stop after the regression tests"


@pytest.fixture(scope="module")
def records():
    rows = []
    yield rows
    if location := os.environ.get("PRIVEDGE_API_RECORD_DIR"):
        output = Path(location)
        output.mkdir(parents=True, exist_ok=True)
        (output / "live_api_regressions.json").write_text(json.dumps({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "transport": "Uvicorn loopback HTTP + real WebSocket, no mocks",
            "records": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")


def strict_json(text):
    def reject_nonfinite(value):
        raise AssertionError(f"Response contains non-JSON numeric value: {value}")
    return json.loads(text, parse_constant=reject_nonfinite)


def http(server, path, body=None):
    request = Request(f"http://{server}{path}", data=body,
                      headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        return response.status, strict_json(response.read().decode("utf-8"))


def ledger(server):
    status, body = http(server, "/api/ledger/meituan_trd")
    assert status == 200
    return body


REST_BAD = [
    (f"epsilon_{value}", '{"target":"商圈5","epsilon":' + value + '}')
    for value in INVALID_NUMBERS
] + [
    ("beta_nan", '{"target":"商圈5","beta":NaN}'),
    ("missing_target_with_nonfinite_nested_input", '{"extra":{"nested":[NaN,1e309]}}'),
    ("invalid_json", '{"target":'),
    ("array", '[]'),
    ("null", 'null'),
    ("string", '"text"'),
    ("number", '1'),
]


@pytest.mark.parametrize("case,raw", REST_BAD, ids=[row[0] for row in REST_BAD])
def test_rest_invalid_body_is_safe_json_and_leaves_ledger_unchanged(live_server, records, case, raw):
    before = ledger(live_server)
    status, body = http(live_server, "/api/run", raw.encode("utf-8"))
    after = ledger(live_server)
    records.append({"case": f"REST/{case}", "status": status, "body": body,
                    "ledger_unchanged": before == after})
    assert status in {400, 422}
    assert body.get("detail")
    assert before == after


WS_BAD = REST_BAD + [
    ("epsilon_zero", '{"target":"商圈5","epsilon":0}'),
    ("seed_text", '{"target":"商圈5","seed":"invalid"}'),
    ("missing_target", '{}'),
    ("unknown_target", '{"target":"unknown"}'),
    ("unknown_dataset", '{"target":"商圈5","dataset":"unknown"}'),
    ("negative_seed", '{"target":"商圈5","seed":-1}'),
    ("binary_frame", b'{}'),
]


@pytest.mark.parametrize("case,raw", WS_BAD, ids=[row[0] for row in WS_BAD])
def test_websocket_reports_invalid_input_then_accepts_next_request(live_server, records, case, raw):
    before = ledger(live_server)
    with connect(f"ws://{live_server}/ws/run", open_timeout=5, close_timeout=5) as ws:
        ws.send(raw)
        error = strict_json(ws.recv(timeout=10))
        after_error = ledger(live_server)
        assert error.get("kind") == "error" and error.get("error"), error
        assert before == after_error
        # Recovery is on the SAME connection, so swallowing an exception and
        # closing the connection cannot satisfy the contract.
        ws.send(json.dumps(VALID, ensure_ascii=False))
        events = []
        while True:
            message = strict_json(ws.recv(timeout=15))
            if message.get("kind") != "event":
                break
            events.append(message["event"])
        records.append({"case": f"WS/{case}", "error": error,
                        "ledger_unchanged_after_error": before == after_error,
                        "recovery_kind": message.get("kind"), "event_count": len(events)})
        assert message.get("kind") == "result", message
        assert len(events) > 10
        assert events == message["result"]["events"]
        assert message["result"]["audit"]["ledger_chain_ok"]
