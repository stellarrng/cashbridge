"""The UI contract implemented on the real engines (docs/UI_CONTRACT.md).

Every screen talks to the backend only through this class. It returns plain JSON-compatible
data built from the coordinator and the engines; it never lets a screen calculate a number.
Fields for features that are not built yet are null or empty, as the contract allows.
"""

from __future__ import annotations

from datetime import date as date_cls
import numpy as np

import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from agents.autopilot import FinanceAutopilot
from agents import intelligence_core as ic
from core import scenario_simulator as sim

_SEED_CACHE: Dict[str, str] = {}  # simulated past quarters, keyed by inputs + world model
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
            from api.lender_adapters import adapter_from_env
            from data import loader as _loader
            kwargs["lender_submit"] = adapter_from_env(_loader.lender_catalog(SANDBOX_INPUTS_DIR)).submit  # mock unless configured
            coordinator = Coordinator(
                inputs_dir=SANDBOX_INPUTS_DIR,
                evidence_dir=runtime / "evidence",
                cases_dir=runtime / "cases",
                **kwargs,
            )
        self.coord = coordinator
        self.coord.archive_on_reset = True  # restarts and demo resets archive evidence instead of deleting it
        self._last_error: Optional[str] = None
        self._chat: List[Dict[str, Any]] = []
        self._green_reviews: Dict[str, str] = {}
        self._last_contract: Optional[Dict[str, Any]] = None
        self._last_autopilot: Optional[Dict[str, Any]] = None
        self._lender_review: Dict[str, Any] = self._empty_lender_review()
        self._intel_dir = Path(self.coord.audit_path).parent.parent / "intelligence"
        self._last_plan: Optional[Dict[str, Any]] = None
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
        self._reset_intelligence()

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

    def green_cash_impact(self, project_id: str, capex_week: int, financed_pct: float, tenor_months: int,
                          electricity_price_usd_per_kwh: float, annual_opex_usd: float) -> Dict[str, Any]:
        """Green investment on the live 13-week forecast; loan APR taken from the case's bridge-loan quote (MOCK)."""
        from core.green_finance import green_cash_impact
        projects = json.loads((SANDBOX_INPUTS_DIR / 'green_projects.json').read_text(encoding='utf-8'))
        project = next((p for p in projects if p['project_id'] == project_id), None)
        if project is None:
            raise ValueError('Unknown green project')
        loan = next((o for o in self.coord.options if o.type == "loan" and o.apr_pct is not None), None)
        apr = float(loan.apr_pct) if loan else 12.0
        f = self.coord.forecast
        result = green_cash_impact([float(w.closing) for w in f.weeks], float(f.buffer_usd), project, capex_week, financed_pct,
                                   apr, tenor_months, electricity_price_usd_per_kwh, annual_opex_usd)
        result["loan_apr_source"] = f"{loan.name} quote" if loan else "assumed 12% (no loan quote on file)"
        self._analytics_audit('green_cash_impact', {'project_id': project_id, 'capex_week': capex_week, 'financed_pct': financed_pct,
                                                    'tenor_months': tenor_months}, {k: result[k] for k in ('without_project', 'cash_funded', 'loan_funded')})
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
            "director_alerts_open": sum(1 for a in getattr(self, "_inbox", []) if a["status"] == "OPEN"),
            "model_update_pending": bool(ic.ModelRegistry(self._intel_dir / "model_registry.json").status()["pending"])
            if hasattr(self, "_intel_dir") else False,
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

    def withdraw_release(self, by: str, reason: str) -> Dict[str, Any]:
        pack_id = self.coord.pack.get("pack_id")
        self.coord.withdraw_release(by, reason)
        self._lender_review["history"].append({"event": "WITHDRAWN_BY_SME", "by": by, "note": reason})
        self._lender_review["status"] = "WITHDRAWN"
        return {"ok": True, "pack_id": pack_id, "snapshot": self.get_snapshot()}

    def reopen_pack(self) -> Dict[str, Any]:
        return self._try(lambda: self.coord.reopen_after_rejection())

    # ------------------------------------------------------------------ autopilot
    def run_autopilot(self, actor: Optional[str], execute: bool, goal: str = "") -> Dict[str, Any]:
        """Governed agent pass. ``execute`` lets it draft the pack (preparer role only, checked by the API)."""
        _, registry = self._intel()
        core = ic.IntelligenceCore(params=registry.active(), n_paths=1000)
        result = FinanceAutopilot(self.coord, core=core).run(actor=actor, execute=execute, goal=goal or "Close the forecast cash gap safely")
        self._last_autopilot = result
        return result

    # ------------------------------------------------------------- intelligence core
    def _reset_intelligence(self) -> None:
        """Each demo session starts from the prior world model and an empty (lazily seeded) memory."""
        if self._intel_dir.exists():
            shutil.rmtree(self._intel_dir, ignore_errors=True)
        self._last_plan = None
        self._twin_events: List[str] = []
        self._twin_plan: Optional[Dict[str, Any]] = None
        self._inbox: List[Dict[str, Any]] = []
        self._digest: List[Dict[str, Any]] = []

    def _intel(self):
        memory = ic.CaseMemory(self._intel_dir / "case_memory.jsonl")
        registry = ic.ModelRegistry(self._intel_dir / "model_registry.json")
        if not memory.records():
            # SIMULATED past quarters so memory and learning have something to show in the demo. The result depends
            # only on the inputs and the world model, so it is computed once per process and copied afterwards.
            inputs = ic.CoreInputs.from_coordinator(self.coord)
            key = hashlib.sha256((inputs.forecast_inputs.model_dump_json() + registry.active().version).encode()).hexdigest()
            if key not in _SEED_CACHE:
                ic.seed_memory(memory, inputs, ic.IntelligenceCore(registry.active(), n_paths=600), episodes=8, seed=7)
                _SEED_CACHE[key] = memory.path.read_text(encoding="utf-8")
            else:
                memory.path.write_text(_SEED_CACHE[key], encoding="utf-8")
        return memory, registry

    def intelligence(self, goal: str = "keep_cash_positive", min_probability: Optional[float] = None,
                     objective: str = ic.DEFAULT_OBJECTIVE) -> Dict[str, Any]:
        """Run the Core: state, ranked allowed plans, the chosen one, memory and the learning status."""
        memory, registry = self._intel()
        params = registry.active()
        self.coord._gate("intelligence_core", "plan_liquidity", Tier.L1_ANALYZE,
                         {"goal": goal, "min_probability": min_probability, "objective": objective, "world_model": params.version})
        inputs = self._twin_inputs()  # the live case plus any events that have happened since
        result = ic.IntelligenceCore(params=params).plan(inputs, goal, baseline_actions=ic.fixed_workflow_actions(inputs),
                                                        memory=memory, min_probability=min_probability, objective=objective,
                                                        incumbent=self._twin_plan["actions"] if self._twin_plan else None)
        core = ic.IntelligenceCore(params=params)
        stress = core.stress_test(inputs, result.chosen["actions"], goal)
        result.chosen["stress_test"] = stress
        run_id = f"RUN-{len([r for r in memory.records() if r['type'] == 'plan']) + 1:03d}"
        memory.remember_plan(run_id, result, source="LIVE")
        self._last_plan = dict(result.as_dict(), run_id=run_id)
        return {"plan": self._last_plan, "learning": self._learning_status(memory, registry), "benchmark": self._benchmark_summary(),
                "twin": self.twin_status()}

    def public_robustness(self) -> Optional[Dict[str, Any]]:
        """Headline for the landing page: how often the single pack and the Core plan keep cash at or above zero."""
        _, registry = self._intel()
        key = (self.coord.forecast_run_id, self.coord.state.value, registry.active().version)
        if getattr(self, "_robust_cache", (None,))[0] == key:
            return self._robust_cache[1]
        inputs = ic.CoreInputs.from_coordinator(self.coord)
        result = ic.IntelligenceCore(params=registry.active(), n_paths=1000).plan(inputs, baseline_actions=ic.fixed_workflow_actions(inputs))
        out = {"single_pack_p": result.baseline.get("p_goal"), "core_p": result.chosen["p_goal"], "core_plan": result.chosen["description"],
               "core_packs": result.chosen["packs"], "status": result.status, "paths": 1000, "world_model": registry.active().version}
        self._robust_cache = (key, out)
        return out

    # ------------------------------------------------------- events and executive inbox
    def _twin_inputs(self) -> "ic.CoreInputs":
        inputs = ic.CoreInputs.from_coordinator(self.coord)
        for kind in self._twin_events:
            inputs = ic.apply_event(inputs, kind)
        return inputs

    def _twin_core(self) -> "ic.IntelligenceCore":
        _, registry = self._intel()
        return ic.IntelligenceCore(params=registry.active(), n_paths=1000)

    def twin_status(self) -> Dict[str, Any]:
        return {"catalogue": [{"kind": k, **v} for k, v in ic.EVENTS.items()], "applied": list(self._twin_events),
                "plan_in_force": {k: self._twin_plan[k] for k in ("description", "p_goal", "cost_usd", "packs")} if self._twin_plan else None,
                "inbox": [{k: v for k, v in a.items() if k != "proposed_plan"}
                          for a in sorted(self._inbox, key=lambda a: (a["status"] != "OPEN", -a["priority"]["score"]))],
                "digest": self._digest[::-1], "policy": ic.ALERT_POLICY,
                "counts": {"events": len(self._inbox) + len(self._digest), "director_alerts": len(self._inbox), "digest_items": len(self._digest),
                           "open_alerts": sum(1 for a in self._inbox if a["status"] == "OPEN")},
                "note": "Demo events are buttons; in production they would arrive from the bank feed, ERP and inbox parser."}

    def intelligence_event(self, kind: str, actor: Optional[str]) -> Dict[str, Any]:
        """Apply a catalogue event to the twin, re-plan, and route the result to the Director or the digest."""
        if kind not in ic.EVENTS:
            raise ValueError(f"unknown event {kind!r}")
        if kind in self._twin_events:
            raise ValueError("This event has already happened in this session; reset the events to replay it")
        core = self._twin_core()
        before = self._twin_inputs()
        if self._twin_plan is None:
            self._twin_plan = core.plan(before).chosen
        after = ic.apply_event(before, kind)
        self.coord._gate("intelligence_core", "plan_liquidity", Tier.L1_ANALYZE, {"event": kind, "actor": actor})
        started = datetime.now()
        assessment = ic.assess_event(core, before, after, kind, self._twin_plan)
        assessment["latency_ms"] = int((datetime.now() - started).total_seconds() * 1000)
        chosen = assessment.pop("_chosen")
        self._twin_events.append(kind)
        self._last_plan = None  # the decision view re-plans on the new state
        item = dict(assessment, id=f"EVT-{len(self._inbox) + len(self._digest) + 1:03d}", recorded_by=actor)
        if assessment["route"] == "DIRECTOR_INBOX":
            item.update(status="OPEN", proposed_plan=chosen)
            self._inbox.append(item)
        else:
            item.update(status="HANDLED")
            self._twin_plan = chosen  # same shape (or kept); nothing for the Director to approve
            self._digest.append(item)
        return {"assessment": {k: v for k, v in item.items() if k != "proposed_plan"}, "twin": self.twin_status()}

    def intelligence_decide_alert(self, alert_id: str, accept: bool, reviewer: str) -> Dict[str, Any]:
        item = next((a for a in self._inbox if a["id"] == alert_id), None)
        if item is None:
            raise LookupError("alert not found")
        if item["status"] != "OPEN":
            raise ValueError("This alert has already been decided")
        self.coord._gate("model_owner", "record_plan_decision", Tier.L2_INTERNAL_WRITE,
                         {"alert": alert_id, "accept": accept}, human_approver=reviewer)
        if accept:
            self._twin_plan = item["proposed_plan"]
        self._last_plan = None
        item.update(status="ACCEPTED" if accept else "KEPT_CURRENT_PLAN", decided_by=reviewer)
        return self.twin_status()

    def intelligence_reset_events(self) -> Dict[str, Any]:
        self._twin_events, self._twin_plan, self._inbox, self._digest = [], None, [], []
        self._last_plan = None
        return self.twin_status()

    def intelligence_status(self) -> Dict[str, Any]:
        memory, registry = self._intel()
        return {"plan": self._last_plan, "learning": self._learning_status(memory, registry), "benchmark": self._benchmark_summary(),
                "twin": self.twin_status()}

    def _learning_status(self, memory: "ic.CaseMemory", registry: "ic.ModelRegistry") -> Dict[str, Any]:
        episodes = memory.episodes()
        return {"registry": registry.status(), "memory_chain_ok": memory.verify(), "episodes": len(episodes),
                "episodes_with_miss": sum(1 for e in episodes if not e["outcome"]["goal_met"]),
                "recent": [{"run_id": e["run_id"], "source": e["source"], "plan": e["description"], "predicted_p_goal": e["predicted"]["p_goal"],
                            "goal_met": e["outcome"]["goal_met"], "trough_usd": e["outcome"]["trough_usd"],
                            "cause": e["outcome"]["attribution"]["label"], "lesson": e["outcome"]["attribution"]["lesson"]}
                           for e in episodes[-10:]][::-1]}

    def intelligence_simulate_outcome(self, actor: Optional[str]) -> Dict[str, Any]:
        """Demo only: let one quarter 'happen' in the hidden test world for the last plan, then explain it."""
        if not self._last_plan:
            raise ValueError("Run the Intelligence Core first")
        memory, registry = self._intel()
        self.coord._gate("intelligence_core", "simulate_outcome", Tier.L1_ANALYZE, {"run_id": self._last_plan["run_id"]})
        inputs = ic.CoreInputs.from_coordinator(self.coord)
        seed = 900 + len(memory.records())
        realised = sim.realise(inputs.forecast_inputs, ic.HIDDEN_TEST_WORLD, seed=seed)
        outcome = ic.attribute_outcome(inputs, self._last_plan["chosen"]["actions"], realised)
        memory.remember_outcome(self._last_plan["run_id"], dict(outcome, items=ic.observed_items(realised),
                                                                truth_world=ic.HIDDEN_TEST_WORLD.label, recorded_by=actor))
        return {"run_id": self._last_plan["run_id"], "outcome": outcome, "learning": self._learning_status(memory, registry)}

    def intelligence_propose_update(self, actor: Optional[str]) -> Dict[str, Any]:
        """Fit a candidate world model on recorded outcomes and gate it offline. It is stored as pending only."""
        memory, registry = self._intel()
        observed = [e["outcome"]["items"] for e in memory.episodes()]
        current = registry.active()
        learner = ic.WorldModelLearner(current)
        metrics = learner.evaluate(observed, current)
        candidate = learner.fit(observed)
        self.coord._gate("intelligence_core", "propose_model_update", Tier.L2_INTERNAL_WRITE,
                         {"candidate": candidate.version, "accepted_offline": metrics["accepted"]})
        pending = registry.propose(candidate, metrics, proposed_by=actor or "intelligence_core")
        return {"pending": pending, "learning": self._learning_status(memory, registry)}

    def intelligence_decide_update(self, approve: bool, reviewer: str, note: str = "") -> Dict[str, Any]:
        memory, registry = self._intel()
        pending = registry.status()["pending"]
        if not pending:
            raise ValueError("No pending model update")
        if approve and reviewer == pending.get("proposed_by"):
            raise ValueError("Segregation of duties: the proposer cannot approve the model update")
        if approve and not pending["metrics"].get("accepted"):
            raise ValueError("The offline evaluation did not accept this candidate; it cannot be activated")
        self.coord._gate("model_owner", "activate_model_update", Tier.L2_INTERNAL_WRITE,
                         {"approve": approve, "note": note}, human_approver=reviewer)
        try:
            entry = registry.decide(approve, reviewer, note)
        except PermissionError as error:
            raise ValueError(str(error)) from error
        self._last_plan = None  # the next plan must use the active model
        return {"decision": entry, "learning": self._learning_status(memory, registry)}

    @staticmethod
    def _benchmark_summary() -> Optional[Dict[str, Any]]:
        path = EXECUTION_EVIDENCE_DIR / "planner_benchmark.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        ops_path = EXECUTION_EVIDENCE_DIR / "ops_benchmark.json"
        ops = json.loads(ops_path.read_text(encoding="utf-8"))["summary"] if ops_path.exists() else None
        return {"generated_at": data["generated_at"], "protocol": data["protocol"], "summary": data["summary"],
                "learning_gate": data["learning_gate"], "ceiling_within_cap": data.get("ceiling_within_cap"), "ops": ops}

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
            "funding_schedule": self.funding_schedules().get(c.selected_option_id),
            "buyer_behaviour_cross_check": self._behaviour_score(invoice),
            "buyer_risk_explanation": c.risk.explain(invoice.buyer_id, (invoice.due_date - invoice.issue_date).days, float(invoice.amount.to_usd())),
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
    def _behaviour_score(self, invoice) -> Optional[Dict[str, Any]]:
        try:
            from agents.buyer_behaviour import BehaviouralBuyerModel
            from data import loader
            model = BehaviouralBuyerModel(loader.read("payment_history.json", self.coord.inputs_dir)["records"])
            out = model.score(invoice.buyer_id, self.coord.as_of, float(invoice.amount.to_usd()))
            out["v8_p_on_time"] = round(self.coord.risk.p_on_time(invoice), 2)
            return out
        except Exception:  # a cross-check must never block the lender view
            return None

    def receipts_outlook(self) -> Dict[str, Any]:
        """v9 receipts timing (censoring-aware Kaplan-Meier, early payment included) next to the conservative base plan,
        with an 80% band calibrated by split conformal on the company's own rolling-origin errors."""
        from datetime import timedelta
        from core import conformal as cf
        from core.forecasting_engine import _invoice_views
        from core.payment_timing import PaymentTimingModel, observations_at
        from data import loader
        if getattr(self, "_outlook_cache", None) is not None:
            return self._outlook_cache
        c = self.coord
        inp = c.forecast_inputs
        hist = loader.read("payment_history.json", c.inputs_dir)["records"]
        rows = [(r["buyer_id"], date_cls.fromisoformat(r["due_date"]), date_cls.fromisoformat(r["paid_date"])) for r in hist]
        model = PaymentTimingModel(observations_at(inp.start_date - timedelta(days=1), (("ALL", d, p) for _, d, p in rows)),
                                   inp.start_date - timedelta(days=1))
        open_items = []
        for v in _invoice_views(inp):
            due = v.receivable.promised_date or v.receivable.due_date
            open_items.append(("ALL", due, float(v.final_usd)))
        expected, after = model.weekly_receipts(open_items, inp.start_date, 13)
        base = [float(w.inflows) for w in c.forecast.weeks]
        # conformal half-widths per horizon from the backtest on this company's own history (no look-ahead)
        from eval.forecast_backtest import backtest, load_cashbridge
        bt = getattr(self, "_bt", None) or backtest(load_cashbridge(), "own", warmup_weeks=16, mc=50)
        self._bt = bt
        errs = bt.get("_abs_errors_by_h") or []
        half = [cf.conformal_quantile(e, 0.2) if e else None for e in errs] if errs else [None] * 13
        outflows = [float(w.outflows) for w in c.forecast.weeks]
        close_v9, cash = [], float(inp.opening_cash_usd)
        for i in range(13):
            cash += expected[i] - outflows[i]
            close_v9.append(round(cash, 2))
        self._outlook_cache = {
            "weeks": list(range(1, 14)), "base_receipts": [round(x, 2) for x in base], "v9_expected_receipts": [round(float(x), 2) for x in expected],
            "v9_band_80": [[round(max(0.0, float(e) - h), 2), round(float(e) + h, 2)] if h is not None and np.isfinite(h) else None
                           for e, h in zip(expected, half)],
            "v9_closing_if_receipts_as_expected": close_v9, "after_horizon_usd": round(float(after), 2),
            "backtest": {k: v for k, v in bt["methods"].items()} if bt else None, "interval_coverage": bt.get("intervals") if bt else None,
            "external_backtest": "reports/forecast_backtest.md",
            "note": ("The base plan stays conservative (no early payments, late share four weeks late) because locked pack figures must "
                     "not rely on early payers. The v9 outlook is the expected timing from the payment history; its 80% band is "
                     "calibrated on realised errors (split conformal)."),
        }
        return self._outlook_cache

    def provenance(self, pack_id: Optional[str] = None, for_lender: bool = False) -> Dict[str, Any]:
        """Click-to-source lineage of every locked metric (core/provenance.py). Lenders see only the released pack."""
        from core.provenance import lineage
        c = self.coord
        pack = self._submitted_pack() if for_lender else c.pack
        if not pack.get("pack_id") or (pack_id is not None and pack.get("pack_id") != pack_id):
            raise LookupError(f"unknown pack '{pack_id}'")
        if for_lender:
            c._gate("bank_reviewer", "read_documents", Tier.L0_READ, {"pack_id": pack["pack_id"], "view": "provenance"})
        return lineage(c)

    def lender_quotes(self) -> Dict[str, Any]:
        """Quotes for the chosen (or best eligible) lender product through the configured adapter, kept in the quote book."""
        from decimal import Decimal as D
        from api.lender_adapters import QuoteBook, QuoteRequest, adapter_from_env, default_book_path
        c = self.coord
        option = c.selected_option() or next((o for o in c.options if o.eligible and o.type in ("factoring", "loan")), None)
        if option is None or c.nominee is None:
            return {"quotes": [], "adapter": None, "notice": "No lender product to quote yet."}
        adapter = adapter_from_env(c.catalog)
        book = QuoteBook(default_book_path())
        ref = c.pack.get("pack_id") or f"PRE-{c.nominee.invoice_no}"
        req = QuoteRequest(pack_id=ref, bundle_sha256=c.pack.get("bundle_sha256") or "", product=option.type, invoice_no=c.nominee.invoice_no,
                           invoice_usd=D(str(c.nominee.amount.to_usd())), requested_usd=D(str(option.amount_usd)),
                           days=int((option.assumptions or {}).get("days") or (c.nominee.due_date - c.as_of).days), drawdown_date=c.as_of)
        existing = [q for q in book.list(ref) if q["status"] == "OPEN"]
        if not existing:
            book.save(adapter.request_quote(req))
        return {"adapter": {"provider_id": adapter.provider_id, "environment": adapter.environment},
                "quotes": book.list(ref), "engine_unchanged": True,
                "notice": "Quotes are data with an expiry. A simulated quote comes from the MOCK catalogue and is not a lender offer."}

    def distress_signal(self) -> Dict[str, Any]:
        """Screening hint from DSO, DIO and gross margin, validated on public Polish company data (core/distress_signal.py)."""
        from core.distress_signal import score
        result = score(self.coord.ledger)
        if result is None:
            raise LookupError("distress model not built: run eval/external_distress_validation.py")
        return {**result, "synthetic_company": True}

    def funding_schedules(self) -> Dict[str, Any]:
        """Timeline, 13-week effect and settlement scenarios for every lender option (one shared schedule each)."""
        from agents.coordinator import nominee_receipts
        from core.funding_coverage import coverage
        c = self.coord
        receipts = nominee_receipts(c)
        out = {}
        for o in c.options:
            sc = c.schedules.get(o.id)
            if sc is None:
                continue
            cov = coverage(c.forecast.weeks, option=o, funding_week=1, buffer_usd=c.forecast.buffer_usd,
                           start_date=c.forecast_inputs.start_date, schedule=sc, invoice_receipts=receipts)
            out[o.id] = {"option": o.name, "schedule": sc.as_dict(), "scenarios": sc.scenarios(),
                         "expected_cost_usd": cov["expected_cost_usd"], "funding_week": cov["funding_week"],
                         "settlement_week": cov["settlement_week"], "residual_gap_usd": cov["residual_gap_usd"],
                         "assumptions": cov["assumptions"], "illustrative": True,
                         "label": "Computed from MOCK lender terms: an illustration, not a lender offer"}
        return out

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
        self._reset_intelligence()
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
