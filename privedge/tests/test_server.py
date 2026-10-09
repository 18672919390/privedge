import pytest

pytest.importorskip("httpx2")
from fastapi.testclient import TestClient  # noqa: E402

from privedge.server.app import WEB_DIST, app  # noqa: E402

client = TestClient(app)


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
