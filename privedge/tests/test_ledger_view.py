"""Presentation regression: latest-window budget cannot be inferred from a sorted tail."""

from privedge.envelope import ReleaseItem
from privedge.server.engine import DemoEngine


def append_release(demo, source, window, epsilon=1.0):
    # Exercise the real signing, principal validation, budget charge and hash chain.
    return demo._sign_and_log(demo.publishers[source], epsilon, 1000, 1, window,
                              (ReleaseItem(0, 0.1, 0.01),))


def test_empty_ledger_has_no_latest_window_or_budget():
    demo = DemoEngine("meituan_trd")
    view = demo.ledger_view()
    assert view["total"] == 0 and view["entries"] == []
    assert view["latest_window"] is None
    assert view["latest_budget"] == [] and view["budget"] == []
    assert view["chain_ok"]


def test_latest_window_uses_append_order_not_source_or_window_sort():
    demo = DemoEngine("meituan_trd")
    sources = sorted(demo.publishers)
    append_release(demo, sources[-1], "W999")
    append_release(demo, sources[0], "W1000", epsilon=2.0)
    append_release(demo, sources[1], "W1000", epsilon=1.0)
    before = [dict(entry) for entry in demo.ledger.entries]
    view = demo.ledger_view()
    assert view["budget"][-1]["window_id"] == "W999"  # Concrete old failure trigger.
    assert view["latest_window"] == "W1000"
    assert {row["source_id"]: row["spent"] for row in view["latest_budget"]} == {
        sources[0]: 2.0, sources[1]: 1.0}
    assert all(row["window_id"] == "W1000" for row in view["latest_budget"])
    assert demo.ledger.entries == before and view["chain_ok"]


def test_latest_budget_remains_complete_after_history_exceeds_200_rows():
    demo = DemoEngine("meituan_trd")
    sources = sorted(demo.publishers)[:10]
    for number in range(1, 32):
        for source in sources:
            append_release(demo, source, f"W{number:03d}")
    append_release(demo, sources[0], "W031", epsilon=0.5)
    before = [dict(entry) for entry in demo.ledger.entries]
    view = demo.ledger_view(limit=3)
    assert view["total"] == 311 and len(view["entries"]) == 3
    assert len(view["budget"]) == 200  # Keep the historical compatibility limit.
    assert len([r for r in view["budget"] if r["window_id"] == "W031"]) < 10
    assert view["latest_window"] == "W031" and len(view["latest_budget"]) == 10
    expected = {source: 1.0 for source in sources}
    expected[sources[0]] = 1.5
    assert {row["source_id"]: row["spent"] for row in view["latest_budget"]} == expected
    assert all(row["window_id"] == "W031" and row["limit"] == 4.0 for row in view["latest_budget"])
    assert demo.ledger.entries == before and view["chain_ok"]
