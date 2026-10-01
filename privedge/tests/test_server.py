import pytest

pytest.importorskip("httpx2")
from fastapi.testclient import TestClient  # noqa: E402

from privedge.server.app import app  # noqa: E402

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
