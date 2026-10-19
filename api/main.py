"""FastAPI app: the UI contract over JSON, plus the built React bundle.

    GET  /api/snapshot            -> get_snapshot()
    POST /api/<method>            -> every other contract method (docs/UI_CONTRACT.md, C.1)

One process, one port. All actions go through the coordinator and therefore the permission
gatekeeper. Calls are serialised with a lock because the demo case is a single state machine.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import BASE_DIR
from security.role_access import require_bank_reviewer
from ui.backend import get_backend
from automation.api import router as automation_router

DIST_DIR = BASE_DIR / "ui" / "web" / "dist"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class PackBody(BaseModel):
    option_id: str


class SimulateBody(BaseModel):
    params: Dict[str, Any]


class IntelligenceBody(BaseModel):
    data: Dict[str, Any]


class CopilotBody(BaseModel):
    question: str
    inputs: Dict[str, Any] = {}


class ConceptBody(BaseModel):
    topic: str


class ContractReviewBody(BaseModel):
    text: str
    invoice_amount_usd: Optional[float] = None


class CapitalPlanBody(BaseModel):
    available_cash_usd: float
    minimum_reserve_usd: float
    working_capital_usd: float
    marketing_usd: float
    green_investment_usd: float


class GreenEconomicsBody(BaseModel):
    project_id: str
    electricity_price_usd_per_kwh: float
    annual_opex_usd: float = 0


class GreenReviewBody(BaseModel):
    project_id: str


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
    app.include_router(automation_router)
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

    @app.get('/api/analytics/summary', tags=['intelligence'])
    def analytics_summary() -> Dict[str, Any]:
        return call(lambda b: b.financial_analytics())

    @app.post('/api/analytics/scenario', tags=['intelligence'])
    def analytics_scenario(body: IntelligenceBody) -> Dict[str, Any]:
        return call(lambda b: b.financial_scenario(body.data), refusal_status=422)

    @app.post('/api/copilot/ask', tags=['agentic'])
    def copilot_ask(body: CopilotBody) -> Dict[str, Any]:
        return call(lambda b: b.copilot_decision(body.question, body.inputs), refusal_status=422)

    @app.post('/api/chat/explain-concept', tags=['conversation'])
    def explain_concept(body: ConceptBody) -> Dict[str, Any]:
        return call(lambda b: b.explain_public_concept(body.topic), refusal_status=422)

    @app.post('/api/projects/waterfall', tags=['intelligence'])
    def project_waterfall(body: IntelligenceBody) -> Dict[str, Any]:
        return call(lambda b: b.project_cashflow(body.data), refusal_status=422)

    @app.post('/api/projects/assess', tags=['intelligence'])
    def project_assess(body: IntelligenceBody) -> Dict[str, Any]:
        return call(lambda b: b.project_assessment(body.data), refusal_status=422)

    @app.post('/api/contracts/analyze', tags=['intelligence'])
    def contract_review(body: ContractReviewBody) -> Dict[str, Any]:
        return call(lambda b: b.analyze_contract({'text': body.text, 'invoice_amount_usd': body.invoice_amount_usd}), refusal_status=422)

    @app.post('/api/contracts/draft', tags=['intelligence'])
    def contract_draft(body: IntelligenceBody) -> Dict[str, Any]:
        return call(lambda b: b.draft_contract(body.data), refusal_status=422)

    @app.post('/api/contracts/draft-docx', tags=['intelligence'])
    def contract_docx(body: IntelligenceBody) -> Response:
        from contracts.docx_export import draft_docx_bytes
        raw = call(lambda b: draft_docx_bytes(body.data), refusal_status=422)
        return Response(content=raw,
                        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        headers={'Content-Disposition': 'attachment; filename="CashBridge_UNSIGNED_DRAFT.docx"',
                                 'Cache-Control':'no-store'})

    @app.post('/api/contracts/reconcile', tags=['intelligence'])
    def contract_reconcile(body: IntelligenceBody) -> Dict[str, Any]:
        return call(lambda b: b.reconcile_contract(body.data), refusal_status=422)

    @app.post('/api/contracts/extract-upload', tags=['intelligence'])
    async def contract_extract_upload(file: UploadFile = File(...)) -> Dict[str, Any]:
        from contracts.extraction import extract_upload, MAX_UPLOAD_BYTES
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        try:
            return extract_upload(file.filename or '', raw)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get('/api/bank/review', tags=['intelligence'])
    def bank_review(response: Response, _: None = Depends(require_bank_reviewer)) -> Dict[str, Any]:
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Vary'] = 'Authorization'
        return call(lambda b: b.bank_review())

    @app.post("/api/capital-plan")
    def capital_plan(body: CapitalPlanBody) -> Dict[str, Any]:
        from core.capital_planning import evaluate_allocation
        return call(lambda b: evaluate_allocation(body.model_dump() if hasattr(body, "model_dump") else body.dict()), refusal_status=422)

    @app.get("/api/green-finance")
    def green_finance() -> Dict[str, Any]:
        return call(lambda b: b.green_finance_view())

    @app.post('/api/green-finance/economics', tags=['intelligence'])
    def green_economics(body: GreenEconomicsBody) -> Dict[str, Any]:
        return call(lambda b: b.green_economics(body.project_id, body.electricity_price_usd_per_kwh,
                                                body.annual_opex_usd), refusal_status=422)

    @app.post("/api/green-finance/request-review")
    def green_review(body: GreenReviewBody) -> Dict[str, Any]:
        return call(lambda b: b.request_green_review(body.project_id), refusal_status=422)

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

    @app.get("/api/pack/pdf")
    def pack_pdf() -> FileResponse:
        path = call(lambda b: b.pack_pdf())
        if path is None or not Path(path).exists():
            raise HTTPException(status_code=404, detail="No pack has been prepared yet")
        return FileResponse(path, media_type="application/pdf", filename=Path(path).name)

    # ---- engine endpoints (Step 6.2): thin wrappers over the same coordinator methods, all gatekept
    def lookup(action: Callable[[Any], Any]) -> Any:
        try:
            return call(action)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/forecast", tags=["engine"])
    def forecast(
        dso_change_days: Optional[int] = None, deposit_pct: Optional[float] = None,
        tariff_shared_pct: Optional[float] = None, fx_change_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        given = {k: v for k, v in {"dso_change_days": dso_change_days, "deposit_pct": deposit_pct,
                                   "tariff_shared_pct": tariff_shared_pct, "fx_change_pct": fx_change_pct}.items() if v is not None}
        return call(lambda b: b.forecast_view(given), refusal_status=422)

    @app.get("/reconcile", tags=["engine"])
    def reconcile() -> Dict[str, Any]:
        return call(lambda b: b.reconciliation_view())

    @app.get("/funding-options", tags=["engine"])
    def funding_options() -> Any:
        return call(lambda b: b.funding_options())

    @app.post("/packs", tags=["engine"], status_code=201)
    def create_pack(body: PackBody) -> Dict[str, Any]:
        return call(lambda b: b.create_pack(body.option_id))

    @app.post("/packs/{pack_id}/request-approval", tags=["engine"])
    def request_pack_approval(pack_id: str) -> Dict[str, Any]:
        return lookup(lambda b: b.request_pack_approval(pack_id))

    @app.post("/packs/{pack_id}/approve", tags=["engine"])
    def approve_pack(pack_id: str, body: ApproveBody) -> JSONResponse:
        result = lookup(lambda b: b.approve_pack(pack_id, body.code))
        if result["ok"]:
            return JSONResponse(result)
        status = 409 if result["error"] == "DoubleFinancingBlocked" else 403
        return JSONResponse(result, status_code=status)

    @app.get("/audit/verify", tags=["engine"])
    def audit_verify() -> Dict[str, Any]:
        return call(lambda b: b.verify_chain())

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
