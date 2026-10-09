"""PrivEdge console backend: REST + WebSocket over the live demo engine and the registered runs.

Run:  python -m uvicorn privedge.server.app:app --port 8765
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import DATASETS, engine
from .evidence import evidence, prereg_documents

WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

app = FastAPI(title="PrivEdge 控制台 API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    dataset: str = "meituan_trd"
    target: str
    epsilon: float = Field(2.0, gt=0, le=4.0)
    top_m: int = Field(40, ge=10, le=80)
    users: int = Field(5000, ge=1000, le=20000)
    attack: str = "none"
    attackers: int = Field(1, ge=1, le=3)
    beta: float = Field(0.10, ge=0.0, le=0.3)
    seed: int | None = None


def _engine(dataset: str):
    try:
        return engine(dataset)
    except ValueError as err:
        raise HTTPException(404, str(err)) from err


@app.get("/api/datasets")
def datasets() -> list[dict]:
    return [_engine(name).describe() for name in DATASETS]


@app.post("/api/run")
def run(request: RunRequest) -> dict:
    try:
        return _engine(request.dataset).run(**request.model_dump(exclude={"dataset"}))
    except ValueError as err:
        raise HTTPException(400, str(err)) from err


@app.websocket("/ws/run")
async def run_stream(socket: WebSocket) -> None:
    """Stream each pipeline step as it executes, then the final result."""
    await socket.accept()
    loop = asyncio.get_running_loop()
    try:
        while True:
            request = RunRequest(**await socket.receive_json())
            queue: asyncio.Queue = asyncio.Queue()

            def emit(event: dict) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, {"kind": "event", "event": event})

            def work() -> None:
                try:
                    result = _engine(request.dataset).run(**request.model_dump(exclude={"dataset"}), emit=emit)
                    loop.call_soon_threadsafe(queue.put_nowait, {"kind": "result", "result": result})
                except Exception as err:  # noqa: BLE001 - reported to the client
                    loop.call_soon_threadsafe(queue.put_nowait, {"kind": "error", "error": str(err)})

            threading.Thread(target=work, daemon=True).start()
            while True:
                message = await queue.get()
                await socket.send_json(message)
                if message["kind"] != "event":
                    break
    except WebSocketDisconnect:
        return


@app.get("/api/ledger/{dataset}")
def ledger(dataset: str) -> dict:
    return _engine(dataset).ledger_view()


@app.post("/api/ledger/{dataset}/tamper-drill")
def tamper_drill(dataset: str, seq: int = 0) -> dict:
    return _engine(dataset).tamper_drill(seq)


@app.get("/api/audit/{dataset}")
def audit(dataset: str) -> list[dict]:
    return _engine(dataset).service.audit_log[-50:][::-1]


@app.get("/api/evidence")
def evidence_view() -> dict:
    return evidence()


@app.get("/api/prereg")
def prereg() -> list[dict]:
    return prereg_documents()


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = _dist_file(path)
        return FileResponse(candidate or WEB_DIST / "index.html")


def _dist_file(path: str) -> Path | None:
    """A file inside web/dist, or None. Absolute, drive, UNC and '..' paths are rejected before any
    filesystem access, so the route can neither leave dist nor touch network shares."""
    if not path or "\\" in path or ":" in path or "\x00" in path:
        return None
    parts = PurePosixPath(path).parts
    if PurePosixPath(path).is_absolute() or any(part in ("", ".", "..") for part in parts):
        return None
    candidate = (WEB_DIST / Path(*parts)).resolve()
    return candidate if candidate.is_relative_to(WEB_DIST.resolve()) and candidate.is_file() else None
