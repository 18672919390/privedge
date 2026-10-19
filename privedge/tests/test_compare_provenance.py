"""Regression for the received reviewer's path-only preregistration acceptance."""
import hashlib
import json

import pytest

from privedge.experiments import review_compare_v1 as review


@pytest.mark.parametrize("binding,expected", [(None, False), ("0" * 64, False), ("correct", True)])
def test_process_does_not_admit_unbound_preregistration(tmp_path, monkeypatch, binding, expected):
    # Isolate this gate: other integrity/grid/statistical checks have passed.
    prereg = tmp_path / "COMPARE_V1.md"
    prereg.write_text("frozen proposal\n", encoding="utf-8")
    data = tmp_path / "data/meituan_trd"
    data.mkdir(parents=True)
    (data / "domain.json").write_bytes(b"{}")
    config = {"dataset": "meituan_trd", "prereg": review.PREREG_RELATIVE}
    if binding is not None:
        config["prereg_sha256"] = hashlib.sha256(prereg.read_bytes()).hexdigest() if binding == "correct" else binding
    manifest = {"config": config, "data_sha256": {"domain.json": hashlib.sha256(b"{}").hexdigest()}}
    loaded = {"hashes": {"results.csv": {"match": True}, "summary.json": {"match": True}},
              "original_summary": {"cells": []}}
    monkeypatch.setattr(review, "PREREG_PATH", prereg)
    monkeypatch.setattr(review, "PACKAGE_ROOT", tmp_path)
    monkeypatch.setattr(review, "read_source", lambda run_id: (tmp_path, manifest, [], loaded))
    monkeypatch.setattr(review, "check_grid", lambda *args: {"valid_for_confirmatory_decision": True, "formal_grid": {"match": True}})
    monkeypatch.setattr(review, "build_statistics", lambda rows: ({"cells": []}, [], [], []))
    result = review.process("received-run", tmp_path / "review", False)
    assert result["confirmatory_admissible"] is expected
    saved = json.loads((tmp_path / "review/meituan_trd/validation.json").read_text(encoding="utf-8"))
    assert saved["preregistration"]["binding_matches"] is expected
