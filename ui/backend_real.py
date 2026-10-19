"""The UI contract implemented on the real engines (docs/UI_CONTRACT.md).

Every screen talks to the backend only through this class. It returns plain JSON-compatible
data built from the coordinator and the engines; it never lets a screen calculate a number.
Fields for features that are not built yet are null or empty, as the contract allows.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from agents.autopilot import FinanceAutopilot
from agents.cfo_assistant import CfoAssistant
from agents.concept_explainer import ConceptExplainer
from agents.decision_copilot import DecisionCopilot
from agents.coordinator import Coordinator
from agents.llm_client import LlmClient
from config.settings import EXECUTION_EVIDENCE_DIR, FX_NOTE, RUNTIME_DIR, SANDBOX_INPUTS_DIR, USD_VND
from core.forecasting_engine import compute_ccc
from core.pdf_compiler import bundle_sha256
from security.otp_verifier import action_hash as compute_action_hash
from core.green_finance import assess_green_project, green_project_economics
from core.financial_intelligence import financial_summary, budget_stress, project_feasibility
from contracts.intelligence import analyze as analyze_contract_text, draft as draft_contract_text, reconcile as reconcile_contract_text
from config.settings import Tier
from schemas.agent_schemas import Decision
from schemas.forecast_schemas import ForecastResult, ScenarioParams, to_contract
from security import number_check
from security.audit_log import verify_chain

SCENARIO_CONTROLS = {
    "dso_change_days": {"min": -30, "max": 30, "step": 5, "default": 0},
    "deposit_pct": {"min": 0, "max": 50, "step": 5, "default": 30},
    "tariff_shared_pct": {"min": 0, "max": 100, "step": 10, "default": 0},
    "fx_change_pct": {"min": -5, "max": 5, "step": 1, "default": 0},
}
PACK_KEYS = (
    "status", "pack_id", "locked_metrics", "letter_text", "number_check", "action_hash",
    "pdf_path", "lender_ref", "registry_block", "prepared_by", "approved_by",
)
BANK_DECISIONS = ("APPROVE_FUNDING", "REQUEST_INFO", "DECLINE")


class RealBackend:
    """Implements every method in the contract (C.1)."""

    def __init__(
        self,
        coordinator: Optional[Coordinator] = None,
        runtime_dir: Path = RUNTIME_DIR,
        clock: Optional[Callable[[], datetime]] = None,
        eval_path: Path = EXECUTION_EVIDENCE_DIR / "eval_results.json",
    ) -> None:
        self._eval_path = Path(eval_path)
        if coordinator is None:
            runtime = Path(runtime_dir)
            kwargs: Dict[str, Any] = {"llm": LlmClient()}  # offline unless LLM_API_KEY is set
            if clock is not None:
                kwargs["clock"] = clock
            coordinator = Coordinator(
                inputs_dir=SANDBOX_INPUTS_DIR,
                evidence_dir=runtime / "evidence",
                cases_dir=runtime / "cases",
                **kwargs,
            )
        self.coord = coordinator
        self._last_error: Optional[str] = None
        self._chat: List[Dict[str, Any]] = []
        self._green_reviews: Dict[str, str] = {}
        self._last_contract: Optional[Dict[str, Any]] = None
        self._last_autopilot: Optional[Dict[str, Any]] = None
        self._lender_review: Dict[str, Any] = self._empty_lender_review()
        self._start()

    # ------------------------------------------------------------------ setup
    def _start(self) -> None:
        """Every server start is a fresh demo session: the previous session's audit log and registry are cleared."""
        self.coord.reset()
        self.assistant = CfoAssistant(self.coord)
        self.decision_copilot = DecisionCopilot()
        self.concepts = ConceptExplainer()
        self._chat = [self._briefing()]
        self._last_contract = None
        self._last_autopilot = None
        self._lender_review = self._empty_lender_review()

    @staticmethod
    def _empty_lender_review() -> Dict[str, Any]:
        return {"status": "NOT_SUBMITTED", "decision": None, "note": None, "reviewer": None,
                "decided_at": None, "verification": None, "history": []}

    def _briefing(self) -> Dict[str, Any]:
        coord = self.coord
        forecast = coord.forecast
        if forecast.first_shortfall_week is None:
            return self._message("No cash shortfall is forecast in the next 13 weeks.", [])
        top = next((o for o in coord.options if o.eligible), None)
        locked: Dict[str, Any] = {"week": forecast.first_shortfall_week, "shortfall": forecast.shortfall_usd}
        text = f"Week {locked['week']} is expected to be short by USD {forecast.shortfall_usd:,.2f}."
        citations = [{"label": f"Forecast run {coord.forecast_run_id}", "source_id": f"forecast:{coord.forecast_run_id}"}]
        if top is not None:
            locked.update(amount=top.amount_usd, apr=top.apr_pct)
            text += f" Cheapest option: {top.name} for USD {top.amount_usd:,.2f} at about {top.apr_pct:.1f}% a year."
            citations.append({"label": "APR calculation", "source_id": f"funding:{top.id}"})
        if not number_check.check(text, locked).ok:  # cannot happen: every number comes from `locked`
            text = "The briefing was withheld because it failed the number check."
        return self._message(text, citations)

    def _message(self, text: str, citations: List[Dict[str, str]]) -> Dict[str, Any]:
        return {"role": "assistant", "text": text, "citations": citations, "mode": "local-explanation-no-llm"}

    def green_finance_view(self) -> Dict[str, Any]:
        """Synthetic pre-screening: no lender submission or taxonomy certification."""
        path = SANDBOX_INPUTS_DIR / "green_projects.json"
        projects = json.loads(path.read_text(encoding="utf-8"))
        results = []
        for project in projects:
            assessment = assess_green_project(project)
            assessment["review_status"] = self._green_reviews.get(assessment["project_id"], "NOT_REQUESTED")
            results.append(assessment)
        return {"synthetic": True, "projects": results,
                "notice": "Green eligibility and bank lending decisions require independent human verification."}

    def green_economics(self, project_id: str, electricity_price_usd_per_kwh: float, annual_opex_usd: float) -> Dict[str, Any]:
        projects = json.loads((SANDBOX_INPUTS_DIR / 'green_projects.json').read_text(encoding='utf-8'))
        project = next((p for p in projects if p['project_id'] == project_id), None)
        if project is None: raise ValueError('Unknown green project')
        result = green_project_economics(project, electricity_price_usd_per_kwh, annual_opex_usd)
        self._analytics_audit('green_project_economics', {'project_id':project_id,
                'electricity_price_usd_per_kwh':electricity_price_usd_per_kwh,'annual_opex_usd':annual_opex_usd}, result)
        return result

    def request_green_review(self, project_id: str) -> Dict[str, Any]:
        """Record a review request in this demo session; does not contact a bank."""
        if not any(p["project_id"] == project_id for p in self.green_finance_view()["projects"]):
            raise ValueError("Unknown green project")
        self._green_reviews[project_id] = "PENDING_HUMAN_REVIEW"
        return self.green_finance_view()

    # ------------------------------------------------------ Financial & contract intelligence
    def _analytics_audit(self, tool: str, input_data: Any, output_data: Any, tier: Tier = Tier.L1_ANALYZE) -> None:
        """Store hashes only; no document contents in the audit log."""
        self.coord.audit.append(case_id=self.coord.case.case_id, agent='intelligence', tool=tool,
                                tier=tier, decision=Decision.ALLOWED, reason='User-invoked offline demo tool; no external action',
                                input_payload=input_data, output_payload=output_data)

    def copilot_decision(self, question: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Audit a controlled multi-tool analytical chain; never allow a write tool."""
        options = self.funding_options()
        result = self.decision_copilot.run(question, inputs, funding_options=options)
        self._analytics_audit('copilot_decision_workflow',
                              {'question': question, 'input_sources': sorted(inputs),
                               'tools_executed': [x['tool'] for x in result['plan']]},
                              {'tools': [x['tool'] for x in result['plan']], 'decision': result['decision']})
        return result

    def explain_public_concept(self, topic: str) -> Dict[str, Any]:
        # Optional external model receives only allowlisted public topic titles,
        # no case/user question/contract/transaction data.
        result = self.concepts.explain(topic)
        self._analytics_audit('public_concept_explanation', {'topic': topic},
                              {'mode': result['mode']})
        return result

    def project_cashflow(self, values: Dict[str, Any]) -> Dict[str, Any]:
        from core.project_cashflow import project_cash_waterfall
        result = project_cash_waterfall(values)
        self._analytics_audit('project_cash_waterfall', {'source': 'user_entered_milestones'}, result)
        return result

    def financial_analytics(self) -> Dict[str, Any]:
        result = financial_summary()
        self._analytics_audit('financial_analytics', {'source': result['source_id']}, result)
        return result

    def financial_scenario(self, values: Dict[str, Any]) -> Dict[str, Any]:
        result = budget_stress(values)
        self._analytics_audit('budget_stress', values, result)
        return result

    def project_assessment(self, values: Dict[str, Any]) -> Dict[str, Any]:
        result = project_feasibility(values)
        self._analytics_audit('project_feasibility', values, result)
        return result

    def analyze_contract(self, values: Dict[str, Any]) -> Dict[str, Any]:
        result = analyze_contract_text(values.get('text', ''), values.get('invoice_amount_usd'))
        self._last_contract = result
        self._analytics_audit('contract_review', values, result)
        return result

    def draft_contract(self, values: Dict[str, Any]) -> Dict[str, Any]:
        result = draft_contract_text(values)
        self._analytics_audit('contract_draft_unsigned', values, result, Tier.L2_INTERNAL_WRITE)
        return result

    def reconcile_contract(self, values: Dict[str, Any]) -> Dict[str, Any]:
        result = reconcile_contract_text(values)
        self._analytics_audit('contract_invoice_compare', values, result)
        return result

    def bank_review(self) -> Dict[str, Any]:
        """Informational reviewer screen; never a credit scoring or authentication claim."""
        summary = financial_summary()
        snap = self.get_snapshot()
        result = {
            'synthetic': True, 'bank_access': 'SERVER_SIDE_BEARER_TOKEN_GATE_SYNTHETIC_DEMO',
            'case_id': snap['meta']['case_id'], 'case_state': snap['meta']['case_state'],
            'evidence': {'audit_chain_ok': snap['evidence']['chain_ok'],
                         'invoice_registry_blocks': len(snap['evidence']['registry_blocks']),
                         'verified_invoices': len([x for x in snap['verification'] if x.get('status') in {'VERIFIED','ELIGIBLE'}])
                         if isinstance(snap['verification'], list) else None,
                         'document_review': self._last_contract,
                         'source_id': summary['source_id']},
            'financial_ratios': summary['ratios'],
            'funding_options': snap['funding_options'],
            'green_projects': self.green_finance_view()['projects'],
            'review_checklist': ['Verify entity/KYC and signatory authority', 'Validate raw bank transactions and contract with counterparties',
                                 'Check exposure, collateral and any duplicate financing in external registers',
                                 'Validate model inputs and independently approve or decline credit'],
            'notice': 'READ-ONLY synthetic reviewer preview. Bank view requires a server-configured reviewer token; this is not production IAM, underwriting or a lending decision.'
        }
        return result

    # --------------------------------------------------------------- snapshot
    def get_snapshot(self) -> Dict[str, Any]:
        c = self.coord
        return {
            "meta": self._meta(),
            "kpis": self._kpis(c.forecast),
            "forecast": self._forecast_block(c.forecast),
            "scenario_controls": SCENARIO_CONTROLS,
            "reconciliation": {"rows": c.recon_rows, "featured_wire": self._featured_wire()},
            "verification": c.verification,
            "alerts": c.alerts,
            "funding_options": to_contract(c.options),
            "selected_option_id": c.selected_option_id,
            "pack": {key: self._pack_value(key) for key in PACK_KEYS},
            "tier_monitor": c.audit.tail(10),
            "pii_inspector": self._pii_inspector(),
            "chat": {"history": list(self._chat)},
            "collections": {
                "schedule": c.collection_schedule(),
                "promises": [
                    {"invoice_id": p.invoice_id, "buyer": p.buyer,
                     "promised_date": p.promised_date.isoformat(), "source_text": p.source_text}
                    for p in c.promises
                ],
            },
            "scans": c.scans,
            "buyer_risk": c.buyer_risk_rows(),
            "risk_model": c.risk.model.describe(),
            "evidence": self._evidence(),
            "autopilot": self._last_autopilot,
            "lender_review": self._lender_view(),
        }

    def _meta(self) -> Dict[str, Any]:
        c = self.coord
        return {
            "mode": "local-finance-engines",
            "synthetic": True,
            "company": c.profile["name"],
            "case_id": c.case.case_id,
            "case_state": c.state.value,
            "as_of": c.as_of.isoformat(),
            "fx_note": FX_NOTE,
            "last_error": self._last_error,
        }

    def _kpis(self, forecast: ForecastResult) -> Dict[str, Any]:
        c = self.coord
        ccc = compute_ccc(c.ledger)
        return {
            "cash_today_usd": float(c.cash_today),
            "cash_today_vnd": int(c.cash_today * USD_VND),
            "ccc": {"dio": ccc.dio, "dso": ccc.dso, "dpo": ccc.dpo, "ccc": ccc.ccc},
            "first_shortfall_week": forecast.first_shortfall_week,
            "shortfall_usd": float(forecast.shortfall_usd) if forecast.shortfall_usd is not None else None,
            "blocked_fraud_count": c.blocked_fraud_count,
        }

    @staticmethod
    def _forecast_block(forecast: ForecastResult) -> Dict[str, Any]:
        return {
            "buffer_usd": float(forecast.buffer_usd),
            "weeks": to_contract(forecast.weeks),
            "attribution": to_contract(forecast.attribution),
        }

    def _featured_wire(self) -> Optional[Dict[str, Any]]:
        row = next((r for r in self.coord.recon_rows if r["tier"] == 3 and r["status"] == "BOOKED"), None)
        if row is None:
            return None
        by_no = {i.invoice_no: i for i in self.coord.all_invoices}
        invoices = [{"id": no, "amount": float(by_no[no].amount.amount)} for no in sorted(row["matched_invoices"])]
        total = sum(by_no[no].amount.to_usd() for no in row["matched_invoices"])
        return {
            "txn_id": row["txn_id"],
            "received": row["amount"],
            "invoices": invoices,
            "invoice_total": float(total),
            "gap": row["gap"],
            "gap_reason": row["gap_reason"],
            "explanation": "Intermediary bank fee within USD 50 tolerance"
            if row["gap_reason"] == "bank_fee" else "Difference explained by FX conversion",
        }

    def _pack_value(self, key: str) -> Any:
        return self.coord.pack.get(key)

    def _lender_view(self) -> Dict[str, Any]:
        review = dict(self._lender_review)
        state = self.coord.state.value
        if state in ("SUBMITTED", "FUNDED", "REJECTED") and review["status"] == "NOT_SUBMITTED":
            review["status"] = "IN_REVIEW"
        return review

    def _pii_inspector(self) -> Dict[str, str]:
        inspector = self.coord.llm.pii_inspector()
        return {
            **inspector,
            'note': ('Local masking preview: nothing was sent to the LLM; this is not a transmission log. '
                     'The private SME documents and numbers are never sent to the optional public-topic explanation model.'),
        }

    def _evidence(self) -> Dict[str, Any]:
        c = self.coord
        ok, broken, checked = verify_chain(c.audit_path)
        return {
            "chain_ok": ok,
            "broken_seq": broken,
            "lines_checked": checked,
            "audit_tail": c.audit.tail(25),
            "registry_blocks": c.registry.blocks(),
            "eval": self._eval_results(),
        }

    def _eval_results(self) -> Optional[Dict[str, Any]]:
        """Results of the last `make eval`, in the contract shape, or None if it has not been run."""
        if not self._eval_path.exists():
            return None
        data = json.loads(self._eval_path.read_text(encoding="utf-8"))
        return {
            "passed": data["passed"],
            "total": data["total"],
            "baseline": data.get("baseline", "skipped"),
            "rows": [
                {"task": r["task"], "cashbridge_pass": r["cashbridge_pass"], "baseline_pass": r["baseline_pass"],
                 "invented_numbers": r["invented_numbers"], "category": r["category"], "answer": r["answer"]}
                for r in data["rows"]
            ],
        }

    # ---------------------------------------------------------------- actions
    def simulate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            scenario = ScenarioParams(**params)
        except (ValidationError, TypeError) as error:
            raise ValueError(f"invalid scenario: {error}") from error
        result = self.coord.simulate(scenario)
        return {
            "forecast": self._forecast_block(result.forecast),
            "kpis": self._kpis(result.forecast),
            "delta": to_contract(result.delta),
        }

    def ask_cfo(self, text: str) -> Dict[str, Any]:
        # Explicit offline tool routing; untrusted user text is not executed as code.
        q = text.lower()
        if any(term in q for term in ('contract risk', 'contract clause', 'contract review', 'contract fraud', 'hợp đồng')):
            if self._last_contract:
                flags = self._last_contract['flags']
                message = ('The most recently reviewed contract has ' + str(len(flags)) +
                           ' rule-based review flags: ' +
                           (', '.join(x['code'] for x in flags) if flags else 'none detected') +
                           '. Check the Contracts tab for evidence. This is not proof of fraud or legal advice.')
            else:
                message = 'Open Contracts, paste or upload a document, and click Review before asking about its clauses or risk.'
            reply = self._message(message, [{'label':'Session contract review','source_id':'contract:session'}])
        elif any(term in q for term in ('marketing budget', 'marketing spend', 'marketing increase', 'marketing allocation')):
            result = budget_stress({'marketing_increase_pct':25})
            reply = self._message('A sample 25% marketing budget increase would add USD '
                  +f"{result['additional_marketing_monthly_usd']:,.2f} per month. "
                  +'For a personalized scenario, change inputs in Financial Analytics; marketing ROI is not modeled.',
                  [{'label':'Budget engine synthetic ledger','source_id':result['source_id']}])
        elif any(term in q for term in ('dscr', 'quick ratio', 'interest coverage', 'debt to equity')):
            metrics = financial_summary()
            reply = self._message('Synthetic ledger: DSCR proxy '+str(metrics['ratios']['dscr_proxy'])+
                ', quick ratio '+str(metrics['ratios']['quick_ratio'])+
                ', interest coverage '+str(metrics['ratios']['interest_coverage'])+
                '. These are illustrative ratios, not lending approval.',
                [{'label':'Financial analytics input','source_id':metrics['source_id']}])
        else:
            reply = self.assistant.ask(text)
        self._chat += [{"role": "user", "text": text, "citations": [], "mode": reply["mode"]}, reply]
        return reply

    def choose_option(self, option_id: str) -> Dict[str, Any]:
        return self._try(lambda: self.coord.choose_option(option_id))

    def prepare_pack(self, actor: Optional[str] = None) -> Dict[str, Any]:
        def action() -> None:
            outcome = self.coord.prepare_pack(prepared_by=actor)
            if not outcome.get("ok"):
                raise ValueError(outcome.get("error", "the pack could not be prepared"))

        return self._try(action)

    def request_otp(self) -> Dict[str, Any]:
        return self.coord.request_approval()

    def approve(self, code: str, approver: Optional[str] = None) -> Dict[str, Any]:
        result = self.coord.approve(code, approver=approver)
        if result["ok"]:
            self._lender_review = {**self._empty_lender_review(), "status": "IN_REVIEW",
                                   "history": [{"event": "SUBMITTED", "by": approver, "lender_ref": result.get("lender_ref")}]}
        return {"ok": result["ok"], "error": result["error"], "snapshot": self.get_snapshot()}

    def reject_pack(self, by: str, reason: str) -> Dict[str, Any]:
        return self._try(lambda: self.coord.reject_pack(by, reason))

    def reopen_pack(self) -> Dict[str, Any]:
        return self._try(lambda: self.coord.reopen_after_rejection())

    # ------------------------------------------------------------------ autopilot
    def run_autopilot(self, actor: Optional[str], execute: bool, goal: str = "") -> Dict[str, Any]:
        """Governed agent pass. ``execute`` lets it draft the pack (preparer role only, checked by the API)."""
        result = FinanceAutopilot(self.coord).run(actor=actor, execute=execute, goal=goal or "Close the forecast cash gap safely")
        self._last_autopilot = result
        return result

    # ------------------------------------------------------------------ bank portal
    def _submitted_pack(self) -> Dict[str, Any]:
        if self.coord.state.value not in ("SUBMITTED", "FUNDED", "REJECTED"):
            raise LookupError("no submitted case")
        return self.coord.pack

    def bank_inbox(self) -> Dict[str, Any]:
        """Only packs the SME Director released with an OTP are visible to the lender (data minimisation)."""
        c = self.coord
        items = []
        if c.state.value in ("SUBMITTED", "FUNDED", "REJECTED"):
            option = c.selected_option()
            pack = c.pack
            items.append({
                "pack_id": pack["pack_id"], "company": c.profile["name"], "product": option.name if option else None,
                "amount_usd": float(option.amount_usd) if option and option.amount_usd is not None else None,
                "apr_pct": option.apr_pct if option else None, "invoice_no": c.nominee.invoice_no if c.nominee else None,
                "lender_ref": pack.get("lender_ref"), "case_state": c.state.value, "review": self._lender_view(),
                "submitted_by": pack.get("approved_by"), "prepared_by": pack.get("prepared_by"),
            })
        return {"synthetic": True, "lender": c.lender_name, "items": items,
                "notice": "Only packs released by the SME Director with a one-time code appear here. Pre-submission SME data is not shared."}

    def bank_case(self, pack_id: str) -> Dict[str, Any]:
        c = self.coord
        pack = self._submitted_pack()
        if pack.get("pack_id") != pack_id:
            raise LookupError(f"unknown pack '{pack_id}'")
        invoice = c.nominee
        verification = next((v for v in c.verification if v["invoice_id"] == invoice.invoice_no), None)
        buyer = next((b for b in c.buyer_risk_rows() if b["buyer_id"] == invoice.buyer_id), None)
        option = c.selected_option()
        summary = financial_summary()
        self.coord._gate("bank_reviewer", "read_documents", Tier.L0_READ, {"pack_id": pack_id})
        return {
            "synthetic": True, "pack_id": pack_id, "company": c.profile["name"], "lender": c.lender_name,
            "case_state": c.state.value, "lender_ref": pack.get("lender_ref"),
            "prepared_by": pack.get("prepared_by"), "approved_by": pack.get("approved_by"),
            "product": to_contract(option) if option else None,
            "locked_metrics": pack["locked_metrics"], "letter_text": pack["letter_text"],
            "document_hashes": pack.get("document_hashes"), "bundle_sha256": pack.get("bundle_sha256"),
            "action_hash": pack.get("action_hash"), "registry_block": pack.get("registry_block"),
            "invoice": {"invoice_no": invoice.invoice_no, "buyer": invoice.buyer_name, "amount_usd": float(invoice.amount.to_usd()),
                        "issue_date": invoice.issue_date.isoformat(), "due_date": invoice.due_date.isoformat(),
                        "three_way": verification, "scans": [s for s in c.scans if s["invoice_no"] == invoice.invoice_no]},
            "buyer_risk": buyer, "risk_model": c.risk.model.describe(),
            "forecast": self._forecast_block(c.forecast), "financial_ratios": summary["ratios"],
            "autopilot": ({k: self._last_autopilot[k] for k in ("run_id", "decision", "recommendation", "evidence", "evidence_counts", "steps")}
                          if self._last_autopilot else None),
            "review": self._lender_view(),
            "review_checklist": [
                "Verify SME entity, KYC and signatory authority",
                "Confirm the buyer and send a notice of assignment",
                "Check the invoice in an external / shared duplicate-financing register",
                "Recompute the hashes below against the documents received",
                "Make and record the human credit decision",
            ],
            "not_shared": ["Inbox and contacts", "Unrelated contracts and drafts", "Other invoices' scans", "Chat history"],
        }

    def bank_pack_pdf(self, pack_id: str) -> Path:
        pack = self._submitted_pack()
        path = self.coord.pack_pdf_file
        if pack.get("pack_id") != pack_id or path is None or not Path(path).exists():
            raise LookupError(f"unknown pack '{pack_id}'")
        return Path(path)

    def bank_verify(self, pack_id: str) -> Dict[str, Any]:
        """Independent recomputation of every hash the pack claims, plus the audit and registry chains."""
        c = self.coord
        pack = self._submitted_pack()
        if pack.get("pack_id") != pack_id:
            raise LookupError(f"unknown pack '{pack_id}'")
        locked = {m["key"]: m["value"] for m in pack["locked_metrics"]}
        recomputed_docs = c._document_hashes()
        recomputed_bundle = bundle_sha256(recomputed_docs, locked)
        payload = {"pack_id": pack["pack_id"], "invoice_no": c.nominee.invoice_no, "option_id": c.selected_option_id,
                   "bundle_sha256": recomputed_bundle, "amount_usd": str(c.selected_option().amount_usd)}
        audit_ok, broken, lines = verify_chain(c.audit_path)
        registry_ok, registry_broken = c.registry.verify_chain()
        block = pack.get("registry_block")
        checks = [
            {"check": "Source documents hash to the values in the pack", "ok": recomputed_docs == pack.get("document_hashes"),
             "detail": ", ".join(f"{k} {v[:12]}…" for k, v in recomputed_docs.items())},
            {"check": "Bundle SHA-256 recomputed from documents + locked metrics", "ok": recomputed_bundle == pack.get("bundle_sha256"),
             "detail": recomputed_bundle},
            {"check": "Director's OTP was bound to this exact action", "ok": compute_action_hash("submit_pack", payload) == pack.get("action_hash"),
             "detail": pack.get("action_hash")},
            {"check": "Preparer and approver are different people", "ok": bool(pack.get("approved_by")) and pack.get("approved_by") != pack.get("prepared_by"),
             "detail": f"prepared by {pack.get('prepared_by') or 'unknown'}, approved by {pack.get('approved_by') or 'unknown'}"},
            {"check": "Audit log hash chain intact", "ok": audit_ok, "detail": f"{lines} lines checked" + (f", broken at {broken}" if broken else "")},
            {"check": "Invoice registry chain intact (this installation)", "ok": registry_ok,
             "detail": f"block {block['block_index']}" if block else "no block (loan products are not registered)"},
            {"check": "Not financed at another lender", "ok": None,
             "detail": "Cannot be proven by the SME's own registry; check a shared register"},
        ]
        result = {"pack_id": pack_id, "checks": checks, "all_verifiable_ok": all(x["ok"] for x in checks if x["ok"] is not None)}
        self._lender_review["verification"] = result
        self._lender_review["history"].append({"event": "VERIFIED" if result["all_verifiable_ok"] else "VERIFICATION_FAILED"})
        return result

    def bank_decision(self, pack_id: str, decision: str, note: str, reviewer: str) -> Dict[str, Any]:
        pack = self._submitted_pack()
        if pack.get("pack_id") != pack_id:
            raise LookupError(f"unknown pack '{pack_id}'")
        if self._lender_review.get("verification") is None:
            raise ValueError("run the evidence verification before recording a decision")
        self.coord.record_bank_decision(decision, reviewer, note)
        status = {"APPROVE_FUNDING": "FUNDED_MOCK", "REQUEST_INFO": "INFO_REQUESTED", "DECLINE": "DECLINED"}[decision]
        self._lender_review.update(status=status, decision=decision, note=note or None, reviewer=reviewer,
                                   decided_at=self.coord._clock().isoformat())
        self._lender_review["history"].append({"event": decision, "by": reviewer, "note": note or None})
        return self.bank_case(pack_id)

    # ----------------------------------------------- engine endpoints (api/main.py, Step 6.2)
    def forecast_view(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """The 13-week forecast, optionally under what-if controls."""
        if params:
            return self.simulate({**{k: c["default"] for k, c in SCENARIO_CONTROLS.items()}, **params})
        return {"forecast": self._forecast_block(self.coord.forecast), "kpis": self._kpis(self.coord.forecast)}

    def reconciliation_view(self) -> Dict[str, Any]:
        return {"rows": self.coord.recon_rows, "featured_wire": self._featured_wire()}

    def funding_options(self) -> List[Dict[str, Any]]:
        return to_contract(self.coord.options)

    def create_pack(self, option_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        """Choose an option and draft its pack. A refusal is raised as ValueError."""
        self.coord.choose_option(option_id)
        outcome = self.coord.prepare_pack(prepared_by=actor)
        if not outcome.get("ok"):
            raise ValueError(outcome.get("error", "the pack could not be prepared"))
        return {k: self.coord.pack.get(k) for k in PACK_KEYS}

    def _require_pack(self, pack_id: str) -> None:
        if self.coord.pack.get("pack_id") != pack_id:
            raise LookupError(f"unknown pack '{pack_id}'")

    def request_pack_approval(self, pack_id: str) -> Dict[str, Any]:
        self._require_pack(pack_id)
        return self.coord.request_approval()

    def approve_pack(self, pack_id: str, code: str, approver: Optional[str] = None) -> Dict[str, Any]:
        self._require_pack(pack_id)
        result = self.coord.approve(code, approver=approver)
        if result["ok"]:
            self._lender_review = {**self._empty_lender_review(), "status": "IN_REVIEW",
                                   "history": [{"event": "SUBMITTED", "by": approver, "lender_ref": result.get("lender_ref")}]}
        return {**result, "pack": {k: self.coord.pack.get(k) for k in PACK_KEYS}}

    def pack_pdf(self) -> Optional[Path]:
        """Path of the current pack's PDF, or None (served by the API as /api/pack/pdf)."""
        return self.coord.pack_pdf_file

    def retry_double_financing(self) -> Dict[str, Any]:
        return self.coord.retry_double_financing()

    def tamper_draft(self) -> Dict[str, Any]:
        return self.coord.tamper_draft()

    def verify_chain(self) -> Dict[str, Any]:
        ok, broken, checked = verify_chain(self.coord.audit_path)
        return {"ok": ok, "broken_seq": broken, "lines_checked": checked}

    def tamper_demo(self) -> Dict[str, Any]:
        """Edit one line in a temporary copy of the audit log and verify it. The real log is untouched."""
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "audit_copy.jsonl"
            shutil.copyfile(self.coord.audit_path, copy)
            rows = copy.read_text(encoding="utf-8").splitlines()
            target = len(rows) // 2
            edited = json.loads(rows[target])
            edited["decision"] = "ALLOWED" if edited["decision"] != "ALLOWED" else "BLOCKED"
            rows[target] = json.dumps(edited, sort_keys=True, ensure_ascii=False)
            copy.write_text("\n".join(rows) + "\n", encoding="utf-8")
            ok, broken, checked = verify_chain(copy)
        return {"ok": ok, "broken_seq": broken, "lines_checked": checked, "note": "temporary copy only"}

    def reset_demo(self) -> Dict[str, Any]:
        self._green_reviews.clear()
        self._last_contract = None
        self._last_error = None
        self._last_autopilot = None
        self._lender_review = self._empty_lender_review()
        self.coord.reset()
        self._chat = [self._briefing()]
        return self.get_snapshot()

    # --------------------------------------------------------------- internals
    def _try(self, action: Callable[[], None]) -> Dict[str, Any]:
        """Run a state-changing action. A refusal is reported in ``meta.last_error``, not raised."""
        self._last_error = None
        try:
            action()
        except ValueError as error:
            self._last_error = str(error)
        return self.get_snapshot()


_backend: Optional[RealBackend] = None


def get_backend() -> RealBackend:
    """Process-wide backend (one demo case per server)."""
    global _backend
    if _backend is None:
        _backend = RealBackend()
    return _backend
