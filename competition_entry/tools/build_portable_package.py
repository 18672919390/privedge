"""Build an offline Windows x64 folder from already-installed locked dependencies.

Use the project's Python interpreter. Downloads only optional license texts, never
installs software; --license-dir allows a fully offline repeat after first review.
Existing bundles and scientific evidence are never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from datetime import datetime
from importlib import metadata
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = TOOL_DIR.parents[1]
ROOT = SOURCE_ROOT if (SOURCE_ROOT / "privedge").is_dir() else SOURCE_ROOT.parent
PROJECT = ROOT / ("privedge" if (ROOT / "privedge").is_dir() else "application")
SKIP = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".git", ".agents", ".codex"}
NATIVE = {"_asyncio.pyd", "_ctypes.pyd", "_decimal.pyd", "_elementtree.pyd", "_hashlib.pyd",
          "_multiprocessing.pyd", "_overlapped.pyd", "_queue.pyd", "_socket.pyd", "_ssl.pyd",
          "_uuid.pyd", "_wmi.pyd", "_zoneinfo.pyd", "libcrypto-3-x64.dll", "libssl-3-x64.dll",
          "libffi-8.dll", "pyexpat.pyd", "select.pyd", "unicodedata.pyd"}
LICENSE_URLS = {
    "OpenSSL-LICENSE.txt": "https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.8/LICENSE.txt",
    "libffi-LICENSE.txt": "https://raw.githubusercontent.com/libffi/libffi/master/LICENSE",
    "Expat-COPYING.txt": "https://raw.githubusercontent.com/libexpat/libexpat/R_2_8_3/expat/COPYING",
}
PROVERIF_SOURCE_SHA = "4871f53c32ab4a04669a060c4886ba5d9080496963fb980a9a62d2c429ceabc4"
PROVERIF_EXE_SHA = "702273912616a46919d5a2ecd0c5465cffdea9ff66296171d44d01d1700b8894"
TOOL_SOURCES = ("build_portable_package.py", "portable_launcher.py", "portable_reproduction.py")


def dependency_locks(project: Path) -> dict[str, tuple[str, str]]:
    result = {}
    for filename in ("requirements.lock", "requirements-reproduction.lock"):
        for line in (project / filename).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, version = line.split("==", 1)
            key = name.lower().replace("_", "-")
            if key in result and result[key][1] != version:
                raise ValueError(f"Conflicting dependency pin: {name}")
            result[key] = (name, version)
    return result


def check_proverif(directory: Path, source: Path) -> dict:
    if sha(source) != PROVERIF_SOURCE_SHA or sha(directory / "proverif.exe") != PROVERIF_EXE_SHA:
        raise ValueError("ProVerif executable/source differs from the reviewed 2.05 artifacts")
    with tarfile.open(source, "r:gz") as archive:
        version = archive.extractfile("proverif2.05/src/version.ml").read().decode("utf-8")
        if 'let version = "2.05"' not in version:
            raise ValueError("Unexpected ProVerif source version")
        for name in ("LICENSE", "CHANGES"):
            if archive.extractfile(f"proverif2.05/{name}").read() != (directory / name).read_bytes():
                raise ValueError(f"ProVerif source/binary notice mismatch: {name}")
    return {"name": "ProVerif", "version": "2.05", "license": "GPL-2.0-or-later",
            "unmodified": True,
            "source_url": "https://bblanche.gitlabpages.inria.fr/proverif/proverif2.05.tar.gz",
            "source_archive": "third_party_sources/proverif2.05.tar.gz", "source_sha256": sha(source),
            "executable": "tools/proverif/proverif2.05/proverif.exe", "executable_sha256": sha(directory / "proverif.exe"),
            "binary_distribution": "proverifbin2.05.tar.gz",
            "binary_distribution_sha256": "7b402ce05343e8819c8f05b871105c06d96d5c86556035fa3db4ad24c0820a32",
            "binary_origin_note": "Existing Windows 2.05 distribution; executable byte-matched to the original local archive during E34 review.",
            "notice_files": {name: sha(directory / name) for name in ("LICENSE", "README", "CHANGES")},
            "build_instructions": "The complete source archive includes README, build and build.bat; rebuilding the tool requires OCaml 4.03+. The supplied Windows executable does not.",
            "verification_scope": "Version and source-material match; reproducible compilation of the tool binary is not claimed."}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allowed(path: Path) -> bool:
    return not any(p in SKIP for p in path.parts) and path.name not in {".env", "kaggle.json", "direct_url.json"} and path.suffix not in {".pem", ".key", ".pyc", ".tsbuildinfo"}


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--license-dir", type=Path, required=True)
    parser.add_argument("--fetch-license-texts", action="store_true")
    parser.add_argument("--expected-tests", type=int, default=0)
    parser.add_argument("--proverif-dir", type=Path, default=ROOT / "tools/proverif/proverif2.05")
    parser.add_argument("--proverif-source", type=Path, default=ROOT / "third_party_sources/proverif2.05.tar.gz")
    parser.add_argument("--output-dir", type=Path, help="New destination folder; must not exist")
    args = parser.parse_args()
    assert sys.platform == "win32" and sys.maxsize > 2**32 and sys.version_info[:2] == (3, 12)
    base = Path(sys.base_prefix)
    verifier = check_proverif(args.proverif_dir, args.proverif_source)
    locked = dependency_locks(PROJECT)
    for name in TOOL_SOURCES:
        if not (TOOL_DIR / name).is_file():
            raise FileNotFoundError(f"Missing tool source: {name}")
    for name in ("先读我_使用指南.html", "复现索引.json"):
        if not (TOOL_DIR / "portable_assets" / name).is_file():
            raise FileNotFoundError(f"Missing offline guide asset: {name}")
    args.license_dir.mkdir(parents=True, exist_ok=True)
    license_sources = {}
    for name, url in LICENSE_URLS.items():
        cached = args.license_dir / name
        if args.fetch_license_texts and not cached.exists():
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
            if b"License" not in data and b"Permission" not in data:
                raise ValueError(f"Expected license text: {name}")
            cached.write_bytes(data)
        if not cached.is_file():
            raise FileNotFoundError(f"Review and provide license text: {cached}")
        license_sources[name] = {"source": url, "sha256": sha(cached)}
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    bundle = (args.output_dir or ROOT / "share" / f"PrivEdge_Windows_x64_E34_{stamp}").resolve()
    if any(bundle.is_relative_to(path.resolve()) for path in (PROJECT, TOOL_DIR, base)):
        raise ValueError("Output folder must not be inside application, tool sources or source runtime")
    bundle.mkdir(parents=True, exist_ok=False)
    runtime = bundle / "runtime"
    app = bundle / "application"
    for name in ("python.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        copy(base / name, runtime / name)
    for name in sorted(NATIVE):
        copy(base / "DLLs" / name, runtime / "DLLs" / name)
    stdlib_excluded = {"site-packages", "test", "tests", "tkinter", "idlelib", "turtledemo", "ensurepip", "venv", "__pycache__"}
    if (base / "Lib").is_dir():
        with zipfile.ZipFile(runtime / "python312.zip", "x", zipfile.ZIP_DEFLATED) as z:
            for path in sorted((base / "Lib").rglob("*")):
                relative = path.relative_to(base / "Lib")
                if path.is_file() and not any(part in stdlib_excluded for part in relative.parts) and path.suffix != ".pyc":
                    z.write(path, relative.as_posix())
    elif (base / "python312.zip").is_file():
        copy(base / "python312.zip", runtime / "python312.zip")
    else:
        raise FileNotFoundError("No complete local Python standard library found")
    (runtime / "python312._pth").write_text("python312.zip\n.\nDLLs\nsite-packages\n../application\n", encoding="ascii")
    dependencies = []
    for name, version in locked.values():
        dist = metadata.distribution(name)
        if dist.version != version:
            raise ValueError(f"Installed version does not match lock: {name}")
        source_root = Path(dist.locate_file("")).resolve()
        license_files = []
        for member in dist.files or []:
            relative = Path(str(member))
            if relative.is_absolute() or ".." in relative.parts or not allowed(relative):
                continue
            source = Path(dist.locate_file(member)).resolve()
            if not source.is_relative_to(source_root):
                raise ValueError(f"Distribution path leaves site-packages: {name}")
            if source.is_file():
                target = runtime / "site-packages" / relative
                copy(source, target)
                if any(p.lower().startswith(("license", "notice", "copying")) for p in relative.parts) and source.suffix in {"", ".txt", ".md", ".APACHE", ".BSD", ".external"}:
                    license_files.append(target.relative_to(bundle).as_posix())
        if not license_files:
            raise ValueError(f"No installed license notice found: {name}")
        dependencies.append({"name": dist.metadata["Name"], "version": version, "license_files": license_files})
    for source in sorted(PROJECT.rglob("*")):
        relative = source.relative_to(PROJECT)
        if source.is_file() and allowed(relative):
            if not source.resolve().is_relative_to(PROJECT.resolve()):
                raise ValueError(f"Application source leaves project directory: {relative}")
            copy(source, app / relative)
    for package in ("react", "react-dom", "scheduler", "echarts", "zrender", "tslib"):
        for name in ("LICENSE", "LICENSE.txt", "NOTICE"):
            source = PROJECT / "web/node_modules" / package / name
            if not source.is_file():
                source = ROOT / "licenses/web" / package / name
            if source.is_file():
                copy(source, bundle / "licenses" / "web" / package / name)
    for name in LICENSE_URLS:
        copy(args.license_dir / name, bundle / "licenses" / "runtime" / name)
    copy(TOOL_DIR / "portable_launcher.py", bundle / "run_privedge.py")
    copy(TOOL_DIR / "portable_reproduction.py", bundle / "run_reproduction.py")
    for name in TOOL_SOURCES:
        copy(TOOL_DIR / name, bundle / "tool_sources/competition_entry/tools" / name)
    for path in sorted((TOOL_DIR / "portable_assets").rglob("*")):
        if path.is_file() and allowed(path.relative_to(TOOL_DIR)):
            relative = path.relative_to(TOOL_DIR / "portable_assets")
            copy(path, bundle / "tool_sources/competition_entry/tools/portable_assets" / relative)
            copy(path, bundle / relative)
    for name in ("proverif.exe", "LICENSE", "README", "CHANGES"):
        copy(args.proverif_dir / name, bundle / "tools/proverif/proverif2.05" / name)
    copy(args.proverif_source, bundle / "third_party_sources/proverif2.05.tar.gz")
    source_record = bundle / "licenses/proverif/SOURCE.json"
    source_record.parent.mkdir(parents=True, exist_ok=True)
    source_record.write_text(json.dumps(verifier, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, options in (("启动程序.cmd", ""), ("验证程序.cmd", "--check"), ("运行测试.cmd", "--tests")):
        text = '@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\n"runtime\\python.exe" -B -X utf8 "run_privedge.py" ' + options + '\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n'
        (bundle / name).write_bytes(text.encode("utf-8"))
    for name, mode in (("快速核心统计复现.cmd", "quick"), ("完整A8四方法重算.cmd", "full"),
                       ("重跑形式化验证.cmd", "formal"), ("从历史证据重建图表.cmd", "figures")):
        text = '@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\n"runtime\\python.exe" -B -X utf8 "run_reproduction.py" --mode ' + mode + '\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n'
        (bundle / name).write_bytes(text.encode("utf-8"))
    (bundle / "打开使用指南.cmd").write_bytes('@echo off\r\nchcp 65001 >nul\r\nstart "" "%~dp0先读我_使用指南.html"\r\n'.encode("utf-8"))
    test_note = f"构建时填写的测试基线为{args.expected_tests}项，实际结果以验收记录为准。" if args.expected_tests else "测试数量与结果以本版本实际验收记录为准。"
    instructions = f'''PrivEdge E34 Windows x64 离线程序与核心复现包（API 0.4.1）

先完整解压，再双击“打开使用指南.cmd”或“先读我_使用指南.html”。指南包含五页演示、参数、复现步骤及结果位置。
双击“启动程序.cmd”进入系统；无需安装Python、Node、ProVerif或联网安装依赖。只监听本机，优先8765，忙时自动换空闲端口，按窗口实际网址访问。关闭前按Ctrl+C。
“验证程序.cmd”检查文件哈希、三数据、双A8接口和账本副本；“运行测试.cmd”运行回归测试。{test_note}
“快速核心统计复现.cmd”是三数据小样本工程核验；“完整A8四方法重算.cmd”才执行完整既有A8网格。两者都使用旧种子，不构成新的确认性研究。
“重跑形式化验证.cmd”使用包内ProVerif2.05；“从历史证据重建图表.cmd”只重绘存档图表。两者独立于A8统计重算。
所有新增输出在reproduction_outputs/<新会话>/和application/runs/<实验>/<新ID>/，旧原件及实验中心登记不变。先看每个会话的结果索引.html；FAILED或INTERRUPTED不能当作完成。
标准表重算边界不包括从公开原始数据重建标准表，不包括完整论文排版。Windows兼容性及实体第二电脑终验以真实记录为准。
源码在application与tool_sources，两个依赖锁在application。ProVerif完整源码在third_party_sources，许可及来源哈希在licenses/proverif/SOURCE.json。制图依赖也已内置；不复制系统中文字体。
同进程演示，无登录，账本和密钥重启清空。“检查通过”不表示预测准确；历史A8是描述性结果。哈希检查不是第三方认证。
版本基准23546a1加未提交本地变更，文件版本以package_manifest.json为准。数据许可见application/THIRD_PARTY_LICENSES.md。正式报告、简介与真人声明按比赛要求另行提交，程序包不代替学校审核或实际提交。
'''
    (bundle / "使用说明.txt").write_text(instructions, encoding="utf-8-sig")
    (bundle / "dependency_inventory.json").write_text(json.dumps({"python": sys.version, "dependencies": dependencies,
        "lock_files": ["application/requirements.lock", "application/requirements-reproduction.lock"],
        "native_license_sources": license_sources, "external_tools": [verifier]}, ensure_ascii=False, indent=2), encoding="utf-8")
    files = {p.relative_to(bundle).as_posix(): sha(p) for p in sorted(bundle.rglob("*")) if p.is_file()}
    (bundle / "package_manifest.json").write_text(json.dumps({"delivery": "E34", "api_version": "0.4.1", "base_commit": "23546a1", "uncommitted_changes": True, "platform": "Windows x64", "files": files}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"bundle": str(bundle), "files": len(files) + 1, "dependencies": len(dependencies), "bytes": sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
