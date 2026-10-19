"""E34 offline reproduction wrapper; copied verbatim to run_reproduction.py.

Only selected historical commands are available. Existing data, evidence and
registered results are checked before and after execution and never rewritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATASETS = ("meituan_trd", "olist_brazil", "massive_steps")
MODES = ("quick", "full", "formal", "figures")
SCOPE = {
    "quick": "三数据各首目标、首种子101的A8工程快速核验；不用于科学结论。",
    "full": "三数据A8完整既有参数重算；旧种子复现，不是独立确认性复验。",
    "formal": "既有ProVerif模型和四个负对照重跑；不是代码安全或LDP数值证明。",
    "figures": "从已登记历史证据重绘图表及架构图；不重新计算统计实验。",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root: Path, value: str | Path) -> Path:
    root = root.resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path outside the selected folder: {value}")
    return path


def verify_payload(root: Path) -> dict:
    try:
        entries = json.loads((root / "package_manifest.json").read_text(encoding="utf-8"))["files"]
        if not isinstance(entries, dict) or not entries:
            raise ValueError("Empty or malformed package manifest")
        errors = []
        for name, expected in entries.items():
            try:
                path = contained(root, name)
                if not path.is_file() or digest(path) != expected:
                    errors.append(name)
            except (OSError, ValueError):
                errors.append(name)
        return {"ok": not errors, "files_checked": len(entries), "mismatches": errors}
    except (OSError, KeyError, ValueError, TypeError) as exc:
        return {"ok": False, "files_checked": 0, "mismatches": [], "error": str(exc)}


def build_plan(root: Path, mode: str, session: Path | None = None) -> list[dict]:
    if mode not in MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    root = root.resolve()
    session = (session or root / "reproduction_outputs" / "NEW_SESSION").resolve()
    if not session.is_relative_to(root / "reproduction_outputs"):
        raise ValueError("Session output must be inside reproduction_outputs")
    prefix = [str(root / "runtime/python.exe"), "-B", "-X", "utf8", "-m"]

    def job(key: str, module: str, args: list[str], kind: str, **extra) -> dict:
        return {"key": key, "module": module, "command": prefix + [module] + args,
                "kind": kind, **extra}

    if mode in ("quick", "full"):
        jobs = []
        for dataset in DATASETS:
            args = ["--dataset", dataset, "--epsilons", "1,2"]
            if mode == "quick":
                args += ["--max-targets", "1", "--max-seeds", "1"]
            jobs.append(job(dataset, "privedge.experiments.compare_v1", args, "experiment",
                            dataset=dataset, smoke_test=mode == "quick"))
        args = [f"RUN_ID:{dataset}" for dataset in DATASETS]
        args += ["--out-root", str(session / "review")]
        if mode == "quick":
            args.append("--allow-smoke")
        jobs.append(job("review", "privedge.experiments.review_compare_v1", args, "review", smoke_test=mode == "quick"))
        return jobs
    if mode == "formal":
        return [job("formal", "privedge.experiments.formal_v1",
                    ["--proverif", str(root / "tools/proverif/proverif2.05/proverif.exe")], "formal")]
    return [job(name, f"privedge.experiments.{name}", ["--out", str(session / "figures")], "figures")
            for name in ("figures", "diagrams")]


def resolve_command(job: dict, run_ids: dict[str, str]) -> list[str]:
    command = []
    for value in job["command"]:
        if value.startswith("RUN_ID:"):
            key = value.removeprefix("RUN_ID:")
            if key not in run_ids:
                raise ValueError(f"No completed run for {key}; review cannot start")
            value = run_ids[key]
        command.append(value)
    return command


def validate_hashes(folder: Path, entries: dict) -> None:
    if not entries:
        raise ValueError("Output manifest has no artifacts")
    for name, expected in entries.items():
        path = contained(folder, name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Output hash mismatch: {name}")


def output_directory(stdout: str, allowed_parent: Path, before: set[Path]) -> Path:
    candidates = []
    for line in stdout.splitlines():
        try:
            path = Path(line.strip())
            if not path.is_absolute():
                continue
            path = path.resolve()
            if path.parent == allowed_parent.resolve() and path.is_dir() and path not in before:
                candidates.append(path)
        except (OSError, ValueError):
            continue
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) != 1:
        raise ValueError("Expected exactly one new output directory printed by the command")
    return candidates[0]


def validate_output(root: Path, session: Path, job: dict, stdout: str,
                    before: set[Path], run_ids: dict[str, str]) -> dict:
    kind = job["kind"]
    if kind == "figures":
        names = (["fig_utility", "fig_sensitivity", "fig_security", "fig_hijack", "fig_overhead"]
                 if job["key"] == "figures" else ["fig_architecture", "fig_protocol"])
        artifacts = {}
        for name in names:
            for ext in ("png", "svg"):
                path = session / "figures" / f"{name}.{ext}"
                if not path.is_file() or path.stat().st_size == 0:
                    raise ValueError(f"Missing figure: {path.name}")
                artifacts[path.relative_to(root).as_posix()] = digest(path)
        return {"artifacts": artifacts, "source": "registered historical evidence; redraw only"}
    if kind == "review":
        folder = output_directory(stdout, session / "review", before)
        manifest = json.loads((folder / "review_manifest.json").read_text(encoding="utf-8"))
        if manifest["source_run_ids"] != [run_ids[d] for d in DATASETS]:
            raise ValueError("Review refers to different runs")
        validate_hashes(folder, manifest["artifact_sha256"])
        for dataset in DATASETS:
            validation = json.loads((folder / dataset / "validation.json").read_text(encoding="utf-8"))
            checks = validation["grid_checks"]
            required = ["methods", "epsilons", "scenarios", "smoke_test", "grid_rows", "paired_methods", "state_and_refusal_scoring"]
            if not job["smoke_test"]:
                required += ["seeds", "targets", "formal_grid"]
            hashes_ok = all(validation.get(key) and all(v["match"] for v in validation[key].values())
                            for key in ("source_hashes", "data_hashes"))
            if (validation.get("source_run_id") != run_ids[dataset] or not hashes_ok
                    or not all(checks[key]["match"] for key in required)
                    or not validation["original_summary_recomputed_check"]["match"]):
                raise ValueError(f"Independent review did not validate hashes, grid or summary: {dataset}")
        return {"output_dir": folder.relative_to(root).as_posix(),
                "manifest_sha256": digest(folder / "review_manifest.json"),
                "independent_confirmation": False,
                "interpretation": "Historical-seed reproduction only; numerical decision rules do not establish new pre-run freezing."}
    experiment = "formal_v1" if kind == "formal" else f"compare_v1_{job['dataset']}"
    folder = output_directory(stdout, root / "application/runs" / experiment, before)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("experiment") != experiment or manifest.get("run_id") != folder.name:
        raise ValueError("Unexpected experiment or run ID")
    validate_hashes(folder, manifest["outputs"])
    result = {"run_id": folder.name, "output_dir": folder.relative_to(root).as_posix(),
              "manifest_sha256": digest(folder / "manifest.json")}
    if kind == "formal":
        report = json.loads((folder / "results.json").read_text(encoding="utf-8"))
        expected_controls = {"nc1_window_unsigned", "nc2_no_role_binding", "nc3_gateway_skips_ledger", "nc4_ledger_skips_signature"}
        main = report.get("main", [])
        expected_main = {"Q1": True, "Q2": True, "Q3": True, "Q4": True, "Q5": True, "S1": False, "S2": False}
        if (not report.get("main_ok") or len(main) != len(expected_main)
                or {item.get("query"): item.get("holds") for item in main} != expected_main
                or set(report.get("controls", {})) != expected_controls):
            raise ValueError("Formal main properties or negative-control coverage failed")
        if not all(c.get("as_expected") for c in report["controls"].values()):
            raise ValueError("A formal negative control did not match the recorded expectation")
        result["main_ok"] = True
    else:
        config = manifest["config"]
        metadata = json.loads((root / "application/data" / job["dataset"] / "domain.json").read_text(encoding="utf-8"))
        targets = [server["server_id"] for server in metadata["servers"]]
        expected_targets = targets[:1] if job["smoke_test"] else targets
        if (config.get("dataset") != job["dataset"] or config.get("smoke_test") is not job["smoke_test"]
                or config.get("epsilons") != [1.0, 2.0]
                or config.get("seeds") != ([101] if job["smoke_test"] else [101, 211, 307, 401, 503])
                or config.get("users_per_source") != 5000 or config.get("top_m") != 20 or config.get("top_k") != 10
                or not expected_targets or config.get("targets") != expected_targets):
            raise ValueError("Experiment parameters differ from the selected E34 profile")
        with (folder / "results.csv").open(encoding="utf-8-sig", newline="") as handle:
            row_count = sum(1 for _ in csv.DictReader(handle))
        expected_rows = len(config["targets"]) * len(config["seeds"]) * 2 * 9 * 4
        if (job["smoke_test"] and len(config["targets"]) != 1) or row_count != expected_rows:
            raise ValueError("Experiment row coverage is incomplete")
        result.update(rows=row_count, smoke_test=config["smoke_test"], independent_confirmation=False)
    return result


def write_session(root: Path, session: Path, report: dict) -> None:
    (session / "session.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for entry in report["jobs"]:
        links = []
        for key in ("stdout", "stderr", "output_dir"):
            if entry.get(key):
                target = contained(root, entry[key])
                relative = Path(os.path.relpath(target, session)).as_posix()
                links.append(f'<a href="{html.escape(relative, quote=True)}">{html.escape(key)}</a>')
        rows.append(f"<tr><td>{html.escape(entry['key'])}</td><td>{html.escape(entry['status'])}</td><td>{' · '.join(links)}</td></tr>")
    status = html.escape(report["status"])
    error = html.escape(report.get("error", ""))
    body = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PrivEdge E34 复现记录</title>
<style>body{{font:16px/1.7 'Microsoft YaHei',sans-serif;max-width:1000px;margin:40px auto;padding:0 20px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd5df;padding:10px;text-align:left}}code{{word-break:break-all}}</style>
<h1>PrivEdge E34 复现记录</h1><p>状态：<b>{status}</b></p><p>{html.escape(report['scope'])}</p>
<p>本次输出不会替换实验中心的历史登记。快速核验与旧种子重算均不是新的确认性证据；检查通过不表示预测准确。</p>
<p>{error}</p><table><tr><th>步骤</th><th>状态</th><th>文件</th></tr>{''.join(rows)}</table>
<p><a href="session.json">完整会话记录</a> · <a href="command_plan.json">命令及参数</a> · <a href="../../先读我_使用指南.html">返回指南</a></p></html>'''
    (session / "结果索引.html").write_text(body, encoding="utf-8")


def run(root: Path, mode: str) -> tuple[int, Path]:
    root = root.resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session = root / "reproduction_outputs" / f"{mode}-{stamp}-{uuid.uuid4().hex[:8]}"
    session.mkdir(parents=True, exist_ok=False)
    plan = build_plan(root, mode, session)
    (session / "command_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"version": "E34", "mode": mode, "scope": SCOPE[mode], "status": "RUNNING",
              "started_at": datetime.now(timezone.utc).isoformat(), "independent_confirmation": False, "jobs": []}
    run_ids = {}
    exit_code = 2
    try:
        report["integrity_before"] = verify_payload(root)
        if not report["integrity_before"]["ok"]:
            raise ValueError("包内冻结文件校验失败，请完整解压原始程序包后再运行。")
        if not (root / "runtime/python.exe").is_file():
            raise FileNotFoundError("缺少包内 runtime/python.exe。")
        if mode == "formal" and not (root / "tools/proverif/proverif2.05/proverif.exe").is_file():
            raise FileNotFoundError("缺少包内 ProVerif 2.05；不能把历史结果当作本次重跑。")
        for job in plan:
            command = resolve_command(job, run_ids)
            entry = {"key": job["key"], "status": "RUNNING", "command": command,
                     "started_at": datetime.now(timezone.utc).isoformat()}
            report["jobs"].append(entry)
            logs = session / "logs"
            logs.mkdir(exist_ok=True)
            stdout = logs / f"{job['key']}.stdout.txt"
            stderr = logs / f"{job['key']}.stderr.txt"
            entry.update(stdout=stdout.relative_to(root).as_posix(), stderr=stderr.relative_to(root).as_posix())
            if job["kind"] == "review":
                parent = session / "review"
            elif job["kind"] in ("experiment", "formal"):
                name = "formal_v1" if job["kind"] == "formal" else f"compare_v1_{job['dataset']}"
                parent = root / "application/runs" / name
            else:
                parent = session / "figures"
            before = {p.resolve() for p in parent.iterdir() if p.is_dir()} if parent.is_dir() else set()
            write_session(root, session, report)
            print(f"[{len(report['jobs'])}/{len(plan)}] {job['key']}：正在执行；日志 {stdout}", flush=True)
            env = os.environ.copy()
            env["MPLCONFIGDIR"] = str(session / "matplotlib_cache")
            with stdout.open("w", encoding="utf-8") as output, stderr.open("w", encoding="utf-8") as error:
                completed = subprocess.run(command, cwd=root / "application", env=env,
                                           stdout=output, stderr=error, check=False)
            entry["returncode"] = completed.returncode
            if completed.returncode:
                raise RuntimeError(f"{job['key']} 返回 {completed.returncode}，请查看该步骤stderr日志。")
            entry.update(validate_output(root, session, job, stdout.read_text(encoding="utf-8"), before, run_ids))
            if job["kind"] == "experiment":
                run_ids[job["dataset"]] = entry["run_id"]
            entry.update(status="PASSED", finished_at=datetime.now(timezone.utc).isoformat())
        report["status"] = "PASSED"
        exit_code = 0
    except KeyboardInterrupt:
        report.update(status="INTERRUPTED", error="已中断；未完成输出及日志保留，不能作为完成结果。")
        exit_code = 130
    except Exception as exc:
        report.update(status="FAILED", error=str(exc))
    finally:
        for entry in report["jobs"]:
            if entry["status"] == "RUNNING":
                entry["status"] = report["status"]
        report["integrity_after"] = verify_payload(root)
        if not report["integrity_after"]["ok"]:
            report.update(status="FAILED", integrity_error="冻结文件发生变化；请保留日志并重新解压原包核查。")
            exit_code = 2
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_session(root, session, report)
    print(f"{report['status']}：{session / '结果索引.html'}", flush=True)
    if report.get("error"):
        print(report["error"], flush=True)
    return exit_code, session


def main() -> int:
    parser = argparse.ArgumentParser(description="PrivEdge E34 offline reproduction; no online installation")
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--plan", action="store_true", help="Print commands only; do not create files or run experiments")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps({"mode": args.mode, "scope": SCOPE[args.mode], "jobs": build_plan(args.root, args.mode)}, ensure_ascii=False, indent=2))
        return 0
    print(SCOPE[args.mode], flush=True)
    print("输出写入新目录；旧证据不改。关闭或中断窗口会保留未完成日志。", flush=True)
    return run(args.root, args.mode)[0]


if __name__ == "__main__":
    raise SystemExit(main())
