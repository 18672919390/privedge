"""Regressions independently reproduced while reviewing the B evidence delivery."""
from dataclasses import replace
import threading

import pytest
from fastapi.testclient import TestClient

from conftest import release_all
from privedge.envelope import seal
from privedge.ledger import Ledger
from privedge.server.app import app
from privedge.server.engine import DemoEngine


@pytest.mark.parametrize("field,value", [("epsilon", "NaN"), ("epsilon", "Infinity"),
    ("epsilon", "-Infinity"), ("epsilon", "1e309"), ("beta", "NaN")])
def test_nonfinite_http_input_returns_validation_error_without_running(monkeypatch, field, value):
    import privedge.server.app as server
    calls = []
    monkeypatch.setattr(server, "_engine", lambda name: calls.append(name))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/run", content='{"target":"x","%s":%s}' % (field, value),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert calls == []
    assert client.get("/api/prereg").status_code == 200


def view_engine(world):
    engine = DemoEngine.__new__(DemoEngine)
    engine.ledger, engine.registry = world["ledger"], world["registry"]
    engine.lock = threading.Lock()
    return engine


def append_window(world, templates, window):
    for template, publisher in zip(templates, world["publishers"]):
        unsigned = replace(template, release_id=window + template.source_id, window_id=window,
                           nonce="", created_at="", signature="")
        world["ledger"].append(seal(unsigned, publisher.identity.key_id, publisher.identity.private_key))


def test_latest_budget_is_empty_without_release(world):
    view = view_engine(world).ledger_view()
    assert view["latest_window"] is None
    assert view["latest_budget"] == []


def test_latest_budget_follows_append_order_not_window_sort(world):
    templates = release_all(world)
    append_window(world, templates, "W010")
    append_window(world, templates, "W002")
    view = view_engine(world).ledger_view()
    assert view["latest_window"] == "W002"
    assert len(view["latest_budget"]) == 5
    assert {row["window_id"] for row in view["latest_budget"]} == {"W002"}
    assert view["chain_ok"]


def test_latest_budget_keeps_all_sources_when_history_is_truncated(world):
    templates = release_all(world)
    for i in range(41):
        append_window(world, templates, f"W{i:03d}")
    engine = view_engine(world)
    before = engine.ledger.head
    view = engine.ledger_view(limit=3)
    assert len(view["entries"]) == 3 and len(view["budget"]) == 200
    assert view["latest_window"] == "W040"
    assert {row["source_id"] for row in view["latest_budget"]} == {p.source_id for p in world["publishers"]}
    assert all(row["spent"] == 2.0 for row in view["latest_budget"])
    assert engine.ledger.head == before and view["chain_ok"]
