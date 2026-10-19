"""Engineering tests for the offline wrapper, in source and portable layouts.

Fixtures below are synthetic control-flow checks, never scientific evidence.
No test starts ProVerif, performs statistics, installs packages or opens a server.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT = Path(__file__).resolve().parents[1]
TOOLS = next((p for p in (PROJECT.parent / "competition_entry/tools",
                         PROJECT.parent / "tool_sources/competition_entry/tools")
              if (p / "portable_reproduction.py").is_file()), None)
if TOOLS is None:
    raise RuntimeError("Portable reproduction tool sources are missing from the delivery")


def load_tool(name):
    spec = importlib.util.spec_from_file_location(f"privedge_test_{name}", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repro = load_tool("portable_reproduction")
builder = load_tool("build_portable_package")


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "中文 空格 & 复现包"
    (root / "application").mkdir(parents=True)
    (root / "runtime").mkdir()
    (root / "runtime/python.exe").write_bytes(b"synthetic placeholder; never executed")
    (root / "application/frozen.txt").write_text("historical immutable fixture", encoding="utf-8")
    files = {p.relative_to(root).as_posix(): repro.digest(p) for p in root.rglob("*") if p.is_file()}
    (root / "package_manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    return root


@pytest.mark.parametrize("mode", ["quick", "full"])
def test_a8_plan_keeps_three_datasets_and_explicit_review_scope(bundle, mode):
    jobs = repro.build_plan(bundle, mode)
    assert [j["dataset"] for j in jobs[:-1]] == list(repro.DATASETS)
    assert all(j["command"][0] == str(bundle / "runtime/python.exe") for j in jobs)
    for j in jobs[:-1]:
        command = j["command"]
        assert command[command.index("--epsilons") + 1] == "1,2"
        assert ("--max-targets" in command) == (mode == "quick")
        assert ("--max-seeds" in command) == (mode == "quick")
        if mode == "quick":
            assert command[command.index("--max-targets") + 1] == "1"
            assert command[command.index("--max-seeds") + 1] == "1"
    assert ("--allow-smoke" in jobs[-1]["command"]) == (mode == "quick")
    with pytest.raises(ValueError, match="No completed run"):
        repro.resolve_command(jobs[-1], {})


def test_plan_mode_never_creates_outputs_or_executes_commands(tmp_path, monkeypatch, capsys):
    target = tmp_path / "尚不存在 & 包"
    monkeypatch.setattr(repro.sys, "argv", ["run_reproduction.py", "--mode", "full", "--plan", "--root", str(target)])
    monkeypatch.setattr(repro.subprocess, "run", lambda *a, **k: pytest.fail("Plan invoked a process"))
    assert repro.main() == 0
    assert not target.exists()
    assert json.loads(capsys.readouterr().out)["mode"] == "full"


def test_plan_rejects_unregistered_mode_and_external_output(bundle, tmp_path):
    with pytest.raises(ValueError, match="Unsupported mode"):
        repro.build_plan(bundle, "download")
    with pytest.raises(ValueError, match="inside reproduction_outputs"):
        repro.build_plan(bundle, "figures", tmp_path / "external")


def test_frozen_manifest_detects_changed_and_missing_payload(bundle):
    assert repro.verify_payload(bundle)["ok"]
    (bundle / "application/frozen.txt").write_text("changed", encoding="utf-8")
    check = repro.verify_payload(bundle)
    assert not check["ok"]
    assert check["mismatches"] == ["application/frozen.txt"]
    (bundle / "application/frozen.txt").unlink()
    assert not repro.verify_payload(bundle)["ok"]


def test_manifest_cannot_read_hashes_outside_bundle(bundle, monkeypatch):
    (bundle / "package_manifest.json").write_text(json.dumps({"files": {"../private.txt": "any"}}), encoding="utf-8")
    monkeypatch.setattr(repro, "digest", lambda path: pytest.fail("Escaping path was read"))
    assert repro.verify_payload(bundle)["mismatches"] == ["../private.txt"]


def test_output_detection_never_accepts_an_existing_or_ambiguous_run(bundle):
    parent = bundle / "application/runs/example"
    old, new, other = (parent / n for n in ("old", "new", "other"))
    for p in (old, new, other):
        p.mkdir(parents=True)
    before = {old.resolve()}
    assert repro.output_directory(f"progress\n{old}\n{new}\nfinished", parent, before) == new
    with pytest.raises(ValueError, match="exactly one"):
        repro.output_directory(str(old), parent, before)
    with pytest.raises(ValueError, match="exactly one"):
        repro.output_directory(f"{new}\n{other}", parent, before)


def fake_a8_output(bundle, *, row_count=72, seeds=None, smoke=True):
    data = bundle / "application/data/meituan_trd"
    data.mkdir(parents=True)
    (data / "domain.json").write_text(json.dumps({"servers": [{"server_id": "first"}, {"server_id": "second"}]}), encoding="utf-8")
    folder = bundle / "application/runs/compare_v1_meituan_trd/synthetic-new-run"
    folder.mkdir(parents=True)
    (folder / "results.csv").write_text("fixture\n" + "row\n" * row_count, encoding="utf-8")
    (folder / "summary.json").write_text("{}", encoding="utf-8")
    manifest = {"experiment": "compare_v1_meituan_trd", "run_id": folder.name,
                "config": {"dataset": "meituan_trd", "smoke_test": smoke, "epsilons": [1.0, 2.0],
                           "seeds": seeds if seeds is not None else [101], "targets": ["first"],
                           "users_per_source": 5000, "top_m": 20, "top_k": 10},
                "outputs": {n: repro.digest(folder / n) for n in ("results.csv", "summary.json")}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


@pytest.mark.parametrize("change,expected", [({"row_count": 71}, "coverage"),
                                            ({"seeds": [999]}, "parameters"),
                                            ({"smoke": False}, "parameters")])
def test_success_exit_alone_cannot_accept_incomplete_or_wrong_a8(bundle, change, expected):
    folder = fake_a8_output(bundle, **change)
    session = bundle / "reproduction_outputs/session"
    job = repro.build_plan(bundle, "quick", session)[0]
    with pytest.raises(ValueError, match=expected):
        repro.validate_output(bundle, session, job, str(folder), set(), {})


def test_a8_output_records_rows_and_never_promotes_confirmation(bundle):
    folder = fake_a8_output(bundle)
    session = bundle / "reproduction_outputs/session"
    result = repro.validate_output(bundle, session, repro.build_plan(bundle, "quick", session)[0], str(folder), set(), {})
    assert result["rows"] == 72 and result["smoke_test"]
    assert result["independent_confirmation"] is False


def test_review_zero_exit_cannot_hide_failed_independent_summary_check(bundle):
    session = bundle / "reproduction_outputs/session"
    folder = session / "review/new-review"
    run_ids = {d: f"new-{d}" for d in repro.DATASETS}
    artifacts = {}
    for dataset in repro.DATASETS:
        path = folder / dataset / "validation.json"
        path.parent.mkdir(parents=True)
        value = {"source_run_id": run_ids[dataset], "source_hashes": {"results": {"match": True}},
                 "data_hashes": {"data": {"match": True}},
                 "grid_checks": {k: {"match": True} for k in ("methods", "epsilons", "scenarios", "smoke_test", "grid_rows", "paired_methods", "state_and_refusal_scoring")},
                 "original_summary_recomputed_check": {"match": dataset != "olist_brazil"}}
        path.write_text(json.dumps(value), encoding="utf-8")
        artifacts[path.relative_to(folder).as_posix()] = repro.digest(path)
    (folder / "review_manifest.json").write_text(json.dumps({"source_run_ids": list(run_ids.values()),
        "artifact_sha256": artifacts}), encoding="utf-8")
    job = repro.build_plan(bundle, "quick", session)[-1]
    with pytest.raises(ValueError, match="Independent review"):
        repro.validate_output(bundle, session, job, str(folder), set(), run_ids)


def test_formal_zero_exit_still_requires_all_negative_controls(bundle):
    folder = bundle / "application/runs/formal_v1/synthetic-formal-run"
    folder.mkdir(parents=True)
    (folder / "results.json").write_text(json.dumps({"main_ok": True, "controls": {}}), encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({"experiment": "formal_v1", "run_id": folder.name,
        "outputs": {"results.json": repro.digest(folder / "results.json")}}), encoding="utf-8")
    session = bundle / "reproduction_outputs/session"
    with pytest.raises(ValueError, match="coverage"):
        repro.validate_output(bundle, session, repro.build_plan(bundle, "formal", session)[0], str(folder), set(), {})


def test_formal_empty_query_parse_is_not_success(bundle):
    folder = bundle / "application/runs/formal_v1/synthetic-empty-query-run"
    folder.mkdir(parents=True)
    controls = {key: {"as_expected": True} for key in ("nc1_window_unsigned", "nc2_no_role_binding", "nc3_gateway_skips_ledger", "nc4_ledger_skips_signature")}
    (folder / "results.json").write_text(json.dumps({"main_ok": True, "main": [], "controls": controls}), encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({"experiment": "formal_v1", "run_id": folder.name,
        "outputs": {"results.json": repro.digest(folder / "results.json")}}), encoding="utf-8")
    session = bundle / "reproduction_outputs/session"
    with pytest.raises(ValueError, match="main properties"):
        repro.validate_output(bundle, session, repro.build_plan(bundle, "formal", session)[0], str(folder), set(), {})


@pytest.mark.parametrize("cancel", [False, True])
def test_failed_or_cancelled_command_keeps_log_and_preserves_history(bundle, monkeypatch, cancel):
    frozen = (bundle / "application/frozen.txt").read_bytes()

    def fake_run(command, **kwargs):
        assert isinstance(command, list) and str(bundle / "runtime/python.exe") == command[0]
        assert kwargs["cwd"] == bundle / "application"
        kwargs["stderr"].write("synthetic failure retained\n")
        if cancel:
            raise KeyboardInterrupt()
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(repro.subprocess, "run", fake_run)
    code, session = repro.run(bundle, "quick")
    record = json.loads((session / "session.json").read_text(encoding="utf-8"))
    assert code == (130 if cancel else 2)
    assert record["status"] == ("INTERRUPTED" if cancel else "FAILED")
    assert len(record["jobs"]) == 1
    assert record["integrity_after"]["ok"]
    assert (session / "logs/meituan_trd.stderr.txt").read_text(encoding="utf-8").startswith("synthetic failure")
    assert (bundle / "application/frozen.txt").read_bytes() == frozen
    assert (session / "结果索引.html").is_file()


def test_changed_frozen_file_forces_failure_after_command(bundle, monkeypatch):
    def fake_run(*args, **kwargs):
        (bundle / "application/frozen.txt").write_text("accidental mutation", encoding="utf-8")
        return SimpleNamespace(returncode=9)
    monkeypatch.setattr(repro.subprocess, "run", fake_run)
    code, session = repro.run(bundle, "quick")
    record = json.loads((session / "session.json").read_text(encoding="utf-8"))
    assert code == 2 and not record["integrity_after"]["ok"]
    assert record["integrity_after"]["mismatches"] == ["application/frozen.txt"]


def test_missing_formal_tool_is_explicit_and_never_runs_another_executable(bundle, monkeypatch):
    monkeypatch.setattr(repro.subprocess, "run", lambda *a, **k: pytest.fail("Missing ProVerif should not execute"))
    code, session = repro.run(bundle, "formal")
    record = json.loads((session / "session.json").read_text(encoding="utf-8"))
    assert code == 2 and "缺少包内 ProVerif" in record["error"]
    assert record["jobs"] == []


def test_source_delivery_has_rebuild_tools_assets_and_separate_locks():
    for name in builder.TOOL_SOURCES:
        assert (TOOLS / name).is_file()
    assert (TOOLS / "portable_assets/先读我_使用指南.html").is_file()
    index = json.loads((TOOLS / "portable_assets/复现索引.json").read_text(encoding="utf-8"))
    assert index["version"] == "E34" and len(index["claims"]) >= 8
    locks = builder.dependency_locks(PROJECT)
    assert {"matplotlib", "pillow", "contourpy", "cycler", "fonttools", "kiwisolver", "pyparsing"} <= set(locks)


def test_conflicting_lock_cannot_silently_change_runtime(tmp_path):
    (tmp_path / "requirements.lock").write_text("numpy==1.0\n", encoding="utf-8")
    (tmp_path / "requirements-reproduction.lock").write_text("numpy==2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Conflicting"):
        builder.dependency_locks(tmp_path)
