"""Append E34 facts and point working documents to the frozen delivery."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "competition_entry/docs/v4"
E34 = DOCS / "backend_validation/20261017_review_delivery"


def save(path, text):
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    path.write_bytes(text.replace("\r\n", "\n").replace("\n", newline).encode("utf-8"))


def main():
    delivery = json.loads((E34 / "complete_delivery.json").read_text(encoding="utf-8"))
    summary = json.loads((Path(delivery["directory"]) / "交付与验证摘要.json").read_text(encoding="utf-8"))
    previous = json.loads((E34 / "protected_before.json").read_text(encoding="utf-8"))["files"]
    changed = [name for name, old in previous.items() if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != old]
    protected = {"checked": len(previous), "changed": changed, "passed": not changed}
    (E34 / "protected_final.json").write_text(json.dumps(protected, ensure_ascii=False, indent=2), encoding="utf-8")
    if changed:
        raise SystemExit(f"Protected artifacts changed: {changed}")
    program = summary["program"]
    report = summary["main_report"]
    paragraph = f"""### E34 评审整编、引导演示与离线复现验收 2026-10-17

本轮先冻结 `REVIEW_DELIVERY_ACCEPTANCE_20261017.md`，再修改与验收。目标是报告整体性、页面可解释性、离线程序完整性，不产生新的算法优越性结论。

- 报告按“安全问题—设计—证据—边界”整编，当前匿名PDF为 `{report['file']}`，{report['pages']}页、{report['bytes']}字节；单页简介为 `PrivEdge_作品简介_20261017.pdf`。工程修复过程移到28页历史附件，不替代正文核心证明与不利结果。
- 前端增加四步引导、种子重放、正常参数带入攻击、按页/数据集保留已完成结果和JSON导出；公开版本接口提供白名单源码与数据指纹。AS明确分子/分母；真实浏览器发现1/3与0.3333的舍入误报后已修复并复验。客户端切页停止接收及后续巡检，不保证终止已开始的后端计算。
- 开发与包内完整Python回归各 **239 passed**（3个既有极小ε数值警告）；前端 **104项自动检查**、**17组真实浏览器观察**。三数据合法请求与E33相同，已登记科学证据响应相同；24份预注册比原23份新增本轮计划。初次检查脚本误把允许的新计划判为差异，原失败与修正依据均保留。
- 新包内实际运行：quick三数据各首目标、旧种子101、ε=1/2、9场景、4方法，共216行并通过独立复核；属于工程烟测，不能作为确认性统计。ProVerif Q1–Q5、S1/S2及4负对照符合预期；历史图表重绘7组、14个PNG/SVG。完整历史A8网格仅核验运行计划，未重跑；严格A8仍NOT_RUN，描述性四方法结果AVAILABLE。
- 程序含隔离CPython、38项依赖、标准表、前端源码/dist、实验与复核代码、历史结果、复现工具及ProVerif二进制/对应版本源码/许可。新压缩包按冻结清单封装，排除测试临时目录与新运行派生文件；新目录解压后核对清单并自检。{len(previous)}个既有受保护文件哈希不变。
- 当前程序 `share/{program['file']}`，{program['bytes']}字节，SHA-256 `{program['sha256']}`。完整转交资料 `share/{Path(delivery['archive']).name}`，SHA-256 `{delivery['sha256']}`。报告SHA-256 `{report['sha256']}`。

工程记录在 `backend_validation/20261017_review_delivery/`；最终汇总 `portable_final_validation.json`、`browser_validation.json`、`complete_delivery.json`、`protected_final.json`。本机解压验收不替代实体第二电脑；学校审核、实际上传与真人声明仍待用户完成。新包不含内部交接文档；未commit或push。

"""
    p = DOCS / "02_实验证据登记.md"
    text = p.read_text(encoding="utf-8")
    if "### E34 " in text:
        raise SystemExit("E34 evidence already registered")
    text = text.replace("所有运行目录都在 `D:\\比赛\\privedge\\runs\\` 下，均带 `manifest.json`（代码指纹、环境、数据 SHA-256）。", "历史统计运行目录在 `D:\\比赛\\privedge\\runs\\` 下，带 `manifest.json`（代码指纹、环境、数据 SHA-256）；后续工程验收与新增离线复现按各E编号列明独立位置。")
    text = text.replace("## 1.1 设计审查中发现并修复的缺陷", paragraph + "## 1.1 设计审查中发现并修复的缺陷", 1)
    text = text.split("## 3 待完成（按优先级）")[0] + """## 3 待完成（按优先级）

1. 用户核实cpipc报名状态，报名截止2026-10-18 23:59；作品提交截止10-22，提交前须通过学校资格审核。
2. 冻结E34包在另一台实体Windows x64电脑完成启动、五页操作、退出及重启验收；保留实际系统信息、包SHA-256与记录。
3. 真人核实贡献、代码和数据来源，填写并签署要求的声明；匿名正文与身份材料分开。
4. 按报名系统实际文件格式、容量、声明位置和命名要求上传报告、程序及要求的附件。当前资料齐备不代表平台已提交。

完整旧统计网格、本轮冻结以外的算法扩展和视频不列为当前补做门槛；视频仅当届通知明确要求时做。严格确认性A8仍未完成，当前报告仅使用已核对的描述性四方法结论；如另行开展，须另写预注册并使用真正未用种子，不得改写旧证据身份。
"""
    save(p, text)
    p = DOCS / "08_相对团队原始研究代码的改动记录.md"
    text = p.read_text(encoding="utf-8")
    text += "\n| 10-17 | E34：增加评审四步引导、固定种子/参数带入/结果保留/JSON导出、白名单版本指纹接口；修复AS分数与四位小数比较的舍入误报；增加离线quick/formal/figures/full入口和完整复现工具链，整编报告/简介/指南 | `server/version.py`、`server/app.py`、`web/src/`及dist、新增测试、README与requirements-reproduction.lock；portable工具 | 默认统计管线不变；三数据合法结果及历史科学证据不变，303个受保护文件不变；quick216行仅工程烟测，严格A8仍NOT_RUN | E34；开发/包内各239 passed（3旧警告）、104前端自动检查、17真实浏览器组、包内离线复现与新ZIP解压自检；`backend_validation/20261017_review_delivery/` |\n"
    save(p, text)
    p = DOCS / "09_任务清单（待认领）.md"
    text = p.read_text(encoding="utf-8")
    first, remainder = text.split("\n", 1)
    current = f"""2026-10-17 E34 当前状态：报告、简介、引导演示、证据导出、离线复现工具链与新程序包已完成。主报告改为《PrivEdge_作品报告_评审整编版_20261017》（匿名PDF {report['pages']}页），工程历史独立附录28页，作品简介1页。程序使用 `share/{program['file']}`；完整资料使用 `share/{Path(delivery['archive']).name}`。开发与包内各239项Python、104项前端自动检查、17组真实浏览器观察通过；quick216行、形式化与图表重绘均在包内实际执行。既有303文件不变。算法、B与前端没有源码补交阻塞。

当前仍需真人完成：①核实报名和学校资格审核；②最终E34冻结包在另一台实体电脑验收；③贡献/来源/声明确认与签字；④按平台要求重命名并上传。严格确认性A8仍NOT_RUN，描述性四方法结果可用且已写清限制；不以重跑旧种子冒充确认性结果。具体记录见02的E34及 `backend_validation/20261017_review_delivery/`。

以下保留10月12日起的分工与历史推进记录；其中早期“待交/未合并/46项测试”等状态只描述当时，不代表当前缺口，以上述E34当前状态为准。
"""
    save(p, current + remainder)
    p = ROOT / "competition_entry/tools/从这里开始.md"
    text = p.read_text(encoding="utf-8")
    note = f"> 2026-10-17：以下为早期资料包的源码协作说明。当前评审程序请使用 `share/{program['file']}`，解压后双击 `启动程序.cmd`，无需执行下面的联网安装步骤。当前报告、简介和全部转交材料见 `share/{Path(delivery['archive']).name}`；验证事实见E34。\n\n"
    save(p, note + text)
    print(json.dumps({"registered": "E34", "protected": protected, "documents_updated": 4}, ensure_ascii=False))


if __name__ == "__main__":
    main()
