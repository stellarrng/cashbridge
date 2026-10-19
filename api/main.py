"""FastAPI app: two portals (SME and Bank) over one evidence trail, plus the static web UI.

Every route that touches case data needs a signed session and a permission (security/auth.py):

    public           /api/health, /api/auth/*, /api/public/overview (demo), /api/trust/scorecard
    sme:read         snapshot, analytics summary, green finance, pack PDF, engine GETs
    sme:analyze      what-ifs, contracts, CFO chat, read-only Autopilot plan
    sme:prepare      choose option, prepare pack, Autopilot execute     (Chief accountant)
    sme:approve      OTP approval, reject pack                          (Director)
    bank:read        inbox and submitted case                           (Lender reviewer)
    bank:decide      verify hashes, record the human credit decision    (Lender reviewer)

One process serves one SYNTHETIC demo case; calls are serialised with a lock. All actions go
through the coordinator and therefore the permission gatekeeper and the hash-chained audit log.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from automation.api import router as automation_router
from config import runtime_mode
from config.settings import BASE_DIR, EXECUTION_EVIDENCE_DIR
from security import auth
from security.auth import LENDER_TENANT, SME_TENANT, AuthError, Principal
from security.role_access import require_bank_reviewer
from ui.backend import get_backend

DIST_DIR = BASE_DIR / "ui" / "web" / "dist"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"]
SCORECARD_PATH = EXECUTION_EVIDENCE_DIR / "trust_scorecard.json"


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


class RejectBody(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class LoginBody(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    passcode: str = Field(min_length=1, max_length=200)
    portal: Optional[str] = Field(default=None, pattern="^(sme|bank)$")


class DemoLoginBody(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    portal: Optional[str] = Field(default=None, pattern="^(sme|bank)$")


class AutopilotBody(BaseModel):
    execute: bool = False
    goal: str = Field(default="Close the forecast cash gap safely", max_length=300)


class BankDecisionBody(BaseModel):
    decision: str = Field(pattern="^(APPROVE_FUNDING|REQUEST_INFO|DECLINE)$")
    note: str = Field(default="", max_length=500)


def _allowed_origins() -> list[str]:
    extra = [o.strip() for o in os.getenv("CASHBRIDGE_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return DEV_ORIGINS + extra


def _portal(permission: str, tenant: str) -> Callable[..., Principal]:
    """Permission check plus tenant scope: an SME user of another company or another lender gets 403."""
    base = auth.require(permission)

    def dependency(principal: Principal = Depends(base)) -> Principal:
        if principal.tenant_id != tenant:
            raise HTTPException(status_code=403, detail="This case belongs to a different organisation")
        return principal

    dependency.__name__ = f"portal_{permission.replace(':', '_')}"
    return dependency


def sme(permission: str) -> Callable[..., Principal]:
    return _portal(permission, SME_TENANT)


def bank(permission: str) -> Callable[..., Principal]:
    return _portal(permission, LENDER_TENANT)


def sme_any(*permissions: str) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(auth.current_principal)) -> Principal:
        if principal.tenant_id != SME_TENANT or not any(principal.can(p) for p in permissions):
            raise HTTPException(status_code=403, detail=f"{auth.ROLE_LABEL[principal.role]} is not allowed to do this")
        return principal

    return dependency


def demo_only() -> None:
    if runtime_mode.is_production():
        raise HTTPException(status_code=404, detail="Not available in production mode")


def create_app(backend_provider: Callable[[], Any] = get_backend, dist_dir: Path = DIST_DIR) -> FastAPI:
    """Build the app. ``backend_provider`` is injectable so tests can use a throw-away backend."""
    runtime_mode.assert_safe_to_start()
    app = FastAPI(title="CashBridge (SYNTHETIC demo)", version="2.0")
    app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins(), allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"], expose_headers=["Content-Disposition"])
    app.include_router(automation_router)
    lock = threading.Lock()

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api/") or request.url.path.startswith(("/forecast", "/reconcile", "/funding-options", "/packs", "/audit")):
            response.headers.setdefault("Cache-Control", "no-store")
        else:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self' " + " ".join(o for o in _allowed_origins() if o.startswith("https://")) + "; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    def call(action: Callable[[Any], Any], refusal_status: int = 409) -> Any:
        try:
            with lock:
                return action(backend_provider())
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error).strip("'\"")) from error
        except ValueError as error:
            raise HTTPException(status_code=refusal_status, detail=str(error)) from error

    def auth_call(action: Callable[[], Any]) -> Any:
        try:
            return action()
        except AuthError as error:
            raise HTTPException(status_code=error.status, detail=error.detail) from error

    # ------------------------------------------------------------------ public
    @app.get("/api/health", tags=["public"])
    def health() -> Dict[str, Any]:
        return {"ok": True, "mode": runtime_mode.mode(), "synthetic": True, "serverless": runtime_mode.is_serverless()}

    @app.get("/api/auth/config", tags=["auth"])
    def auth_config() -> Dict[str, Any]:
        sessions = auth.get_sessions()
        return {"mode": runtime_mode.mode(), "demo_accounts": sessions.demo_accounts(),
                "ephemeral_session_secret": sessions.ephemeral_secret,
                "otp_demo_secret": "JBSWY3DPEHPK3PXP" if not runtime_mode.is_production() else None}

    @app.post("/api/auth/login", tags=["auth"])
    def login(body: LoginBody, request: Request) -> Dict[str, Any]:
        return auth_call(lambda: auth.get_sessions().login(body.user_id, body.passcode, body.portal, auth.client_key(request)))

    @app.post("/api/auth/demo-login", tags=["auth"])
    def demo_login(body: DemoLoginBody) -> Dict[str, Any]:
        return auth_call(lambda: auth.get_sessions().demo_login(body.user_id, body.portal))

    @app.get("/api/auth/me", tags=["auth"])
    def me(principal: Principal = Depends(auth.current_principal)) -> Dict[str, Any]:
        return principal.public()

    @app.post("/api/auth/logout", tags=["auth"])
    def logout(principal: Principal = Depends(auth.current_principal)) -> Dict[str, Any]:
        auth.get_sessions().logout(principal)
        return {"ok": True}

    @app.get("/api/public/overview", tags=["public"])
    def public_overview(_: None = Depends(demo_only)) -> Dict[str, Any]:
        """Headline SYNTHETIC numbers for the landing page (demo mode only, no documents or names of people)."""
        def build(b: Any) -> Dict[str, Any]:
            snap = b.get_snapshot()
            options = [o for o in snap["funding_options"] if o["eligible"] and o["apr_pct"] is not None]
            from core.funding_coverage import coverage
            c = b.coord
            top = next((o for o in c.options if o.eligible and o.type in ("factoring", "loan") and o.apr_pct is not None), None)
            bridge = None
            if top is not None and c.forecast.first_shortfall_week:
                cov = coverage(c.forecast.weeks, option=top, funding_week=c.forecast.first_shortfall_week, buffer_usd=c.forecast.buffer_usd,
                               start_date=c.forecast_inputs.start_date, settle_on=c.nominee.due_date if c.nominee else None)
                bridge = {"name": top.name, "amount_usd": float(top.amount_usd), "apr_pct": top.apr_pct,
                          "funding_week": cov["funding_week"], "closing_after": [w["closing_after"] for w in cov["weeks"]],
                          "first_negative_week_after": cov["first_negative_week_after"], "residual_gap_usd": cov["residual_gap_usd"],
                          "trough_week": cov["trough_week"]}
            return {"synthetic": True, "company": snap["meta"]["company"], "kpis": snap["kpis"], "bridge": bridge,
                    "weeks": [{"week": w["week"], "closing": w["closing"], "status": w["status"]} for w in snap["forecast"]["weeks"]],
                    "options": [{"name": o["name"], "apr_pct": o["apr_pct"], "type": o["type"]} for o in options],
                    "eval": {"passed": snap["evidence"]["eval"]["passed"], "total": snap["evidence"]["eval"]["total"]}
                    if snap["evidence"]["eval"] else None}
        return call(build)

    @app.get("/api/trust/scorecard", tags=["public"])
    def trust_scorecard() -> Dict[str, Any]:
        if not SCORECARD_PATH.exists():
            raise HTTPException(status_code=404, detail="Run `make trust` to produce the scorecard")
        return json.loads(SCORECARD_PATH.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ SME: read
    @app.get("/api/snapshot")
    def snapshot(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.get_snapshot())

    @app.get('/api/analytics/summary', tags=['intelligence'])
    def analytics_summary(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.financial_analytics())

    @app.get("/api/green-finance")
    def green_finance(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.green_finance_view())

    @app.get("/api/pack/pdf")
    def pack_pdf(_: Principal = Depends(sme("sme:read"))) -> FileResponse:
        path = call(lambda b: b.pack_pdf())
        if path is None or not Path(path).exists():
            raise HTTPException(status_code=404, detail="No pack has been prepared yet")
        return FileResponse(path, media_type="application/pdf", filename=Path(path).name)

    # ------------------------------------------------------------------ SME: analyze
    @app.post('/api/analytics/scenario', tags=['intelligence'])
    def analytics_scenario(body: IntelligenceBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.financial_scenario(body.data), refusal_status=422)

    @app.post('/api/copilot/ask', tags=['agentic'])
    def copilot_ask(body: CopilotBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.copilot_decision(body.question, body.inputs), refusal_status=422)

    @app.post('/api/autopilot/run', tags=['agentic'])
    def autopilot_run(body: AutopilotBody, principal: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        if body.execute and not principal.can("sme:prepare"):
            raise HTTPException(status_code=403, detail="Only the preparer (Chief accountant) can let the Autopilot draft a pack; "
                                                        "the Director can run it in plan-only mode")
        return call(lambda b: b.run_autopilot(principal.user_id, body.execute, body.goal), refusal_status=409)

    @app.post('/api/chat/explain-concept', tags=['conversation'])
    def explain_concept(body: ConceptBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.explain_public_concept(body.topic), refusal_status=422)

    @app.post('/api/projects/waterfall', tags=['intelligence'])
    def project_waterfall(body: IntelligenceBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.project_cashflow(body.data), refusal_status=422)

    @app.post('/api/projects/assess', tags=['intelligence'])
    def project_assess(body: IntelligenceBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.project_assessment(body.data), refusal_status=422)

    @app.post('/api/contracts/analyze', tags=['intelligence'])
    def contract_review(body: ContractReviewBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.analyze_contract({'text': body.text, 'invoice_amount_usd': body.invoice_amount_usd}), refusal_status=422)

    @app.post('/api/contracts/draft', tags=['intelligence'])
    def contract_draft(body: IntelligenceBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.draft_contract(body.data), refusal_status=422)

    @app.post('/api/contracts/draft-docx', tags=['intelligence'])
    def contract_docx(body: IntelligenceBody, _: Principal = Depends(sme("sme:analyze"))) -> Response:
        from contracts.docx_export import draft_docx_bytes
        raw = call(lambda b: draft_docx_bytes(body.data), refusal_status=422)
        return Response(content=raw,
                        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        headers={'Content-Disposition': 'attachment; filename="CashBridge_UNSIGNED_DRAFT.docx"',
                                 'Cache-Control': 'no-store'})

    @app.post('/api/contracts/reconcile', tags=['intelligence'])
    def contract_reconcile(body: IntelligenceBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.reconcile_contract(body.data), refusal_status=422)

    @app.post('/api/contracts/extract-upload', tags=['intelligence'])
    async def contract_extract_upload(file: UploadFile = File(...), _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        from contracts.extraction import extract_upload, MAX_UPLOAD_BYTES
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        try:
            return extract_upload(file.filename or '', raw)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/capital-plan")
    def capital_plan(body: CapitalPlanBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        from core.capital_planning import evaluate_allocation
        return call(lambda b: evaluate_allocation(body.model_dump()), refusal_status=422)

    @app.post('/api/green-finance/economics', tags=['intelligence'])
    def green_economics(body: GreenEconomicsBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.green_economics(body.project_id, body.electricity_price_usd_per_kwh,
                                                body.annual_opex_usd), refusal_status=422)

    @app.post("/api/green-finance/request-review")
    def green_review(body: GreenReviewBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.request_green_review(body.project_id), refusal_status=422)

    @app.post("/api/simulate")
    def simulate(body: SimulateBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.simulate(body.params), refusal_status=422)

    @app.post("/api/ask_cfo")
    def ask_cfo(body: AskBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.ask_cfo(body.text))

    @app.post("/api/verify_chain")
    def verify_chain(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.verify_chain())

    # ------------------------------------------------------------------ SME: prepare (accountant)
    @app.post("/api/choose_option")
    def choose_option(body: ChooseBody, _: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        return call(lambda b: b.choose_option(body.option_id))

    @app.post("/api/prepare_pack")
    def prepare_pack(principal: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        return call(lambda b: b.prepare_pack(principal.user_id))

    @app.post("/api/reopen_pack")
    def reopen_pack(_: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        return call(lambda b: b.reopen_pack())

    @app.post("/api/request_otp")
    def request_otp(_: Principal = Depends(sme_any("sme:prepare", "sme:approve"))) -> Dict[str, Any]:
        return call(lambda b: b.request_otp())

    # ------------------------------------------------------------------ SME: approve (director)
    @app.post("/api/approve")
    def approve(body: ApproveBody, principal: Principal = Depends(sme("sme:approve"))) -> Dict[str, Any]:
        return call(lambda b: b.approve(body.code, approver=principal.user_id))

    @app.post("/api/reject_pack")
    def reject_pack(body: RejectBody, principal: Principal = Depends(sme("sme:approve"))) -> Dict[str, Any]:
        return call(lambda b: b.reject_pack(principal.name, body.reason))

    # ------------------------------------------------------------------ Bank portal
    @app.get("/api/bank/inbox", tags=["bank"])
    def bank_inbox(_: Principal = Depends(bank("bank:read"))) -> Dict[str, Any]:
        return call(lambda b: b.bank_inbox())

    @app.get("/api/bank/cases/{pack_id}", tags=["bank"])
    def bank_case(pack_id: str, response: Response, _: Principal = Depends(bank("bank:read"))) -> Dict[str, Any]:
        response.headers['Cache-Control'] = 'private, no-store'
        return call(lambda b: b.bank_case(pack_id))

    @app.get("/api/bank/cases/{pack_id}/pdf", tags=["bank"])
    def bank_pack_pdf(pack_id: str, _: Principal = Depends(bank("bank:read"))) -> FileResponse:
        path = call(lambda b: b.bank_pack_pdf(pack_id))
        return FileResponse(path, media_type="application/pdf", filename=Path(path).name)

    @app.post("/api/bank/cases/{pack_id}/verify", tags=["bank"])
    def bank_verify(pack_id: str, _: Principal = Depends(bank("bank:decide"))) -> Dict[str, Any]:
        return call(lambda b: b.bank_verify(pack_id))

    @app.post("/api/bank/cases/{pack_id}/decision", tags=["bank"])
    def bank_decision(pack_id: str, body: BankDecisionBody, principal: Principal = Depends(bank("bank:decide"))) -> Dict[str, Any]:
        return call(lambda b: b.bank_decision(pack_id, body.decision, body.note, principal.name), refusal_status=409)

    @app.get('/api/bank/review', tags=['intelligence'])
    def bank_review(response: Response, _: None = Depends(require_bank_reviewer)) -> Dict[str, Any]:
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Vary'] = 'Authorization'
        return call(lambda b: b.bank_review())

    # ---- engine endpoints: thin wrappers over the same coordinator methods, all gatekept
    @app.get("/forecast", tags=["engine"])
    def forecast(
        dso_change_days: Optional[int] = None, deposit_pct: Optional[float] = None,
        tariff_shared_pct: Optional[float] = None, fx_change_pct: Optional[float] = None,
        _: Principal = Depends(sme("sme:read")),
    ) -> Dict[str, Any]:
        given = {k: v for k, v in {"dso_change_days": dso_change_days, "deposit_pct": deposit_pct,
                                   "tariff_shared_pct": tariff_shared_pct, "fx_change_pct": fx_change_pct}.items() if v is not None}
        return call(lambda b: b.forecast_view(given), refusal_status=422)

    @app.get("/reconcile", tags=["engine"])
    def reconcile(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.reconciliation_view())

    @app.get("/funding-options", tags=["engine"])
    def funding_options(_: Principal = Depends(sme("sme:read"))) -> Any:
        return call(lambda b: b.funding_options())

    @app.post("/packs", tags=["engine"], status_code=201)
    def create_pack(body: PackBody, principal: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        return call(lambda b: b.create_pack(body.option_id, actor=principal.user_id))

    @app.post("/packs/{pack_id}/request-approval", tags=["engine"])
    def request_pack_approval(pack_id: str, _: Principal = Depends(sme_any("sme:prepare", "sme:approve"))) -> Dict[str, Any]:
        return call(lambda b: b.request_pack_approval(pack_id))

    @app.post("/packs/{pack_id}/approve", tags=["engine"])
    def approve_pack(pack_id: str, body: ApproveBody, principal: Principal = Depends(sme("sme:approve"))) -> JSONResponse:
        result = call(lambda b: b.approve_pack(pack_id, body.code, approver=principal.user_id))
        if result["ok"]:
            return JSONResponse(result)
        status = 409 if result["error"] in ("DoubleFinancingBlocked", "segregation_of_duties") else 403
        return JSONResponse(result, status_code=status)

    @app.get("/audit/verify", tags=["engine"])
    def audit_verify(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.verify_chain())

    # ---- demo-only demonstrations (404 in production mode)
    @app.post("/api/retry_double_financing")
    def retry_double_financing(_: None = Depends(demo_only), __: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        return call(lambda b: b.retry_double_financing())

    @app.post("/api/tamper_draft")
    def tamper_draft(_: None = Depends(demo_only), __: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.tamper_draft())

    @app.post("/api/tamper_demo")
    def tamper_demo(_: None = Depends(demo_only), __: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.tamper_demo())

    @app.post("/api/reset_demo")
    def reset_demo(_: None = Depends(demo_only), __: Principal = Depends(sme("demo:reset"))) -> Dict[str, Any]:
        return call(lambda b: b.reset_demo())

    # ------------------------------------------------------------------ static web UI
    if (dist_dir / "index.html").exists():
        if (dist_dir / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="unknown API route")
            root = dist_dir.resolve()
            candidate = (dist_dir / path).resolve()
            if path and candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            if path == "app" or path.startswith("app/"):
                app_page = dist_dir / "app.html"
                if app_page.exists():
                    return FileResponse(app_page)
            return FileResponse(dist_dir / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def root() -> JSONResponse:
            return JSONResponse({"app": "CashBridge (SYNTHETIC demo)", "ui": "not built: run `make ui`", "docs": "/docs"})

    return app


app = create_app()
