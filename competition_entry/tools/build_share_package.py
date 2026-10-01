"""Build the team share package (code, docs, results, HTML docs) and a separate data package.

Run from anywhere with the project venv:
    D:\\比赛\\privedge\\.venv\\Scripts\\python.exe D:\\比赛\\competition_entry\\tools\\build_share_package.py
Outputs go to D:\\比赛\\share\\. Raw datasets, virtual environments, node_modules and caches are never included;
the exported datasets go only into the separate data package.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import mimetypes
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tmp" / "pydeps_md"))
import markdown  # noqa: E402

DOCS = ROOT / "competition_entry" / "docs" / "v4"
START = TOOLS / "从这里开始.md"

INCLUDE = [
    "privedge",
    "competition_entry/docs/v4",
    "review/top-k-share-20260925",
    "dataset_research/TRD_AUDIT_RESULT_20260929.md",
    "dataset_research/runs/olist_brazil",
    "competition_entry/v4_audit/outputs/massive_ldp_recompute_20260929.json",
]
SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".git"}
SKIP_FILES = {"tsconfig.tsbuildinfo"}
DATA_DIR = "privedge/data"
SECRET_PATTERN = re.compile(r"(\.env$|\.pem$|\.key$|kaggle\.json$|token|secret|credential|id_rsa)", re.I)

CSS = """
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;max-width:980px;margin:32px auto;padding:0 20px;
line-height:1.7;color:#1f2328}
h1,h2,h3{border-bottom:1px solid #d8dee4;padding-bottom:.3em}
table{border-collapse:collapse;margin:12px 0;display:block;overflow-x:auto}
th,td{border:1px solid #d0d7de;padding:6px 10px;vertical-align:top}th{background:#f6f8fa}
code{background:#f6f8fa;padding:.1em .35em;border-radius:4px;font-size:90%}
pre{background:#f6f8fa;padding:12px;overflow-x:auto;border-radius:6px}pre code{padding:0}
img{max-width:100%;border:1px solid #d8dee4;border-radius:6px;margin:8px 0}
blockquote{color:#59636e;border-left:4px solid #d0d7de;margin:0;padding:0 1em}
nav{font-size:14px;margin-bottom:16px}nav a{margin-right:12px}
"""


def skipped(rel: str) -> bool:
    parts = rel.split("/")
    return (
        rel == DATA_DIR or rel.startswith(DATA_DIR + "/")
        or any(p in SKIP_DIRS for p in parts)
        or parts[-1] in SKIP_FILES
    )


def collect() -> list[tuple[Path, str]]:
    files = []
    for entry in INCLUDE:
        source = ROOT / entry
        paths = [source] if source.is_file() else sorted(p for p in source.rglob("*") if p.is_file())
        for path in paths:
            rel = path.relative_to(ROOT).as_posix()
            if skipped(rel):
                continue
            if SECRET_PATTERN.search(path.name):
                raise SystemExit(f"refusing to package a possible credential file: {rel}")
            files.append((path, rel))
    return files


def _nest_lists(text: str) -> str:
    """Adapt GitHub-style Markdown to Python-Markdown.

    Python-Markdown nests lists only with 4-space indents (the docs use 2 or 3, one level deep)
    and needs a blank line before a list or table that follows a paragraph line.
    """
    item = re.compile(r"^ *(?:[-*]|\d+\.) ")
    out: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            line = re.sub(r"^ {1,3}(?=(?:[-*]|\d+\.) )", "    ", line)
            prev = out[-1] if out else ""
            starts_block = item.match(line) or line.startswith("|")
            prev_is_text = prev.strip() and not item.match(prev) and not prev.startswith(("|", "    ", ">", "#"))
            if starts_block and prev_is_text and not (line.startswith("|") and prev.startswith("|")):
                out.append("")
        out.append(line)
    return "\n".join(out)


def _inline_images(body: str, base: Path) -> str:
    def replace(match: re.Match) -> str:
        src = match.group(2)
        path = (base / src).resolve()
        if src.startswith(("http:", "https:", "data:")) or not path.exists():
            return match.group(0)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f'{match.group(1)}data:{mime};base64,{data}"'
    return re.sub(r'(<img[^>]*?src=")([^"]+)"', replace, body)


def to_html(md_path: Path, title: str, nav: str) -> str:
    text = _nest_lists(md_path.read_text(encoding="utf-8"))
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "toc"])
    body = _inline_images(body, md_path.parent)
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body><nav>{nav}</nav>{body}</body></html>")


def html_docs() -> dict[str, str]:
    docs = sorted(DOCS.glob("*.md"))
    names = {doc: doc.stem + ".html" for doc in docs}
    nav = '<a href="../从这里开始.html">从这里开始</a>' + "".join(
        f'<a href="{html.escape(names[d])}">{html.escape(d.stem[:2])}</a>' for d in docs)
    out = {f"文档网页版/{names[d]}": to_html(d, d.stem, nav) for d in docs}
    out["文档网页版/privedge_README.html"] = to_html(ROOT / "privedge" / "README.md", "PrivEdge README", nav)
    start_nav = '<a href="文档网页版/07_项目全景说明（团队共享版）.html">项目全景说明</a>'
    out["从这里开始.html"] = to_html(START, "从这里开始", start_nav)
    return out


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_zip(target: Path, top: str, files: list[tuple[Path, str]], extra: dict[str, bytes],
              manifest: str = "文件清单.txt") -> None:
    manifest_lines = []
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, rel in files:
            data = path.read_bytes()
            archive.writestr(f"{top}/{rel}", data)
            manifest_lines.append(f"{sha256(data)}  {rel}")
        for rel, data in extra.items():
            archive.writestr(f"{top}/{rel}", data)
            manifest_lines.append(f"{sha256(data)}  {rel}")
        archive.writestr(f"{top}/{manifest}", "\n".join(sorted(manifest_lines, key=lambda l: l[66:])) + "\n")
    with zipfile.ZipFile(target) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit(f"CRC check failed for {bad}")
    digest = sha256(target.read_bytes())
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")


DATA_NOTE = """# PrivEdge 数据包说明

把本压缩包解压到共享包的同一个文件夹（与 `从这里开始.html` 同级），会得到 `privedge/data/` 下的三套数据：

| 文件夹 | 来源 | 许可 | 内容 |
|---|---|---|---|
| `meituan_trd` | 美团外卖 TRD，Zenodo DOI 10.5281/zenodo.8025855（上传者 Liu Yijian） | CC BY 4.0（使用时须署名） | 北京 11 个商圈的首单品类，品类已匿名为编号 |
| `olist_brazil` | Kaggle `olistbr/brazilian-ecommerce` | CC BY-NC-SA 4.0（仅限非商业用途，衍生物须同许可） | 巴西各州首单品类 + 公开上下文 |
| `massive_steps` | Massive-STEPS（Semantic Trails，CC0） | CC0；代码 Apache-2.0 | 城市签到类别 + 公开上下文 |

这些是由 `privedge/privedge/adapters/export_*.py` 从公开原始数据导出的标准化文件（每用户一条事件），不含姓名、手机号等个人信息。仅限队内用于本作品，不要公开传播。详细许可见 `privedge/THIRD_PARTY_LICENSES.md`。
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"))
    args = parser.parse_args()
    out_dir = ROOT / "share"
    out_dir.mkdir(exist_ok=True)

    main_top = f"PrivEdge_团队共享包_{args.date}"
    files = collect()
    extra = {rel: text.encode("utf-8") for rel, text in html_docs().items()}
    extra["从这里开始.md"] = START.read_bytes()
    main_zip = out_dir / f"{main_top}.zip"
    write_zip(main_zip, main_top, files, extra)

    data_root = ROOT / DATA_DIR
    data_files = [(p, p.relative_to(ROOT).as_posix()) for p in sorted(data_root.rglob("*")) if p.is_file()]
    data_zip = out_dir / f"PrivEdge_数据包_{args.date}.zip"
    write_zip(data_zip, main_top, data_files, {"数据说明与许可.md": DATA_NOTE.encode("utf-8")},
              manifest="数据包文件清单.txt")

    for path, count in ((main_zip, len(files) + len(extra)), (data_zip, len(data_files) + 1)):
        print(f"{path.name}: {path.stat().st_size / 1e6:.1f} MB, {count} files + manifest")


if __name__ == "__main__":
    main()
