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
from typing import Any, Callable, Dict, Literal, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
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

# The web UI served at "/" and "/app": the built React app (frontend/dist, committed so a fresh clone runs without Node).
# Set CASHBRIDGE_UI_DIR to serve another build.
DIST_DIR = (BASE_DIR / os.environ["CASHBRIDGE_UI_DIR"]).resolve() if os.environ.get("CASHBRIDGE_UI_DIR") else BASE_DIR / "frontend" / "dist"
MAX_BODY_BYTES = 6_000_000  # largest legitimate request: a 5 MB contract upload plus form overhead
MESSAGE_KINDS_BY_PORTAL = {"sme": ("question", "response"), "bank": ("question", "evidence_request")}
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


class GreenCashImpactBody(BaseModel):
    project_id: str = Field(min_length=3, max_length=60)
    capex_week: int = Field(default=3, ge=1, le=13)
    financed_pct: float = Field(default=80, ge=0, le=100)
    tenor_months: int = Field(default=36, ge=6, le=120)
    electricity_price_usd_per_kwh: float = Field(default=0.12, ge=0, le=10)
    annual_opex_usd: float = Field(default=1500, ge=0, le=1e9)


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


class WithdrawBody(BaseModel):
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


class IntelligencePlanBody(BaseModel):
    goal: Literal["keep_cash_positive", "keep_above_buffer"] = "keep_cash_positive"
    min_probability: Optional[float] = Field(default=None, description="One of 0.8, 0.85, 0.9, 0.95")
    objective: Literal["cheapest", "risk_adjusted", "robust"] = Field(
        default="risk_adjusted", description="risk_adjusted = expected cost + 0.02 x CVaR95 (default); robust = worst case over the ambiguity set")


class EventBody(BaseModel):
    kind: Literal["buyer_delay", "order_cancelled", "deposit_up", "early_payment"]


class AlertDecisionBody(BaseModel):
    accept: bool


class ModelDecisionBody(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=300)


class BankDecisionBody(BaseModel):
    decision: str = Field(pattern="^(APPROVE_FUNDING|REQUEST_INFO|DECLINE)$")
    note: str = Field(default="", max_length=500)


class QualityCheckBody(BaseModel):
    sources: list[dict] = Field(default_factory=list, max_length=50)
    ledger_entries: list[dict] = Field(default_factory=list, max_length=200)
    bank_entries: list[dict] = Field(default_factory=list, max_length=200)


class PlanningChangeBody(BaseModel):
    field: Literal['marketing_usd', 'working_capital_usd', 'green_investment_usd']
    proposed_value: str
    reason: str = Field(min_length=8, max_length=500)


class AppealRequestBody(BaseModel):
    reason: str = Field(min_length=12, max_length=500)
    evidence_ref: str = Field(min_length=3, max_length=150)


class WorkspaceReviewBody(BaseModel):
    approve: bool
    note: str = Field(min_length=3, max_length=500)


class CollaborationMessageBody(BaseModel):
    kind: Literal['question', 'evidence_request', 'response']
    message: str = Field(min_length=4, max_length=1000)


class CorrectionBody(BaseModel):
    metric_key: str = Field(min_length=2, max_length=60)
    source_ref: str = Field(min_length=2, max_length=200)
    proposed_value: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=8, max_length=500)


class CorrectionDecisionBody(BaseModel):
    approve: bool
    note: str = Field(min_length=3, max_length=500)


class EvidenceOpenBody(BaseModel):
    item: str = Field(min_length=3, max_length=120)
    detail: str = Field(min_length=4, max_length=1000)
    due_days: int = Field(default=7, ge=1, le=60)


class EvidenceSubmitBody(BaseModel):
    evidence_ref: str = Field(min_length=3, max_length=150)
    sha256: str = Field(min_length=64, max_length=64, pattern="^[0-9a-fA-F]{64}$")
    note: str = Field(default="", max_length=500)


class EvidenceReviewBody(BaseModel):
    accept: bool
    reason: str = Field(min_length=3, max_length=500)
    version: Optional[int] = Field(default=None, ge=1)
    received_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64, pattern="^[0-9a-fA-F]{64}$")


class EvidenceRevokeBody(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class WorkspaceScenarioBody(BaseModel):
    available_cash_usd: float = Field(ge=0, le=1e9)
    minimum_reserve_usd: float = Field(ge=0, le=1e9)


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
    production = runtime_mode.is_production()
    # Interactive API docs are a demo convenience; production does not publish its route map.
    app = FastAPI(title="CashBridge (SYNTHETIC demo)", version="2.0", docs_url=None if production else "/docs",
                  redoc_url=None if production else "/redoc", openapi_url=None if production else "/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins(), allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"], expose_headers=["Content-Disposition"])
    app.include_router(automation_router)
    lock = threading.Lock()

    from fastapi.exception_handlers import http_exception_handler
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def record_denials(request: Request, exc: StarletteHTTPException):
        """Every refused API call (401 / 403) is written to the hash-chained audit log, with who tried what."""
        if exc.status_code in (401, 403) and request.url.path.startswith(("/api/", "/packs", "/forecast", "/audit")):
            who = "anonymous"
            token = auth.bearer(request.headers.get("authorization"))
            if token:
                try:
                    p = auth.get_sessions().verify(token)
                    who = f"{p.user_id} ({p.role}, {p.tenant_id})"
                except Exception:  # forged, expired or signed-out token
                    who = "invalid token"
            try:
                with lock:
                    b = backend_provider()
                    from config.settings import Tier
                    from schemas.agent_schemas import Decision
                    b.coord.audit.append(case_id=b.coord.case.case_id, agent="api_gateway",
                                         tool=f"denied {request.method} {request.url.path}"[:80], tier=Tier.L0_READ,
                                         decision=Decision.BLOCKED, reason=f"HTTP {exc.status_code}: {exc.detail} [{who}]"[:300],
                                         input_payload={"path": request.url.path, "method": request.method, "who": who},
                                         output_payload={"status": exc.status_code})
            except Exception:  # logging must never turn a refusal into a 500
                pass
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        """Last line of defence: a JSON 500 with an incident id, no stack trace, and an audit-chain entry."""
        import secrets as _secrets
        incident = "INC-" + _secrets.token_hex(4).upper()
        try:
            with lock:
                b = backend_provider()
                from config.settings import Tier
                from schemas.agent_schemas import Decision
                b.coord.audit.append(case_id=b.coord.case.case_id, agent="api_gateway", tool=f"error {request.url.path}"[:80],
                                     tier=Tier.L0_READ, decision=Decision.BLOCKED, reason=f"Unhandled {type(exc).__name__} ({incident})",
                                     input_payload={"path": request.url.path, "method": request.method})
        except Exception:
            pass
        return JSONResponse({"detail": f"Unexpected server error. Reference {incident}. Check the case state before retrying.",
                             "incident": incident}, status_code=500)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH") and "json" in request.headers.get("content-type", ""):
            raw = await request.body()
            if raw and (b"NaN" in raw or b"Infinity" in raw or b"e" in raw or b"E" in raw):
                def no_constant(token: str):
                    raise OverflowError(token)

                def finite(text: str) -> float:
                    value = float(text)
                    if value != value or value in (float("inf"), float("-inf")):
                        raise OverflowError(text)
                    return value
                try:
                    json.loads(raw, parse_constant=no_constant, parse_float=finite)
                except OverflowError:
                    return JSONResponse({"detail": "Numbers must be finite: NaN and Infinity are not accepted"}, status_code=422)
                except ValueError:
                    pass  # malformed JSON: FastAPI answers 422 itself
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                too_big = int(declared) > MAX_BODY_BYTES
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if too_big:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        response = await call_next(request)
        if runtime_mode.is_production() or request.url.scheme == "https" or \
                request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
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
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=503, detail="A required data source is unavailable or unreadable; nothing was changed") from error
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

    @app.post("/api/auth/logout-all", tags=["auth"])
    def logout_all(principal: Principal = Depends(auth.current_principal)) -> Dict[str, Any]:
        """Sign this user out on every device and every worker that shares the session store."""
        sessions = auth.get_sessions()
        sessions.logout_everywhere(principal)
        return {"ok": True, "shared_across_processes": sessions.state.shared}

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
                from agents.coordinator import nominee_receipts
                cov = coverage(c.forecast.weeks, option=top, funding_week=c.forecast.first_shortfall_week, buffer_usd=c.forecast.buffer_usd,
                               start_date=c.forecast_inputs.start_date, settle_on=c.nominee.due_date if c.nominee else None,
                               schedule=c.schedules.get(top.id), invoice_receipts=nominee_receipts(c))
                bridge = {"name": top.name, "amount_usd": float(top.amount_usd), "apr_pct": top.apr_pct,
                          "funding_week": cov["funding_week"], "closing_after": [w["closing_after"] for w in cov["weeks"]],
                          "first_negative_week_after": cov["first_negative_week_after"], "residual_gap_usd": cov["residual_gap_usd"],
                          "trough_week": cov["trough_week"]}
            return {"synthetic": True, "company": snap["meta"]["company"], "kpis": snap["kpis"], "bridge": bridge,
                    "robustness": b.public_robustness() if bridge else None,
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

    @app.get('/api/analytics/distress-signal', tags=['intelligence'])
    def distress_signal(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        """Externally validated screening hint (not a credit decision); see reports/external_distress_validation.md."""
        return call(lambda b: b.distress_signal())

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
        if body.execute:
            enforce_verified_data_gate("autopilot_execute", principal.user_id)
        return call(lambda b: b.run_autopilot(principal.user_id, body.execute, body.goal), refusal_status=409)

    @app.get('/api/settings/policy', tags=['auth'])
    def settings_policy(principal: Principal = Depends(auth.current_principal)) -> Dict[str, Any]:
        """Organisation policy as the server enforces it. Read-only: it is changed by deployment, not by a browser."""
        from agents import intelligence_core as ic
        from config.settings import CONCENTRATION_ALERT_PCT, MIN_CASH_BUFFER_USD, OTP_VALIDITY_SECONDS
        return {
            "mode": "production" if runtime_mode.is_production() else "demo",
            "you": {"user_id": principal.user_id, "role": principal.role, "tenant": principal.tenant_id,
                    "permissions": sorted(principal.permissions)},
            "cash": {"buffer_usd": float(MIN_CASH_BUFFER_USD), "concentration_alert_pct": float(CONCENTRATION_ALERT_PCT)},
            "approvals": {"otp_validity_seconds": OTP_VALIDITY_SECONDS, "session_hours": auth.SESSION_TTL_SECONDS // 3600,
                          "segregation_of_duties": "The person who prepares a funding pack cannot approve it",
                          "lender_decision": "Recorded by a named credit reviewer"},
            "planner": {"goals": {k: {"label": v["label"], "min_probability": v["min_probability"]} for k, v in ic.GOALS.items()},
                        "allowed_probabilities": list(ic.ALLOWED_PROBABILITIES), "max_packs_per_plan": ic.POLICY["max_packs_per_plan"],
                        "over_borrowing_factor": ic.POLICY["over_borrowing_factor"],
                        "min_p_on_time_to_pledge": ic.POLICY["min_p_on_time_to_pledge"],
                        "min_days_to_due_after_draw": ic.POLICY["min_days_to_due_after_draw"],
                        "objective": ic.DEFAULT_OBJECTIVE, "cvar_weight": ic.CVAR_WEIGHT},
            "alerts": ic.ALERT_POLICY,
            "change_process": "Set on the server and audited; a browser cannot change these values.",
        }

    # ------------------------------------------------------------ intelligence core
    @app.get('/api/intelligence', tags=['agentic'])
    def intelligence_status(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.intelligence_status())

    @app.post('/api/intelligence/plan', tags=['agentic'])
    def intelligence_plan(body: IntelligencePlanBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.intelligence(body.goal, body.min_probability, body.objective), refusal_status=422)

    @app.post('/api/intelligence/simulate-outcome', tags=['agentic'])
    def intelligence_outcome(_: None = Depends(demo_only), principal: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.intelligence_simulate_outcome(principal.user_id))

    @app.post('/api/intelligence/events', tags=['agentic'])
    def intelligence_event(body: EventBody, _: None = Depends(demo_only), principal: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.intelligence_event(body.kind, principal.user_id))

    @app.post('/api/intelligence/events/reset', tags=['agentic'])
    def intelligence_events_reset(_: None = Depends(demo_only), __: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.intelligence_reset_events())

    @app.post('/api/intelligence/inbox/{alert_id}', tags=['agentic'])
    def intelligence_alert(alert_id: str, body: AlertDecisionBody, principal: Principal = Depends(sme("sme:approve"))) -> Dict[str, Any]:
        return call(lambda b: b.intelligence_decide_alert(alert_id, body.accept, principal.user_id))

    @app.post('/api/intelligence/propose-update', tags=['agentic'])
    def intelligence_propose(principal: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        return call(lambda b: b.intelligence_propose_update(principal.user_id))

    @app.post('/api/intelligence/decide-update', tags=['agentic'])
    def intelligence_decide(body: ModelDecisionBody, principal: Principal = Depends(sme("sme:approve"))) -> Dict[str, Any]:
        return call(lambda b: b.intelligence_decide_update(body.approve, principal.user_id, body.note))

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

    @app.post('/api/green-finance/cash-impact', tags=['intelligence'])
    def green_cash_impact(body: GreenCashImpactBody, _: Principal = Depends(sme("sme:analyze"))) -> Dict[str, Any]:
        return call(lambda b: b.green_cash_impact(body.project_id, body.capex_week, body.financed_pct, body.tenor_months,
                                                  body.electricity_price_usd_per_kwh, body.annual_opex_usd), refusal_status=422)

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
        enforce_verified_data_gate("prepare_pack", principal.user_id)
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
        enforce_verified_data_gate("approve_release", principal.user_id)
        return call(lambda b: b.approve(body.code, approver=principal.user_id))

    @app.post("/api/reject_pack")
    def reject_pack(body: RejectBody, principal: Principal = Depends(sme("sme:approve"))) -> Dict[str, Any]:
        return call(lambda b: b.reject_pack(principal.name, body.reason))

    @app.post("/api/withdraw_release")
    def withdraw_release(body: WithdrawBody, principal: Principal = Depends(sme("sme:approve"))) -> Dict[str, Any]:
        """Consent withdrawal: the Director who released the pack takes it back before the lender decides."""
        result = call(lambda b: b.withdraw_release(principal.user_id, body.reason))
        try:
            from workspace.store import EvidenceDesk
            desk = EvidenceDesk(os.environ.get('CASHBRIDGE_WORKSPACE_DB', str(runtime_mode.runtime_dir(BASE_DIR) / 'workspace.sqlite3')))
            with desk.db() as con:
                desk._notify(con, SME_TENANT, "bank", result["pack_id"], None,
                             "The SME withdrew this pack. Stop processing it and delete copies held outside CashBridge.")
        except Exception:  # the withdrawal itself is already recorded in the audit chain
            pass
        try:  # uploaded evidence of a withdrawn pack is deleted (the request rows keep only the SHA-256 as the record)
            result["evidence_files_deleted"] = evidence_vault().delete_case(SME_TENANT, result["pack_id"])
        except Exception as exc:  # never undo the withdrawal because a file could not be removed; report it instead
            result["evidence_files_deleted"] = f"failed: {type(exc).__name__}"
        return result

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
        if body.decision == "APPROVE_FUNDING":
            outstanding = evidence_desk().blocking(SME_TENANT, pack_id)
            if outstanding:
                raise HTTPException(status_code=409, detail="Resolve the open evidence requests first: " + ", ".join(outstanding))
            enforce_verified_data_gate("lender_approve_funding", principal.user_id)
        return call(lambda b: b.bank_decision(pack_id, body.decision, body.note, principal.name), refusal_status=409)

    @app.get('/api/bank/review', tags=['intelligence'])
    def bank_review(response: Response, _: None = Depends(require_bank_reviewer)) -> Dict[str, Any]:
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Vary'] = 'Authorization'
        return call(lambda b: b.bank_review())

    def enforce_verified_data_gate(action: str = "prepare_pack", actor: str = "-") -> None:
        """Fail-closed Data Reliability Gate (core/financing_gate.py) in front of every financing action.

        Always on in PRODUCTION; opt-in with CASHBRIDGE_REQUIRE_DATA_GATE=1 in DEMO. Verification of a
        source comes from server-held signed attestations, never from the manifest's own claims.
        A refusal is HTTP 409 and is written to the hash-chained audit log.
        """
        from core import financing_gate
        try:
            financing_gate.check(action)
        except financing_gate.GateBlocked as blocked:
            try:
                with lock:
                    b = backend_provider()
                    from config.settings import Tier
                    from schemas.agent_schemas import Decision
                    b.coord.audit.append(case_id=b.coord.case.case_id, agent="data_reliability_gate",
                                         tool=f"gate {action}"[:80], tier=Tier.L0_READ, decision=Decision.BLOCKED,
                                         reason=blocked.detail[:300], input_payload={"action": action, "who": actor},
                                         output_payload={"status": 409})
            except Exception:  # logging must never turn a refusal into a 500
                pass
            raise HTTPException(status_code=409, detail=blocked.detail) from blocked

    @app.get('/api/workspace/data-gate', tags=['data-quality'])
    def data_gate_status(_: Principal = Depends(sme('sme:read'))) -> Dict[str, Any]:
        """What the server-side gate would decide right now (read-only, no manifest contents)."""
        from core import financing_gate
        state = financing_gate.evaluate()
        state["applies_to"] = list(financing_gate.FINANCING_ACTIONS)
        return state

    # ---------------------------------------- Auditable SME planning and released-case conversation
    # New services only create sandbox planning assumptions and reviewable correspondence.
    # They never mutate bank statements, accounting postings or lender credit decisions.
    def workspace_store():
        from workspace.store import WorkspaceStore
        return WorkspaceStore(os.environ.get('CASHBRIDGE_WORKSPACE_DB',
                              str(runtime_mode.runtime_dir(BASE_DIR) / 'workspace.sqlite3')))

    def workspace_case_id():
        return call(lambda b: b.get_snapshot()['meta']['case_id'])

    @app.post('/api/workspace/quality', tags=['data-quality'])
    def quality_check(body: QualityCheckBody, _: Principal = Depends(sme('sme:analyze'))) -> Dict[str, Any]:
        from core.data_reliability import assess
        try:
            return assess(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get('/api/workspace/requests', tags=['workspace'])
    def workspace_requests(principal: Principal = Depends(sme('sme:read'))) -> Dict[str, Any]:
        store=workspace_store()
        return {'requests': store.list_requests(principal.tenant_id, workspace_case_id()),
                'approved_scenario_assumptions': store.assumptions(principal.tenant_id),
                'note': 'Approved assumptions affect the sandbox capital-allocation scenario only; not the ledger or lending decision.'}

    @app.post('/api/workspace/requests', tags=['workspace'])
    def workspace_proposal(body: PlanningChangeBody, principal: Principal = Depends(sme('sme:prepare'))) -> Dict[str, Any]:
        try:
            return workspace_store().propose(principal.tenant_id,workspace_case_id(),principal.user_id,
                                            body.field,body.proposed_value,body.reason)
        except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc

    @app.post('/api/workspace/appeals', tags=['workspace'])
    def workspace_appeal(body: AppealRequestBody, principal: Principal = Depends(sme_any('sme:prepare','sme:approve'))) -> Dict[str, Any]:
        try:
            return workspace_store().appeal(principal.tenant_id,workspace_case_id(),principal.user_id,
                                            body.reason,body.evidence_ref)
        except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc

    @app.post('/api/workspace/requests/{request_id}/review', tags=['workspace'])
    def workspace_review(request_id: str, body: WorkspaceReviewBody,
                         principal: Principal = Depends(sme('sme:approve'))) -> Dict[str, Any]:
        try:
            return workspace_store().review(principal.tenant_id,request_id,principal.user_id,body.approve,body.note)
        except ValueError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc

    @app.post('/api/workspace/scenario', tags=['workspace'])
    def workspace_scenario(body: WorkspaceScenarioBody, principal: Principal = Depends(sme('sme:analyze'))) -> Dict[str, Any]:
        from core.capital_planning import evaluate_allocation
        values={name: v['value'] for name,v in workspace_store().assumptions(principal.tenant_id).items()}
        inputs={'available_cash_usd':body.available_cash_usd,'minimum_reserve_usd':body.minimum_reserve_usd,
                'working_capital_usd':values.get('working_capital_usd',0),
                'marketing_usd':values.get('marketing_usd',0),
                'green_investment_usd':values.get('green_investment_usd',0)}
        try:
            result=evaluate_allocation(inputs)
        except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
        result['assumptions_from']='approved_sandbox_assumptions_only'
        result['credit_decision_performed']=False
        return result

    def released_case(pack_id: str):
        """No correspondence before the Director's OTP release; never trust a browser-supplied pack_id alone.
        (Checks the released pack directly instead of calling bank_case(), which would log a lender document read.)"""
        def check(b: Any) -> Dict[str, Any]:
            pack = b._submitted_pack()
            if pack.get("pack_id") != pack_id:
                raise LookupError(f"unknown pack '{pack_id}'")
            return pack
        return call(check)

    @app.get('/api/workspace/cases/{pack_id}/messages', tags=['workspace'])
    def case_messages(pack_id: str, principal: Principal = Depends(auth.current_principal)) -> Dict[str, Any]:
        if not (principal.tenant_id==SME_TENANT and principal.can('sme:read') or
                principal.tenant_id==LENDER_TENANT and principal.can('bank:read')):
            raise HTTPException(status_code=403,detail='Case not shared with your organisation')
        released_case(pack_id)
        return {'pack_id':pack_id, 'items':workspace_store().list_messages(SME_TENANT,pack_id),
                'delivery':'local_sandbox_only', 'external_message_sent':False}

    @app.post('/api/workspace/cases/{pack_id}/messages', tags=['workspace'])
    def case_message(pack_id: str, body: CollaborationMessageBody,
                     principal: Principal = Depends(auth.current_principal)) -> Dict[str, Any]:
        if not (principal.tenant_id==SME_TENANT and principal.can('sme:prepare') or
                principal.tenant_id==LENDER_TENANT and principal.can('bank:decide')):
            raise HTTPException(status_code=403,detail='Not allowed to send a case message')
        if body.kind not in MESSAGE_KINDS_BY_PORTAL[principal.portal]:
            raise HTTPException(status_code=403, detail=f"{auth.ROLE_LABEL[principal.role]} cannot send a '{body.kind}' message")
        released_case(pack_id)
        try:
            return workspace_store().post_message(SME_TENANT,pack_id,principal.user_id,principal.role,
                                                  body.kind,body.message)
        except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc

    # ---------------------------------------- lender evidence requests on a released case (v8)
    def evidence_desk():
        from workspace.store import EvidenceDesk
        return EvidenceDesk(os.environ.get('CASHBRIDGE_WORKSPACE_DB',
                            str(runtime_mode.runtime_dir(BASE_DIR) / 'workspace.sqlite3')))

    def audit_evidence(principal: Principal, action: str, pack_id: str, request_id: str, extra: Optional[dict] = None) -> None:
        """Every evidence transition also lands in the hash-chained case audit log."""
        def write(b: Any) -> None:
            from config.settings import Tier
            from schemas.agent_schemas import Decision
            b.coord.audit.append(case_id=b.coord.case.case_id, agent="evidence_desk", tool=f"evidence {action}"[:80],
                                 tier=Tier.L2_INTERNAL_WRITE, decision=Decision.ALLOWED,
                                 reason=f"{principal.user_id} ({principal.role}) {action} {request_id}"[:300],
                                 input_payload={"pack_id": pack_id, "request_id": request_id, **(extra or {})})
        call(write)

    def evidence_call(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def shared_reader(principal: Principal) -> None:
        if not (principal.tenant_id == SME_TENANT and principal.can('sme:read') or
                principal.tenant_id == LENDER_TENANT and principal.can('bank:read')):
            raise HTTPException(status_code=403, detail='Case not shared with your organisation')

    @app.get('/api/workspace/cases/{pack_id}/evidence', tags=['workspace'])
    def evidence_list(pack_id: str, principal: Principal = Depends(auth.current_principal)) -> Dict[str, Any]:
        shared_reader(principal)
        released_case(pack_id)
        return {"pack_id": pack_id, **evidence_desk().list(SME_TENANT, pack_id), "external_message_sent": False}

    @app.post('/api/workspace/cases/{pack_id}/evidence', tags=['workspace'])
    def evidence_open(pack_id: str, body: EvidenceOpenBody, principal: Principal = Depends(bank("bank:decide"))) -> Dict[str, Any]:
        released_case(pack_id)
        item = evidence_call(lambda: evidence_desk().open(SME_TENANT, pack_id, principal.user_id, body.item, body.detail, body.due_days))
        audit_evidence(principal, "opened", pack_id, item["id"], {"item": body.item})
        return item

    @app.post('/api/workspace/cases/{pack_id}/evidence/{request_id}/submit', tags=['workspace'])
    def evidence_submit(pack_id: str, request_id: str, body: EvidenceSubmitBody,
                        principal: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        released_case(pack_id)
        item = evidence_call(lambda: evidence_desk().submit(SME_TENANT, pack_id, request_id, principal.user_id,
                                                              body.evidence_ref, body.sha256, body.note))
        audit_evidence(principal, "submitted", pack_id, request_id, {"sha256": body.sha256.lower(), "version": item["version"]})
        return item

    @app.post('/api/workspace/cases/{pack_id}/evidence/{request_id}/review', tags=['workspace'])
    def evidence_review(pack_id: str, request_id: str, body: EvidenceReviewBody,
                        principal: Principal = Depends(bank("bank:decide"))) -> Dict[str, Any]:
        released_case(pack_id)
        item = evidence_call(lambda: evidence_desk().review(SME_TENANT, pack_id, request_id, principal.user_id,
                                                              body.accept, body.reason, body.version, body.received_sha256))
        audit_evidence(principal, "accepted" if body.accept else "rejected", pack_id, request_id, {"version": item["version"]})
        return item

    @app.post('/api/workspace/cases/{pack_id}/evidence/{request_id}/revoke', tags=['workspace'])
    def evidence_revoke(pack_id: str, request_id: str, body: EvidenceRevokeBody,
                        principal: Principal = Depends(bank("bank:decide"))) -> Dict[str, Any]:
        released_case(pack_id)
        item = evidence_call(lambda: evidence_desk().revoke(SME_TENANT, pack_id, request_id, principal.user_id, body.reason))
        audit_evidence(principal, "revoked", pack_id, request_id)
        return item

    def evidence_vault():
        from workspace.evidence_vault import EvidenceVault, vault_key
        runtime = runtime_mode.runtime_dir(BASE_DIR)
        return EvidenceVault(runtime / "vault", vault_key(runtime))

    @app.post('/api/workspace/cases/{pack_id}/evidence/{request_id}/upload', tags=['workspace'])
    async def evidence_upload(pack_id: str, request_id: str, file: UploadFile = File(...), note: str = Form(""), ref: str = Form(""),
                              principal: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        """SME uploads the requested document; the server checks its type, hashes it, encrypts it and submits it."""
        from workspace.evidence_vault import MAX_BYTES, VaultError
        released_case(pack_id)
        evidence_call(lambda: evidence_desk().get(SME_TENANT, pack_id, request_id))  # 404 for a request of another case
        data = await file.read(MAX_BYTES + 1)
        try:
            meta = evidence_vault().store(SME_TENANT, pack_id, request_id, file.filename or "document", data, principal.user_id)
        except VaultError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        item = evidence_call(lambda: evidence_desk().submit(SME_TENANT, pack_id, request_id, principal.user_id, (ref.strip() or meta["filename"])[:150],
                                                              meta["sha256"], note[:500], file_id=meta["file_id"]))
        audit_evidence(principal, "uploaded", pack_id, request_id, {"sha256": meta["sha256"], "size": meta["size"], "mime": meta["mime"]})
        return {**item, "file": {k: meta[k] for k in ("file_id", "filename", "mime", "size", "sha256")}}

    @app.get('/api/workspace/cases/{pack_id}/evidence/{request_id}/file', tags=['workspace'])
    def evidence_file(pack_id: str, request_id: str, principal: Principal = Depends(auth.current_principal)) -> Response:
        """Open the uploaded document: SME of the case or the lender it was released to; integrity re-checked on every read."""
        from workspace.evidence_vault import VaultError
        shared_reader(principal)
        released_case(pack_id)
        row = evidence_call(lambda: evidence_desk().get(SME_TENANT, pack_id, request_id))
        if not row.get("evidence_file_id"):
            raise HTTPException(status_code=404, detail="No uploaded file for this request")
        try:
            meta, data = evidence_vault().read(SME_TENANT, pack_id, row["evidence_file_id"])
        except VaultError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        evidence_desk().record_view(SME_TENANT, pack_id, request_id, principal.user_id, principal.role)
        audit_evidence(principal, "opened", pack_id, request_id, {"sha256": meta["sha256"]})
        return Response(content=data, media_type=meta["mime"], headers={
            "Content-Disposition": f'attachment; filename="{meta["filename"]}"', "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff", "X-CashBridge-SHA256": meta["sha256"],
            "Content-Security-Policy": "default-src 'none'; sandbox"})

    def correction_desk():
        from workspace.corrections import CorrectionDesk
        return CorrectionDesk(os.environ.get('CASHBRIDGE_WORKSPACE_DB', str(runtime_mode.runtime_dir(BASE_DIR) / 'workspace.sqlite3')))

    def with_corrections(result: Dict[str, Any]) -> Dict[str, Any]:
        items = correction_desk().list(SME_TENANT, result["pack_id"])
        for m in result["metrics"]:
            m["corrections"] = [c for c in items if c["metric_key"] == m["key"]]
        result["corrections"] = items
        return result

    @app.get('/api/provenance', tags=['provenance'])
    def provenance(response: Response, _: Principal = Depends(sme('sme:read'))) -> Dict[str, Any]:
        """Lineage of the current pack's locked metrics: formula, inputs, source file/span/hash, review status, corrections."""
        response.headers['Cache-Control'] = 'private, no-store'
        return with_corrections(call(lambda b: b.provenance(), refusal_status=404))

    @app.get('/api/bank/cases/{pack_id}/provenance', tags=['bank'])
    def bank_provenance(pack_id: str, response: Response, _: Principal = Depends(bank('bank:read'))) -> Dict[str, Any]:
        response.headers['Cache-Control'] = 'private, no-store'
        return with_corrections(call(lambda b: b.provenance(pack_id, for_lender=True), refusal_status=404))

    @app.post('/api/provenance/corrections', tags=['provenance'])
    def propose_correction(body: CorrectionBody, principal: Principal = Depends(sme('sme:prepare'))) -> Dict[str, Any]:
        lin = call(lambda b: b.provenance(), refusal_status=404)
        metric = next((m for m in lin["metrics"] if m["key"] == body.metric_key), None)
        if metric is None:
            raise HTTPException(status_code=404, detail="Unknown metric")
        refs = {f"{s.get('doc_id') or s.get('file')}:{s.get('field') or s.get('json_path')}": s.get("value") for s in metric["sources"]}
        if body.source_ref not in refs:
            raise HTTPException(status_code=422, detail="source_ref must be one of this metric's sources")
        try:
            item = correction_desk().propose(SME_TENANT, lin["pack_id"], body.metric_key, body.source_ref, refs[body.source_ref],
                                             body.proposed_value, body.reason, principal.user_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        audit_evidence(principal, "correction proposed", lin["pack_id"], item["id"], {"metric": body.metric_key, "source": body.source_ref})
        return item

    @app.post('/api/provenance/corrections/{rid}/decision', tags=['provenance'])
    def decide_correction(rid: str, body: CorrectionDecisionBody, principal: Principal = Depends(sme('sme:approve'))) -> Dict[str, Any]:
        try:
            item = correction_desk().decide(SME_TENANT, rid, principal.user_id, body.approve, body.note)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        audit_evidence(principal, f"correction {item['status']}", item["pack_id"], rid)
        return item

    @app.get('/api/workspace/notifications', tags=['workspace'])
    def notifications(principal: Principal = Depends(auth.current_principal)) -> Dict[str, Any]:
        shared_reader(principal)
        return {"items": evidence_desk().notifications(SME_TENANT, principal.portal), "audience": principal.portal,
                "delivery": "in_app_only"}

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

    @app.get("/api/forecast/receipts-outlook", tags=["engine"])
    def receipts_outlook(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.receipts_outlook())

    @app.get("/api/lender/quotes", tags=["lender"])
    def lender_quotes(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        from api.lender_adapters import LenderResponseError, LenderUnavailable
        try:
            return call(lambda b: b.lender_quotes())
        except LenderUnavailable as exc:
            raise HTTPException(status_code=503, detail="Lender system unavailable; try again later") from exc
        except LenderResponseError as exc:
            raise HTTPException(status_code=502, detail=f"Lender answer refused: {exc}") from exc

    @app.post("/api/lender/webhook", tags=["lender"], include_in_schema=False)
    async def lender_webhook(request: Request) -> Dict[str, Any]:
        """Provider status callback: HMAC-signed, 5-minute replay window, processed once per event id. No session needed."""
        from api.lender_adapters import QuoteBook, default_book_path
        body = await request.body()
        if len(body) > 64_000:
            raise HTTPException(status_code=413, detail="too large")
        book = QuoteBook(default_book_path())
        try:
            return book.receive_webhook(os.environ.get("CASHBRIDGE_LENDER_WEBHOOK_SECRET", ""), body,
                                        request.headers.get("x-lender-signature", ""),
                                        os.environ.get("CASHBRIDGE_LENDER_PROVIDER_ID", "sandbox-lender"))
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/funding/schedules", tags=["engine"])
    def funding_schedules(_: Principal = Depends(sme("sme:read"))) -> Dict[str, Any]:
        return call(lambda b: b.funding_schedules())

    @app.get("/funding-options", tags=["engine"])
    def funding_options(_: Principal = Depends(sme("sme:read"))) -> Any:
        return call(lambda b: b.funding_options())

    @app.post("/packs", tags=["engine"], status_code=201)
    def create_pack(body: PackBody, principal: Principal = Depends(sme("sme:prepare"))) -> Dict[str, Any]:
        enforce_verified_data_gate("prepare_pack", principal.user_id)
        return call(lambda b: b.create_pack(body.option_id, actor=principal.user_id))

    @app.post("/packs/{pack_id}/request-approval", tags=["engine"])
    def request_pack_approval(pack_id: str, _: Principal = Depends(sme_any("sme:prepare", "sme:approve"))) -> Dict[str, Any]:
        return call(lambda b: b.request_pack_approval(pack_id))

    @app.post("/packs/{pack_id}/approve", tags=["engine"])
    def approve_pack(pack_id: str, body: ApproveBody, principal: Principal = Depends(sme("sme:approve"))) -> JSONResponse:
        enforce_verified_data_gate("approve_release", principal.user_id)
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
            return JSONResponse({"app": "CashBridge (SYNTHETIC demo)", "ui": "missing: frontend/dist is the built web app; run `make web-build` (or restore it from the repository)", "docs": "/docs"})

    return app


app = create_app()
