"""Build the team-internal material package: one folder plus one zip with code, data, results and docs.

Run with the project venv:
    D:\\比赛\\privedge\\.venv\\Scripts\\python.exe D:\\比赛\\competition_entry\\tools\\build_share_package.py
Outputs go to D:\\比赛\\share\\. Raw downloads, virtual environments, node_modules and caches are never included.
The markdown library is loaded from D:\\比赛\\tmp\\pydeps_md (pip install --target there).
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import io
import mimetypes
import re
import shutil
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
TASKS = DOCS / "09_任务清单（待认领）.md"

INCLUDE = [
    "privedge",
    "competition_entry/docs/v4",
    "competition_entry/tools",
    "review/top-k-share-20260925",
    "dataset_research/TRD_AUDIT_RESULT_20260929.md",
    "dataset_research/runs/olist_brazil",
    "competition_entry/v4_audit/outputs/massive_ldp_recompute_20260929.json",
]
SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".git"}
SKIP_FILES = {"tsconfig.tsbuildinfo"}
SECRET_PATTERN = re.compile(r"(\.env$|\.pem$|\.key$|kaggle\.json$|token|secret|credential|id_rsa)", re.I)

CSS = """
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;max-width:1280px;margin:32px auto;padding:0 20px;
line-height:1.7;color:#1f2328}
h1,h2,h3{border-bottom:1px solid #d8dee4;padding-bottom:.3em}
.tw{overflow-x:auto;margin:12px 0}table{border-collapse:collapse;width:100%}
th,td{border:1px solid #d0d7de;padding:6px 10px;vertical-align:top;min-width:3.5em}th{background:#f6f8fa}
td:first-child{white-space:nowrap}
code{background:#f6f8fa;padding:.1em .35em;border-radius:4px;font-size:90%}
pre{background:#f6f8fa;padding:12px;overflow-x:auto;border-radius:6px}pre code{padding:0}
img{max-width:100%;border:1px solid #d8dee4;border-radius:6px;margin:8px 0}
blockquote{color:#59636e;border-left:4px solid #d0d7de;margin:0;padding:0 1em}
nav{font-size:14px;margin-bottom:16px}nav a{margin-right:12px}
"""

CSV_COLUMNS = ["编号", "类别", "任务", "必做/可选", "做什么", "交付", "怎样算完成", "需要的能力", "人日", "建议截止",
               "依赖", "认领人", "协助人", "备注"]


def collect() -> list[tuple[Path, str]]:
    files = []
    for entry in INCLUDE:
        source = ROOT / entry
        paths = [source] if source.is_file() else sorted(p for p in source.rglob("*") if p.is_file())
        for path in paths:
            rel = path.relative_to(ROOT).as_posix()
            parts = rel.split("/")
            if any(p in SKIP_DIRS for p in parts) or parts[-1] in SKIP_FILES:
                continue
            if SECRET_PATTERN.search(path.name):
                raise SystemExit(f"refusing to package a possible credential file: {rel}")
            files.append((path, rel))
    return files


def _normalise(text: str) -> str:
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
            if starts_block and prev_is_text:
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
        return f'{match.group(1)}data:{mime};base64,{base64.b64encode(path.read_bytes()).decode("ascii")}"'
    return re.sub(r'(<img[^>]*?src=")([^"]+)"', replace, body)


def to_html(md_path: Path, title: str, nav: str) -> str:
    body = markdown.markdown(_normalise(md_path.read_text(encoding="utf-8")),
                             extensions=["tables", "fenced_code", "sane_lists", "toc"])
    body = _inline_images(body, md_path.parent)
    body = body.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body><nav>{nav}</nav>{body}</body></html>")


def html_docs() -> dict[str, bytes]:
    docs = sorted(DOCS.glob("*.md"))
    nav = '<a href="../从这里开始.html">从这里开始</a>' + "".join(
        f'<a href="{html.escape(d.stem)}.html">{html.escape(d.stem[:2])}</a>' for d in docs)
    out = {f"文档网页版/{d.stem}.html": to_html(d, d.stem, nav) for d in docs}
    out["文档网页版/privedge_README.html"] = to_html(ROOT / "privedge" / "README.md", "PrivEdge README", nav)
    start_nav = ('<a href="文档网页版/07_项目全景说明（团队共享版）.html">项目全景说明</a>'
                 '<a href="文档网页版/09_任务清单（待认领）.html">任务清单</a>')
    out["从这里开始.html"] = to_html(START, "从这里开始", start_nav)
    return {name: text.encode("utf-8") for name, text in out.items()}


def _cells(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return [re.sub(r"\*\*|`", "", c) for c in cells]


def task_csv() -> bytes:
    """Flatten every task row of the 09 task list into one sheet (UTF-8 with BOM so Excel opens it)."""
    rows, header, category = [], None, ""
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            category, header = line[4:].strip(), None
        elif line.startswith("|") and not re.match(r"^\|[\s\-|]+\|$", line):
            cells = _cells(line)
            if cells[0] == "编号":
                header = cells
            elif header and re.fullmatch(r"[A-DX]\d+", cells[0]):
                record = dict(zip(header, cells))
                record["类别"] = category
                record.setdefault("建议截止", record.get("截止", ""))
                rows.append(record)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    if len(rows) < 30:
        raise SystemExit(f"only {len(rows)} tasks parsed from {TASKS.name}")
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"))
    args = parser.parse_args()
    out_dir = ROOT / "share"
    out_dir.mkdir(exist_ok=True)
    name = f"PrivEdge_团队资料_{args.date}"
    folder, archive_path = out_dir / name, out_dir / f"{name}.zip"
    if folder.exists():
        shutil.rmtree(folder)

    entries: dict[str, bytes] = {rel: path.read_bytes() for path, rel in collect()}
    entries.update(html_docs())
    entries["从这里开始.md"] = START.read_bytes()
    entries["任务认领表.csv"] = task_csv()
    entries["文件清单.txt"] = ("\n".join(f"{sha256(data)}  {rel}" for rel, data in sorted(entries.items()))
                           + "\n").encode("utf-8")

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, data in entries.items():
            target = folder / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            archive.writestr(f"{name}/{rel}", data)
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip():
            raise SystemExit("CRC check failed")
    archive_path.with_suffix(".zip.sha256").write_text(f"{sha256(archive_path.read_bytes())}  {archive_path.name}\n",
                                                       encoding="utf-8")
    print(f"{folder}\n{archive_path}: {archive_path.stat().st_size / 1e6:.1f} MB, {len(entries)} files")


if __name__ == "__main__":
    main()
