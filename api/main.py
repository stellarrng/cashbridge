"""FastAPI app: the UI contract over JSON, plus the built React bundle.

    GET  /api/snapshot            -> get_snapshot()
    POST /api/<method>            -> every other contract method (docs/UI_CONTRACT.md, C.1)

One process, one port. All actions go through the coordinator and therefore the permission
gatekeeper. Calls are serialised with a lock because the demo case is a single state machine.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import BASE_DIR
from ui.backend import get_backend

DIST_DIR = BASE_DIR / "ui" / "web" / "dist"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class SimulateBody(BaseModel):
    params: Dict[str, Any]


class AskBody(BaseModel):
    text: str


class ChooseBody(BaseModel):
    option_id: str


class ApproveBody(BaseModel):
    code: str


def create_app(backend_provider: Callable[[], Any] = get_backend, dist_dir: Path = DIST_DIR) -> FastAPI:
    """Build the app. ``backend_provider`` is injectable so tests can use a throw-away backend."""
    app = FastAPI(title="CashBridge (SYNTHETIC demo)", version="1.0")
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])
    lock = threading.Lock()

    def call(action: Callable[[Any], Any], refusal_status: int = 409) -> Any:
        try:
            with lock:
                return action(backend_provider())
        except ValueError as error:
            raise HTTPException(status_code=refusal_status, detail=str(error)) from error

    @app.get("/api/snapshot")
    def snapshot() -> Dict[str, Any]:
        return call(lambda b: b.get_snapshot())

    @app.post("/api/simulate")
    def simulate(body: SimulateBody) -> Dict[str, Any]:
        return call(lambda b: b.simulate(body.params), refusal_status=422)

    @app.post("/api/ask_cfo")
    def ask_cfo(body: AskBody) -> Dict[str, Any]:
        return call(lambda b: b.ask_cfo(body.text))

    @app.post("/api/choose_option")
    def choose_option(body: ChooseBody) -> Dict[str, Any]:
        return call(lambda b: b.choose_option(body.option_id))

    @app.post("/api/prepare_pack")
    def prepare_pack() -> Dict[str, Any]:
        return call(lambda b: b.prepare_pack())

    @app.post("/api/request_otp")
    def request_otp() -> Dict[str, Any]:
        return call(lambda b: b.request_otp())

    @app.post("/api/approve")
    def approve(body: ApproveBody) -> Dict[str, Any]:
        return call(lambda b: b.approve(body.code))

    @app.post("/api/retry_double_financing")
    def retry_double_financing() -> Dict[str, Any]:
        return call(lambda b: b.retry_double_financing())

    @app.post("/api/tamper_draft")
    def tamper_draft() -> Dict[str, Any]:
        return call(lambda b: b.tamper_draft())

    @app.post("/api/verify_chain")
    def verify_chain() -> Dict[str, Any]:
        return call(lambda b: b.verify_chain())

    @app.post("/api/tamper_demo")
    def tamper_demo() -> Dict[str, Any]:
        return call(lambda b: b.tamper_demo())

    @app.post("/api/reset_demo")
    def reset_demo() -> Dict[str, Any]:
        return call(lambda b: b.reset_demo())

    if (dist_dir / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="unknown API route")
            candidate = (dist_dir / path).resolve()
            if path and candidate.is_file() and dist_dir.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist_dir / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def root() -> JSONResponse:
            return JSONResponse({"app": "CashBridge (SYNTHETIC demo)", "ui": "not built: run `make ui`", "docs": "/docs"})

    return app


app = create_app()
