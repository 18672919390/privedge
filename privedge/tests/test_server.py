import pytest

pytest.importorskip("httpx2")
from fastapi.testclient import TestClient  # noqa: E402

from privedge.server.app import WEB_DIST, app  # noqa: E402

client = TestClient(app)


def test_prediction_api_works_on_every_dataset():
    for row in client.get("/api/datasets").json():
        target = row["servers"][-1]["id"]
        result = client.post("/api/run", json={"dataset": row["name"], "target": target, "epsilon": 2,
                                               "users": 1000, "seed": 1}).json()
        assert result.get("decision", {}).get("state") in {"NORMAL", "DEGRADED", "REFUSED"}, result
        named = result["decision"]["top_k_named"] + result["evaluation"]["truth_top10"]
        assert named
        assert all(isinstance(item["name"], str) and not item["name"].startswith("schema:") for item in named)
        if row["name"] == "olist_brazil":
            assert any(any(ch.isalpha() for ch in item["name"]) for item in named)
        if row["name"] == "meituan_trd":
            assert all(item["name"].startswith("品类#") for item in named)


def test_run_blocks_weight_hijack_end_to_end():
    result = client.post("/api/run", json={"target": "商圈3", "attack": "hijack", "epsilon": 2, "seed": 7}).json()
    assert result["decision"]["state"] == "NORMAL"
    assert result["evaluation"]["privedge"]["attack_success"] <= result["evaluation"]["baseline"]["attack_success"]
    assert result["audit"]["ledger_chain_ok"]


@pytest.mark.parametrize("attack,code", [("tamper", "SIGNATURE_INVALID"), ("impostor", "UNKNOWN_KEY"),
                                         ("equivocation", "EQUIVOCATION")])
def test_network_attacks_are_rejected_at_gateway(attack, code):
    result = client.post("/api/run", json={"target": "商圈4", "attack": attack, "epsilon": 2, "seed": 3}).json()
    assert code in {e["code"] for e in result["events"] if e["type"] == "reject"}


def test_stream_ends_with_result():
    with client.websocket_connect("/ws/run") as socket:
        socket.send_json({"target": "商圈5", "epsilon": 2, "seed": 1})
        kinds = []
        while True:
            message = socket.receive_json()
            kinds.append(message["kind"])
            if message["kind"] != "event":
                break
    assert kinds[-1] == "result" and kinds.count("event") > 10


@pytest.mark.parametrize("payload,raw_text", [
    ({}, False), ({"target": "商圈5", "epsilon": 0}, False),
    ([], False), (None, False), ("not-an-object", False), ("{", True),
])
def test_stream_reports_invalid_requests_and_recovers(monkeypatch, payload, raw_text):
    """Bad messages must not run the engine, and the same connection remains usable."""
    import privedge.server.app as server

    calls = []

    class StubEngine:
        def run(self, **kwargs):
            calls.append(kwargs["target"])
            kwargs["emit"]({"type": "start"})
            return {"completed": True}

    monkeypatch.setattr(server, "_engine", lambda dataset: StubEngine())
    with client.websocket_connect("/ws/run") as socket:
        if raw_text:
            socket.send_text(payload)
        else:
            socket.send_json(payload)
        error = socket.receive_json()
        assert error["kind"] == "error" and error["error"]
        assert calls == []
        socket.send_json({"target": "商圈5", "seed": 1})
        assert socket.receive_json()["kind"] == "event"
        assert socket.receive_json() == {"kind": "result", "result": {"completed": True}}
        assert calls == ["商圈5"]


def test_ledger_tamper_drill_pinpoints_entry():
    client.post("/api/run", json={"target": "商圈6", "epsilon": 1, "seed": 2})
    drill = client.post("/api/ledger/meituan_trd/tamper-drill?seq=2").json()
    assert drill["chain_ok"] is False and drill["first_bad"] == 2
    assert drill["decision_state"] == "REFUSED" and drill["decision_reason"] == "LEDGER_CORRUPTED"
    assert client.get("/api/ledger/meituan_trd").json()["chain_ok"]


@pytest.mark.parametrize("probe", [
    "/..%2F..%2Frequirements.lock", "/%2E%2E/%2E%2E/requirements.lock", "/..%5C..%5Crequirements.lock",
    "/D%3A/%E6%AF%94%E8%B5%9B/privedge/requirements.lock", "/C:/Windows/win.ini", "/%2F%2Flocalhost/c$/Windows/win.ini",
    "/assets/..%2F..%2F..%2Frequirements.lock", "/assets/%2E%2E/%2E%2E/%2E%2E/requirements.lock",
])
def test_static_route_never_leaves_web_dist(probe):
    response = client.get(probe)
    assert response.status_code in (200, 404)
    assert "annotated-types" not in response.text and "[fonts]" not in response.text
    if response.status_code == 200:
        assert response.text.lstrip().lower().startswith("<!doctype html")


def test_static_route_still_serves_built_files():
    assert client.get("/index.html").text.lstrip().lower().startswith("<!doctype html")
    asset = next(p for p in WEB_DIST.joinpath("assets").iterdir() if p.suffix == ".js")
    assert client.get(f"/assets/{asset.name}").content == asset.read_bytes()


def test_a8_evidence_route_is_json_and_does_not_change_legacy_evidence(tmp_path, monkeypatch):
    from privedge.server.evidence import evidence
    from privedge.server import a8_evidence as reader

    registry = tmp_path / "registry.json"
    registry.write_text('{"schema_version":1,"runs":[]}')
    monkeypatch.setattr(reader, "REGISTRY", registry)

    response = client.get("/api/evidence/a8")
    assert response.status_code == 200 and response.json()["status"] == "NOT_RUN"
    assert set(response.json()["datasets"]) == {"massive_steps", "olist_brazil", "meituan_trd"}
    assert client.get("/api/evidence").json() == json_compatible(evidence())


def json_compatible(value):
    import json
    return json.loads(json.dumps(value))
