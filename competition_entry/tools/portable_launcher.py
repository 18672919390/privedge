"""Entry point copied to the portable bundle; all modules come from that bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPLICATION = ROOT / "application"


def verify_files() -> dict:
    manifest = json.loads((ROOT / "package_manifest.json").read_text(encoding="utf-8"))
    errors = []
    for name, expected in manifest["files"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            errors.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(name)
    return {"files_checked": len(manifest["files"]), "ok": not errors, "mismatches": errors}


def functional_check() -> dict:
    from fastapi.testclient import TestClient
    from privedge.server.app import app

    client = TestClient(app)
    checks = {"homepage": client.get("/").status_code == 200,
              "legacy_evidence": client.get("/api/evidence").status_code == 200,
              "a8_status": client.get("/api/evidence/a8").json()["status"],
              "a8_descriptive_status": client.get("/api/evidence/a8/descriptive").json()["status"]}
    for dataset in client.get("/api/datasets").json():
        response = client.post("/api/run", json={"dataset": dataset["name"], "target": dataset["servers"][-1]["id"],
                               "epsilon": 2, "top_m": 40, "users": 1000, "seed": 1})
        drill = client.post(f"/api/ledger/{dataset['name']}/tamper-drill?seq=0").json()
        checks[dataset["name"]] = {"prediction_ok": response.status_code == 200,
                                    "decision": response.json().get("decision", {}).get("state"),
                                    "tamper_refused": drill.get("decision_state") == "REFUSED",
                                    "original_ledger_ok": client.get(f"/api/ledger/{dataset['name']}").json()["chain_ok"]}
    ok = (checks["homepage"] and checks["legacy_evidence"] and checks["a8_status"] != "INVALID"
          and checks["a8_descriptive_status"] == "AVAILABLE")
    ok = ok and all(checks[d]["prediction_ok"] and checks[d]["tamper_refused"] and checks[d]["original_ledger_ok"]
                    for d in ("massive_steps", "olist_brazil", "meituan_trd"))
    return {"ok": bool(ok), "checks": checks, "python": str(Path(sys.executable).relative_to(ROOT)),
            "all_import_paths_in_bundle": all(Path(p).resolve().is_relative_to(ROOT) for p in sys.path)}


def open_when_ready(url: str) -> None:
    # Timer runs outside the request thread; do not open a browser before startup.
    for _ in range(50):
        try:
            with urllib.request.urlopen(url + "api/evidence/a8", timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            threading.Event().wait(0.1)


def main() -> int:
    parser = argparse.ArgumentParser(description="PrivEdge local Windows console")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--integrity-only", action="store_true", help="Read file hashes without predictions or ledger drills")
    parser.add_argument("--tests", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not ROOT.joinpath("application", "web", "dist", "index.html").is_file():
        print("Package incomplete: extract the whole folder before starting.", flush=True)
        return 2
    integrity = verify_files()
    if not integrity["ok"]:
        print(json.dumps({"integrity": integrity}, ensure_ascii=False), flush=True)
        return 2
    if args.integrity_only:
        print(json.dumps({"integrity": integrity}, ensure_ascii=False), flush=True)
        return 0
    if args.tests:
        return subprocess.call([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=APPLICATION)
    if args.check:
        report = {"integrity": integrity, "functional": functional_check()}
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if report["functional"]["ok"] and report["functional"]["all_import_paths_in_bundle"] else 2
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # Reserve the selected socket throughout startup; do not kill other services.
        try:
            listener.bind(("127.0.0.1", args.port))
        except OSError:
            listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        url = f"http://127.0.0.1:{listener.getsockname()[1]}/"
        print(f"PrivEdge: {url}\nPress Ctrl+C to stop. Ledger state is cleared on restart.", flush=True)
        if not args.no_browser:
            threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
        uvicorn.Server(uvicorn.Config("privedge.server.app:app", host="127.0.0.1", log_level="warning")).run(sockets=[listener])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
