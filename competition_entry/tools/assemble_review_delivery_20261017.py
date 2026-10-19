"""Assemble an allow-listed review delivery without private working notes."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "competition_entry/docs/v4"
E34 = DOCS / "backend_validation/20261017_review_delivery"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report-pages", type=int, required=True)
    args = parser.parse_args()
    out = ROOT / "share/PrivEdge_评审整编完整资料_E34_20261017"
    archive = out.with_suffix(".zip")
    if out.exists() or archive.exists():
        raise SystemExit("Output already exists; keep prior delivery intact.")
    report = DOCS / "PrivEdge_作品报告_评审整编版_20261017.pdf"
    intro = DOCS / "PrivEdge_作品简介_20261017.pdf"
    appendix = DOCS / "PrivEdge_工程验证与历史记录附件_20261017.pdf"
    required = [args.program, report, intro, appendix]
    required += [p.with_suffix(".docx") for p in (report, intro, appendix)]
    for path in required:
        if not path.is_file():
            raise SystemExit(f"Missing required artifact: {path}")
    if report.stat().st_size >= 10_000_000:
        raise SystemExit("Report PDF exceeds conservative 10 MB limit.")
    out.mkdir()

    def copy(src, relative):
        dst = out / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    copy(args.program, args.program.name)
    for src in (report, intro):
        copy(src, src.name)
    copy(appendix, Path("补充材料") / appendix.name)
    for src in (report, intro, appendix):
        copy(src.with_suffix(".docx"), Path("可编辑文档") / src.with_suffix(".docx").name)
    evidence = Path("工程验收证据")
    names = ["developer_pytest_normal.txt", "bundle_pytest.txt", "bundle_quick.txt", "bundle_formal.txt", "bundle_figures.txt",
             "browser_validation.json", "frontend_implementation_checks.json", "api_acceptance.json", "prereg_comparison_resolution.json",
             "portable_final_validation.json", "bundle_privacy_allowlist_audit.json", "fresh_live_launcher.json"]
    for name in names:
        copy(E34 / name, evidence / name)
    (out / evidence / "00_证据读法.txt").write_text("""本目录保留工程验证的真实输出，不将单次演示当作统计实验。

developer_pytest_normal.txt 与 bundle_pytest.txt 分别为开发和程序包的239项回归；3个既有极小ε数值警告保留。
frontend_implementation_checks.json 的104项是自动检查；browser_validation.json 的17组是真实页面观察。

api_acceptance.json 保留首次检查的原始失败：比较脚本要求预注册列表完全相等，误拒绝了新加入的E34预先方案。
prereg_comparison_resolution.json 记录逐项复核：旧23份全部保留、仅新增本轮方案，产品没有因此出现功能缺陷。没有覆盖原失败记录。
浏览器原始hijack_state.txt也保留了后来修好的AS舍入误报。以final_hijack_expanded_state.txt及最终attack_metrics.png确认修复。
normal_export.json为最终AS显示修正前实际下载，内嵌指纹准确标识当时版本；它不冒充最终冻结包的指纹。最终资产指纹见前端检查记录。
normal_export_final.json是在最终ZIP新解压目录真实启动后，从网页再次实际下载的记录；其中程序和数据指纹与最终包接口逐项一致。

离线复现目录含quick、formal、figures实际新输出。日志路径可能保留当时解压位置；重新运行请使用程序包根目录CMD入口。
quick只有旧种子101的小网格，不是确认性A8。formal是符号协议模型检查；figures仅从历史结果重绘。
完整旧A8网格本轮未重跑；当前严格A8 NOT_RUN。最终包的实体另一电脑验收尚待真人执行。
""", encoding="utf-8-sig")
    for p in (E34 / "browser").iterdir():
        if p.is_file() and p.suffix in {".png", ".txt", ".json"}:
            copy(p, evidence / "browser" / p.name)
    repro = args.bundle / "reproduction_outputs"
    replica = out / evidence / "离线复现"
    sessions = []
    for mode in ("quick", "formal", "figures"):
        matches = sorted(repro.glob(mode + "-*"))
        if len(matches) != 1:
            raise SystemExit(f"Expected one verified {mode} session, found {len(matches)}")
        source = matches[0]
        shutil.copytree(source, replica / "reproduction_outputs" / source.name)
        session = json.loads((source / "session.json").read_text(encoding="utf-8"))
        if session["status"] != "PASSED":
            raise SystemExit(f"Incomplete reproduction: {source}")
        for job in session["jobs"]:
            relative = job.get("output_dir")
            if not relative:
                continue
            origin = (args.bundle / relative).resolve()
            if not origin.is_relative_to(args.bundle.resolve()):
                raise SystemExit(f"Unexpected reproduction output outside bundle: {origin}")
            destination = replica / relative
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(origin, destination)
        sessions.append(source.name)
    for relative in ("先读我_使用指南.html", "复现索引.json", "application/THIRD_PARTY_LICENSES.md"):
        copy(args.bundle / relative, evidence / "离线复现" / relative)
    (replica / "00_本目录为证据副本.txt").write_text("本目录保留本轮新运行原件及原相对链接，不是可执行程序。运行软件或重新计算，请解压交付中的完整程序ZIP并使用其根目录入口；此处指南也是原件副本。\n", encoding="utf-8-sig")

    summary = {
        "release_id": "E34", "created_at": datetime.now(timezone.utc).isoformat(),
        "program": {"file": args.program.name, "sha256": digest(args.program), "bytes": args.program.stat().st_size},
        "main_report": {"file": report.name, "pages": args.report_pages, "sha256": digest(report), "bytes": report.stat().st_size},
        "intro": {"file": intro.name, "pages": 1, "sha256": digest(intro)},
        "validation": {"developer_python_passed": 239, "portable_python_passed": 239, "frontend_automated_passed": 104,
            "browser_observed_groups": 17, "quick_rows": 216, "quick_seeds": [101],
            "quick_is_statistical_confirmation": False, "full_historical_grid_rerun": False,
            "strict_a8_status": "NOT_RUN", "descriptive_four_method_status": "AVAILABLE",
            "physical_second_computer": "PENDING", "reproduction_sessions": sessions},
        "pending_human_actions": ["冻结程序包在另一台实体 Windows x64 电脑验收", "真人确认贡献、来源、声明并签字", "核实报名和学校资格审核、按平台要求命名并上传"],
        "excluded": ["内部交接文档", "05和09内部任务文件", "个人身份信息和签字", "原始来件和旧程序包", "运行环境测试临时目录"],
    }
    (out / "交付与验证摘要.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "实体第二电脑验收表_待真人填写.txt").write_text(f"""PrivEdge E34 实体第二电脑验收表

状态：待真实执行。本表不是完成证明，不预填通过结果。
受测程序：{args.program.name}
SHA-256：{digest(args.program)}
验收日期：__________  验收人称呼：__________
电脑与开发机器是否为不同实体：__________
Windows版本/架构：__________  解压位置：__________

逐项填写通过/失败、实际现象与记录位置：
1. 将完整程序ZIP解压到短且可写的路径（如D:\\PrivEdge）；双击验证程序.cmd，冻结文件核对与三数据自检：__________
2. 双击运行测试.cmd，填写实际结果（本版参考239 passed；3条已知警告保留）：__________
3. 双击启动程序.cmd，自动打开或复制窗口网址后进入五页控制台：__________
4. 总览的正常交换预设，TRD/商圈3/ε1/m20/5000/seed20260929，10项输出、DEGRADED、Recall .7、NDCG约.8968：__________
5. 同参数合法签名权重劫持，网关可接受；AS基线3/3、PrivEdge1/3，页面按真实结果解释：__________
6. 未重签摘要篡改，出现SIGNATURE_INVALID拒收；账本副本篡改出现REFUSED/LEDGER_CORRUPTED，原链不变：__________
7. 实验中心严格A8为NOT_RUN、描述性四方法可用；不得写成当前现场重算：__________
8. 下载本次记录JSON，核对种子、数据集、E34版本与来源指纹；重放产生新窗口和编号：__________
9. Ctrl+C停止程序后重新启动，账本与临时密钥重建（不是持久化账本）：__________
10. 双击快速核心统计复现.cmd，三数据小网格与独立复核完成；保存结果索引/日志：__________

失败时保留原始错误，不直接改已冻结包。把本表及对应记录交给队长，修正后需要新版本和重新冻结。
物理第二电脑通过只支撑兼容与操作验收，不构成统计确认性复验，也不代表真实部署安全。
""", encoding="utf-8-sig")
    (out / "00_先读我.txt").write_text(f"""PrivEdge E34 评审整编完整资料

1. 作品报告：{report.name}（{args.report_pages}页，匿名正文，低于10 MB）。
2. 作品简介：{intro.name}（单页）。
3. 可执行程序：完整解压 {args.program.name}，进入得到的程序文件夹。
   双击“启动程序.cmd”；先读“先读我_使用指南.html”。无需另装Python或Node，无需联网安装。
4. 可编辑文档：Word正文、简介和工程历史附件；修改后需重新核对PDF。
5. 工程验收证据：当前测试、真实页面检查、离线quick/formal/figures输出；这是工程证据，不是新增统计结论。

现场演示按总览的四步引导：正常摘要交换 → 合法签名数值投毒 → 未重签篡改 → 账本与历史证据。
可以改参数、固定种子重放、导出本次记录。正常示例也可能降级，检查通过不等于预测准确。

程序包内分别提供：验证程序、运行测试、快速核心统计复现、重跑形式化验证、从历史证据重建图表、完整A8四方法重算。
快速复现仅用旧种子101、小网格共216行，不能升级为确认性结论。完整A8入口重算旧网格，本轮仅核对计划，未执行完整网格。
严格A8仍为NOT_RUN；已有四方法结果按描述性证据呈现。标准表到结果可复现；Olist/Massive从外部原始数据重建的预处理脚本仍不完整。

实际提交时，按平台要求把“报告PDF”和“可执行程序ZIP”等文件分别上传；本总资料ZIP用于保管和转交，不假定平台接受它作为唯一文件。
按“队长姓名+作品名称+资料名称”重命名上传件，真实姓名由队长填写。匿名正文不加学校、指导老师或队员身份。
补充材料是否单独上传、程序ZIP容量上限、声明位置，以当前报名平台为准。
真人声明与签字未伪造。请核实报名与学校审核，再完成实际上传。2026-10-18 23:59为报名截止，作品提交截止2026-10-22。
最终包还须在另一台实体Windows x64电脑验收；本机新目录验收不能替代这一步。

本资料不含内部交接文档、05/09内部任务清单。Git未提交、未推送。
文件完整性见“文件清单_SHA256.json”；程序包内部另有自己的完整性清单。
""", encoding="utf-8-sig")
    paths = sorted(p for p in out.rglob("*") if p.is_file())
    forbidden = [p for p in paths if "交接_下一级" in p.name or p.name.startswith(("05_", "09_"))]
    if forbidden:
        raise SystemExit(f"Private path unexpectedly selected: {forbidden}")
    manifest = {p.relative_to(out).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size} for p in paths}
    (out / "文件清单_SHA256.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file():
                z.write(p, f"{out.name}/{p.relative_to(out).as_posix()}")
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise SystemExit("Archive integrity failed.")
        for relative, item in manifest.items():
            content = z.read(f"{out.name}/{relative}")
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise SystemExit(f"Archive mismatch: {relative}")
    result = {"directory": str(out), "archive": str(archive), "files": len(manifest) + 1,
              "bytes": archive.stat().st_size, "sha256": digest(archive), "archive_readback_all_hashes_match": True,
              "report_sha256": digest(report), "program_sha256": digest(args.program)}
    (E34 / "complete_delivery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
