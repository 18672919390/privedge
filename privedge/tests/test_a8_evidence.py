"""Synthetic temporary fixtures test transport integrity, not algorithm accuracy."""
import hashlib
import json
from copy import deepcopy

import pytest

from privedge.server import a8_evidence as reader


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def registered(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(reader, "PREREG", tmp_path / "prereg")
    monkeypatch.setattr(reader, "REGISTRY", tmp_path / "registry.json")
    reader.PREREG.mkdir()
    prereg = b"SYNTHETIC TEST ONLY, NOT A COMPETITION RESULT"
    (reader.PREREG / "TEST_ONLY.md").write_bytes(prereg)
    run_id = "a8_test_only-20261013T000000Z-abcdef"
    folder = reader.RUNS / "a8_test_only" / run_id
    folder.mkdir(parents=True)
    summary = {"schema_version": 1, "dataset": "meituan_trd", "methods": [
        {"id": m, "name": m, "definition": "SYNTHETIC FIXTURE", "status": "COMPLETED"} for m in reader.METHODS],
        "cells": [{"method": m, "epsilon": 2, "top_m": 20, "scenario": "none", "beta": 0,
                   "attackers": 0, "target_scope": "all", "seeds": [13, 17], "sample_count": 4,
                   "ndcg": 0.5, "recall": 0.5, "attack_success": None,
                   "missing_reason": "无攻击条件没有攻击成功率"} for m in reader.METHODS]}
    entry = {"dataset": "meituan_trd", "run_id": run_id, "evidence_id": "E99", "prereg": "TEST_ONLY.md",
             "prereg_sha256": digest(prereg), "manifest_sha256": "0" * 64}

    def write(payload=None, mutate_manifest=None):
        value = deepcopy(summary if payload is None else payload)
        data = json.dumps(value, ensure_ascii=False).encode()
        (folder / "summary.json").write_bytes(data)
        raw = b"SYNTHETIC FIXTURE ONLY\n"
        (folder / "results.csv").write_bytes(raw)
        manifest = {"run_id": run_id, "experiment": "a8_test_only", "started_at": "2026-10-13T00:00:00Z",
                    "finished_at": "2026-10-13T00:01:00Z", "config": {"dataset": "meituan_trd",
                    "seeds": [13, 17], "prereg_sha256": entry["prereg_sha256"]},
                    "data_sha256": {"test": "0" * 64}, "code": {"combined": "0" * 64},
                    "environment": {"python": "test"}, "outputs": {"summary.json": digest(data), "results.csv": digest(raw)}}
        if mutate_manifest:
            mutate_manifest(manifest)
        encoded = json.dumps(manifest).encode()
        (folder / "manifest.json").write_bytes(encoded)
        entry["manifest_sha256"] = digest(encoded)
        reader.REGISTRY.write_text(json.dumps({"schema_version": 1, "runs": [entry]}), encoding="utf-8")
    write()
    return summary, folder, entry, write


def test_empty_registry_never_fabricates_results(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, "REGISTRY", tmp_path / "registry.json")
    reader.REGISTRY.write_text('{"schema_version":1,"runs":[]}')
    result = reader.a8_evidence()
    assert result["status"] == "NOT_RUN"
    assert all(d["status"] == "NOT_RUN" and d["cells"] == [] for d in result["datasets"].values())


def test_valid_registration_is_partial_until_all_datasets_exist(registered):
    result = reader.a8_evidence()
    assert result["status"] == "PARTIAL"
    data = result["datasets"]["meituan_trd"]
    assert data["status"] == "REGISTERED" and len(data["methods"]) == len(data["cells"]) == 4
    assert data["cells"][0]["attack_success"] is None
    assert data["evidence_id"] == "E99" and data["provenance"]["environment"]


def test_inapplicable_external_method_requires_no_fake_cells(registered):
    summary, _, _, write = registered
    summary["methods"][2].update(status="NOT_APPLICABLE", reason="TEST ONLY: incompatible input shape")
    summary["cells"] = [c for c in summary["cells"] if c["method"] != "robust_baseline"]
    write(summary)
    data = reader.a8_evidence()["datasets"]["meituan_trd"]
    assert data["status"] == "REGISTERED" and len(data["cells"]) == 3
    summary["methods"][2]["reason"] = " "
    write(summary)
    assert reader.a8_evidence()["status"] == "INVALID"


@pytest.mark.parametrize("filename", ["manifest.json", "summary.json", "results.csv"])
def test_tampered_files_hide_numbers(registered, filename):
    _, folder, _, _ = registered
    (folder / filename).write_bytes(b"tampered")
    result = reader.a8_evidence()
    assert result["status"] == "INVALID"
    assert result["datasets"]["meituan_trd"]["cells"] == []


def test_changed_prereg_is_rejected(registered):
    (reader.PREREG / "TEST_ONLY.md").write_bytes(b"changed after review")
    assert reader.a8_evidence()["status"] == "INVALID"


@pytest.mark.parametrize("fault", ["missing_method", "duplicate_cell", "unpaired_seeds", "nan", "missing_reason", "wrong_dataset"])
def test_invalid_summary_is_rejected_even_with_updated_hashes(registered, fault):
    summary, _, _, write = registered
    if fault == "missing_method":
        summary["cells"].pop()
    elif fault == "duplicate_cell":
        summary["cells"].append(deepcopy(summary["cells"][0]))
    elif fault == "unpaired_seeds":
        summary["cells"][0]["seeds"] = [13, 19]
    elif fault == "nan":
        summary["cells"][0]["ndcg"] = float("nan")
    elif fault == "missing_reason":
        summary["cells"][0].pop("missing_reason")
    else:
        summary["dataset"] = "olist_brazil"
    write(summary)
    assert reader.a8_evidence()["status"] == "INVALID"


def test_runtime_registry_refresh_has_no_stale_cache(registered):
    assert reader.a8_evidence()["status"] == "PARTIAL"
    reader.REGISTRY.write_text('{"schema_version":1,"runs":[]}')
    assert reader.a8_evidence()["status"] == "NOT_RUN"


@pytest.mark.parametrize("run_id,prereg", [("../escape", "TEST_ONLY.md"),
                                          ("a8_test_only-20261013T000000Z-abcdef", "../escape.md")])
def test_registry_cannot_supply_external_paths(registered, run_id, prereg):
    _, _, entry, _ = registered
    entry.update(run_id=run_id, prereg=prereg)
    reader.REGISTRY.write_text(json.dumps({"schema_version": 1, "runs": [entry]}))
    assert reader.a8_evidence()["status"] == "INVALID"


def test_manifest_config_is_bound_to_registered_prereg(registered):
    _, _, _, write = registered
    write(mutate_manifest=lambda m: m["config"].update(prereg_sha256="0" * 64))
    assert reader.a8_evidence()["status"] == "INVALID"


@pytest.mark.parametrize("field", ["config", "outputs"])
def test_malformed_manifest_structure_returns_invalid(registered, field):
    _, _, _, write = registered
    write(mutate_manifest=lambda m: m.update({field: []}))
    assert reader.a8_evidence()["status"] == "INVALID"


def test_optional_intervals_must_match_metric(registered):
    summary, _, _, write = registered
    summary["cells"][0]["ndcg_ci95"] = [0.4, 0.6]
    write(summary)
    assert reader.a8_evidence()["status"] == "PARTIAL"
    summary["cells"][0]["ndcg_ci95"] = [0.7, 0.9]
    write(summary)
    assert reader.a8_evidence()["status"] == "INVALID"
