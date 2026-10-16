"""Coordinator: the plain-code state machine that owns every case file (no LLM).

It runs the Monday 07:00 flow

    NEW -> RECONCILED -> FORECASTED -> SHORTFALL_DETECTED -> OPTIONS_RANKED
        -> INVOICE_VERIFIED -> PACK_DRAFTED -> AWAITING_APPROVAL -> SUBMITTED

and is the only caller of ``submit_pack`` and ``send_email``, and only with a valid
ApprovalRecord bound to that exact action. Every tool call goes through the permission
gatekeeper, which writes one audit line. Email text is data: it can raise alerts but it
never changes the case state or picks an action.

Case-state rules used here
  * NEEDS_HUMAN: the pipeline cannot continue (nominated invoice fails verification,
    the cover letter fails the number lock). A single unmatched bank transaction does not
    stop the case; it is listed with status NEEDS_HUMAN for the accountant.
  * BLOCKED: the gatekeeper refused a tool call the pipeline itself made.
  * Guard hits on emails (BEC, injection) become alerts only.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from agents.llm_client import LlmClient
from config.settings import (
    CASES_DIR,
    EXECUTION_EVIDENCE_DIR,
    SANDBOX_INPUTS_DIR,
    Tier,
)
from core.forecasting_engine import compute_ccc, forecast_13w
from core.forecasting_engine import simulate as run_simulation
from core.funding_evaluator import FundingRequest, rank_options
from core.invoice_registry import DoubleFinancingBlocked, InvoiceRegistry
from core.matching_engine import reconcile, three_way_match
from core.metrics import monthly_billing_volatility_pct, negative_cash_weeks, top_buyer_share_pct
from core.period_lock import PeriodLocks
from data import loader
from schemas.agent_schemas import CaseFile, CaseState, Decision, GateDecision
from schemas.document_schemas import (
    BankTxn,
    BillOfLading,
    CommercialInvoice,
    Email,
    MatchStatus,
    PurchaseOrder,
    ReconciliationResult,
    ReconStatus,
)
from schemas.forecast_schemas import LedgerSnapshot, LiquidityOption, ScenarioParams, to_contract
from security import injection_guard, number_check
from security.audit_log import AuditLog, sha256_of
from security.bec_fraud_detector import BecVerdict, analyze, is_valid_vn_tax_id
from security.otp_verifier import Challenge, OtpVerifier, action_hash
from security.permission_gatekeeper import PermissionGatekeeper

CASE_ID = "case-0001"
Clock = Callable[[], datetime]


class GateBlocked(Exception):
    """The gatekeeper refused a tool call that the pipeline itself made."""

    def __init__(self, decision: GateDecision) -> None:
        super().__init__(f"{decision.tool} blocked: {decision.reason}")
        self.decision = decision


class LetterDraft(BaseModel):
    """Structured output for the cover letter."""

    text: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mock_lender_ref(payload: Dict[str, Any]) -> str:
    return "MOCK-" + sha256_of(payload)[:10].upper()


class Coordinator:
    """State machine for one demo case. Paths, clock and LLM client are injectable."""

    def __init__(
        self,
        inputs_dir: Path = SANDBOX_INPUTS_DIR,
        evidence_dir: Path = EXECUTION_EVIDENCE_DIR,
        cases_dir: Path = CASES_DIR,
        clock: Clock = _utc_now,
        llm: Optional[LlmClient] = None,
        lender_submit: Callable[[Dict[str, Any]], str] = _mock_lender_ref,
    ) -> None:
        self.inputs_dir = Path(inputs_dir)
        self.evidence_dir = Path(evidence_dir)
        self.cases_dir = Path(cases_dir)
        self._clock = clock
        self.llm = llm or LlmClient(api_key="")
        self._lender_submit = lender_submit
        self.audit_path = self.evidence_dir / "sandbox_operation_logs.jsonl"
        self.registry_path = self.evidence_dir / "invoice_registry.json"
        self._load_inputs()
        self._start_session()

    # ------------------------------------------------------------------ setup
    def _load_inputs(self) -> None:
        d = self.inputs_dir
        self.profile = loader.company(d)
        self.contacts = loader.contacts(d)
        self.catalog = loader.lender_catalog(d)
        self.lender_name = loader.read("lender_catalog.json", d).get("lender", "Partner Factor")
        self.all_invoices: List[CommercialInvoice] = loader.invoices(d)
        self.pos: Dict[str, PurchaseOrder] = {p.po_number: p for p in loader.purchase_orders(d)}
        self.bls: Dict[str, BillOfLading] = {b.invoice_no: b for b in loader.bills_of_lading(d)}
        self.txns: List[BankTxn] = loader.bank_txns(d)
        self.emails: List[Email] = loader.emails(d)
        self.billings = loader.billings(d)
        self.as_of = date.fromisoformat(self.profile["as_of"])
        self.cash_today = Decimal(self.profile["opening_cash_usd"])
        self.ledger = LedgerSnapshot(**self.profile["ledger"])

    def _start_session(self) -> None:
        """Fresh case and fresh security state. Evidence files are left alone."""
        self.audit = AuditLog(self.audit_path, clock=self._clock)
        self.gate = PermissionGatekeeper(self.audit, clock=self._clock)
        self.otp = OtpVerifier(clock=self._clock)
        self.registry = InvoiceRegistry(self.registry_path, clock=self._clock)
        self.locks = PeriodLocks()
        self.case = CaseFile(case_id=CASE_ID)
        self.paid: List[str] = []
        self.recon_rows: List[Dict[str, Any]] = []
        self.forecast = None
        self.forecast_inputs = None
        self.forecast_run_id: Optional[str] = None
        self.verification: List[Dict[str, Any]] = []
        self.nominee: Optional[CommercialInvoice] = None
        self.options: List[LiquidityOption] = []
        self.selected_option_id: Optional[str] = None
        self.alerts: List[Dict[str, Any]] = []
        self.blocked_fraud_count = 0
        self.pack: Dict[str, Any] = self._empty_pack()
        self._pack_payload: Optional[Dict[str, Any]] = None
        self._bundle_sha: Optional[str] = None
        self._challenge: Optional[Challenge] = None

    @staticmethod
    def _empty_pack() -> Dict[str, Any]:
        return {
            "status": "NOT_STARTED", "pack_id": None, "locked_metrics": [], "letter_text": None,
            "number_check": None, "action_hash": None, "pdf_path": None, "lender_ref": None,
            "registry_block": None,
        }

    @property
    def state(self) -> CaseState:
        return self.case.state

    # ------------------------------------------------------------------- gate
    def _gate(
        self,
        agent: str,
        tool: str,
        tier: Tier,
        payload: Optional[Dict[str, Any]] = None,
        approval=None,
        human_approver: Optional[str] = None,
    ) -> GateDecision:
        decision = self.gate.check(agent, tool, tier, CASE_ID, payload, approval, human_approver)
        if decision.decision is Decision.BLOCKED:
            raise GateBlocked(decision)
        return decision

    # --------------------------------------------------------------- triggers
    def weekly_run(self, auto_prepare: bool = False) -> CaseState:
        """The Monday 07:00 trigger. With ``auto_prepare`` it also drafts the pack for the top option."""
        self._start_session()
        try:
            self._read_sources()
            self._reconcile_all()
            self.case.move_to(CaseState.RECONCILED)
            self._forecast()
            if self.state is CaseState.SHORTFALL_DETECTED:
                self._verify_invoices()
                self._rank_options()
                self._confirm_nominee()
            self._process_inbox()
            if auto_prepare and self.state is CaseState.INVOICE_VERIFIED:
                self.choose_option(next(o.id for o in self.options if o.eligible))
                self.prepare_pack()
        except GateBlocked:
            self.case.move_to(CaseState.BLOCKED)
        self._save()
        return self.state

    def on_bank_txn(self, txn: BankTxn) -> ReconciliationResult:
        """A new bank credit arrives: reconcile it against the invoices still open."""
        self._gate("coordinator", "read_bank_statements", Tier.L0_READ, {"txn_id": txn.txn_id})
        result = self._reconcile_one(txn)
        self._save()
        return result

    def on_document(self, document: Any) -> None:
        """A new invoice, purchase order or bill of lading arrives and is added to the case inputs."""
        self._gate("coordinator", "read_documents", Tier.L0_READ, {"type": type(document).__name__})
        if isinstance(document, CommercialInvoice):
            self.all_invoices.append(document)
        elif isinstance(document, PurchaseOrder):
            self.pos[document.po_number] = document
        elif isinstance(document, BillOfLading):
            self.bls[document.invoice_no] = document
        else:
            raise TypeError(f"unsupported document type {type(document).__name__}")
        self._save()

    def on_email(self, email: Email) -> Optional[Dict[str, Any]]:
        """Scan one email. The result can only be an alert; it never moves the case."""
        self._gate("coordinator", "scan_email", Tier.L1_ANALYZE, {"email_id": email.email_id})
        bec = analyze(email, self.contacts)
        injection = injection_guard.inspect(f"{email.subject}\n{email.body}")
        alert: Optional[Dict[str, Any]] = None
        if bec.verdict is BecVerdict.BLOCKED:
            alert = bec.to_alert(self._next_alert_id())
            self.blocked_fraud_count += 1
        elif injection.suspicious:
            alert = {
                "id": self._next_alert_id(),
                "type": "INJECTION",
                "severity": "high",
                "sender": email.sender,
                "subject": email.subject,
                "reasons": [f"Instruction-like text detected ({', '.join(injection.hits)})"],
                "action_hint": "Treated as data. No action taken.",
            }
        elif bec.verdict is BecVerdict.SUSPICIOUS:
            alert = bec.to_alert(self._next_alert_id())
        if alert:
            self.alerts.append(alert)
        return alert

    def user_request(self, action: str, **kwargs: Any) -> Any:
        """Route a user action to the matching public method. Unknown actions are refused."""
        routes = {
            "weekly_run": self.weekly_run,
            "choose_option": self.choose_option,
            "prepare_pack": self.prepare_pack,
            "request_approval": self.request_approval,
            "approve": self.approve,
            "retry_double_financing": self.retry_double_financing,
            "tamper_draft": self.tamper_draft,
            "reset": self.reset,
        }
        if action not in routes:
            raise ValueError(f"unknown user request '{action}'")
        return routes[action](**kwargs)

    # ------------------------------------------------------------ pipeline steps
    def _read_sources(self) -> None:
        self._gate("coordinator", "read_bank_statements", Tier.L0_READ, {"as_of": self.as_of.isoformat()})
        self._gate("coordinator", "read_documents", Tier.L0_READ, {"invoices": len(self.all_invoices)})

    def open_invoices(self) -> List[CommercialInvoice]:
        """Invoices not yet paid."""
        return [inv for inv in self.all_invoices if inv.invoice_no not in self.paid]

    def _reconcile_all(self) -> None:
        booked: List[Dict[str, Any]] = []
        for txn in sorted(self.txns, key=lambda t: t.txn_id):
            result = self._reconcile_one(txn)
            if result.status is ReconStatus.BOOKED:
                booked.append(self.recon_rows[-1])
        if booked:
            self._gate("coordinator", "lock_period", Tier.L2_INTERNAL_WRITE, {"period_id": self._period(), "confidence": 1.0})
            self.locks.lock(self._period(), booked)

    def _period(self) -> str:
        return self.as_of.strftime("%Y-%m")

    def _reconcile_one(self, txn: BankTxn) -> ReconciliationResult:
        self._gate("coordinator", "reconcile", Tier.L1_ANALYZE, {"txn_id": txn.txn_id})
        result = reconcile(txn, self.open_invoices())
        write = {"txn_id": txn.txn_id, "invoices": result.matched_invoices, "confidence": result.confidence}
        if result.matched_invoices:
            decision = self._gate("coordinator", "ledger_write", Tier.L2_INTERNAL_WRITE, write)
            if decision.decision is Decision.ALLOWED:
                self.paid += result.matched_invoices
        elif result.status is ReconStatus.NEEDS_HUMAN:
            self._gate("coordinator", "ledger_write", Tier.L2_INTERNAL_WRITE, write)  # logged as awaiting approval
        self.recon_rows.append(self._recon_row(txn, result, booked=result.status is ReconStatus.BOOKED))
        return result

    @staticmethod
    def _recon_row(txn: BankTxn, result: ReconciliationResult, booked: bool) -> Dict[str, Any]:
        return {
            "txn_id": txn.txn_id,
            "date": txn.txn_date.isoformat(),
            "amount": float(txn.amount.amount),
            "currency": txn.amount.currency.value,
            "reference": txn.reference,
            "tier": result.tier,
            "matched_invoices": result.matched_invoices,
            "gap": float(result.gap) if result.gap is not None else None,
            "gap_reason": result.gap_reason,
            "confidence": result.confidence,
            "status": "BOOKED" if booked else result.status.value,
            "reason": result.reason,
        }

    def _forecast(self) -> None:
        decision = self._gate("coordinator", "run_forecast", Tier.L1_ANALYZE, {"paid": sorted(self.paid)})
        self.forecast_run_id = f"fc-{decision.audit_seq:04d}"
        self.forecast_inputs = loader.forecast_inputs(self.paid, self.inputs_dir)
        self.forecast = forecast_13w(self.forecast_inputs)
        self.case.move_to(CaseState.FORECASTED)
        if self.forecast.first_shortfall_week is None:
            self.case.move_to(CaseState.CLOSED)
        else:
            self.case.move_to(CaseState.SHORTFALL_DETECTED)

    def _verify_invoices(self) -> None:
        issuer = frozenset(self.profile["issuer_registry"])
        for invoice in sorted(self.open_invoices(), key=lambda i: i.invoice_no):
            self._gate("document_agent", "three_way_match", Tier.L1_ANALYZE, {"invoice": invoice.invoice_no})
            result = three_way_match(self.pos.get(invoice.po_number), invoice, self.bls.get(invoice.invoice_no))
            self.verification.append(
                {
                    "invoice_id": invoice.invoice_no,
                    "buyer": invoice.buyer_name,
                    "amount": float(invoice.amount.amount),
                    "currency": invoice.currency.value,
                    "due_date": invoice.due_date.isoformat(),
                    "status": result.status.value,
                    "differences": result.differences,
                    "registry_status": "REGISTERED" if self.registry.is_registered(invoice) else "NOT_REGISTERED",
                    "tax_id_valid": is_valid_vn_tax_id(invoice.seller_tax_id, issuer),
                }
            )
        by_no = {i.invoice_no: i for i in self.open_invoices()}
        candidates = [
            by_no[row["invoice_id"]]
            for row in self.verification
            if row["status"] == MatchStatus.ELIGIBLE.value
            and row["registry_status"] == "NOT_REGISTERED"
            and row["tax_id_valid"]
            and by_no[row["invoice_id"]].currency.value == "USD"
            and by_no[row["invoice_id"]].due_date > self.as_of
        ]
        self.nominee = max(candidates, key=lambda i: i.amount.to_usd(), default=None)

    def _rank_options(self) -> None:
        if self.nominee is None:
            self.case.move_to(CaseState.NEEDS_HUMAN, "No eligible invoice to nominate for funding")
            return
        self._gate("coordinator", "rank_funding_options", Tier.L1_ANALYZE, {"invoice": self.nominee.invoice_no})
        request = FundingRequest(
            invoice_id=self.nominee.invoice_no,
            invoice_amount_usd=self.nominee.amount.to_usd(),
            days_outstanding=(self.nominee.due_date - self.as_of).days,
            amount_needed_usd=self.forecast.shortfall_usd,
        )
        self.options = rank_options(request, self.catalog)
        self.case.move_to(CaseState.OPTIONS_RANKED)

    def _confirm_nominee(self) -> None:
        if self.state is not CaseState.OPTIONS_RANKED:
            return
        if self.registry.is_registered(self.nominee):
            self.case.move_to(CaseState.NEEDS_HUMAN, f"{self.nominee.invoice_no} is already registered")
            return
        self.case.move_to(CaseState.INVOICE_VERIFIED)

    def _process_inbox(self) -> None:
        self._gate("coordinator", "read_inbox", Tier.L0_READ, {"emails": len(self.emails)})
        for email in self.emails:
            self.on_email(email)

    def _next_alert_id(self) -> str:
        return f"AL-{len(self.alerts) + 1:02d}"

    # --------------------------------------------------------------- UI actions
    def choose_option(self, option_id: str) -> None:
        """Minh picks a funding option. Only eligible options can be chosen."""
        if self.state is not CaseState.INVOICE_VERIFIED:
            raise ValueError(f"cannot choose an option in state {self.state.value}")
        option = next((o for o in self.options if o.id == option_id), None)
        if option is None or not option.eligible:
            raise ValueError(f"option '{option_id}' is not available")
        self.selected_option_id = option_id
        self._save()

    def selected_option(self) -> Optional[LiquidityOption]:
        return next((o for o in self.options if o.id == self.selected_option_id), None)

    def prepare_pack(self) -> Dict[str, Any]:
        """Lock metrics, hash the documents, draft the letter, run the number check."""
        option = self.selected_option()
        if self.state is not CaseState.INVOICE_VERIFIED or option is None:
            raise ValueError("choose an option first")
        if option.type not in ("factoring", "loan"):
            return {"ok": False, "error": "Early-payment discounts are agreed with the buyer; there is no lender pack."}
        metrics = self._locked_metrics(option)
        locked = {m["key"]: m["value"] for m in metrics}
        docs = self._document_hashes()
        bundle_sha = sha256_of({"documents": docs, "metrics": locked})
        letter = self._draft_letter(option, locked)
        check = number_check.check(letter, locked)
        if not check.ok:
            self.case.move_to(CaseState.NEEDS_HUMAN, f"cover letter failed the number check: {check.offending}")
            self._save()
            return {"ok": False, "error": "number_check_failed", "offending": check.offending}
        payload = {
            "pack_id": f"PACK-{bundle_sha[:8].upper()}",
            "invoice_no": self.nominee.invoice_no,
            "option_id": option.id,
            "bundle_sha256": bundle_sha,
            "amount_usd": str(option.amount_usd),
        }
        self.case.move_to(CaseState.PACK_DRAFTED)
        self.case.move_to(CaseState.AWAITING_APPROVAL)
        self._pack_payload, self._bundle_sha, self._challenge = payload, bundle_sha, None
        self.pack = {
            **self._empty_pack(),
            "status": "AWAITING_APPROVAL",
            "pack_id": payload["pack_id"],
            "locked_metrics": metrics,
            "letter_text": letter,
            "number_check": {"ok": True, "offending": []},
            "action_hash": action_hash("submit_pack", payload),
            "document_hashes": docs,
            "bundle_sha256": bundle_sha,
        }
        self._save()
        return {"ok": True}

    def _locked_metrics(self, option: LiquidityOption) -> List[Dict[str, Any]]:
        ccc = compute_ccc(self.ledger)
        receivables = self.forecast_inputs.receivables
        items = [
            ("revenue_12m_usd", "12-month revenue", self.ledger.revenue_usd, "USD"),
            ("billing_volatility_pct", "Monthly billing volatility", monthly_billing_volatility_pct(self.billings), "%"),
            ("ccc_days", "Cash conversion cycle", ccc.ccc, "days"),
            ("top_buyer_share_pct", "Top buyer share of open receivables", top_buyer_share_pct(receivables), "%"),
            ("negative_cash_weeks", "Negative-cash weeks in the 13-week forecast", negative_cash_weeks(self.forecast.weeks), "weeks"),
            ("first_shortfall_week", "First shortfall week", self.forecast.first_shortfall_week, "week"),
            ("shortfall_usd", "Shortfall in that week", self.forecast.shortfall_usd, "USD"),
            ("invoice_amount_usd", f"Face value of {self.nominee.invoice_no}", self.nominee.amount.to_usd(), "USD"),
            ("advance_usd", "Funds requested", option.amount_usd, "USD"),
            ("apr_pct", "Annualised cost", option.apr_pct, "%"),
            ("days_outstanding", "Days until the invoice is due", (self.nominee.due_date - self.as_of).days, "days"),
        ]
        return [{"key": k, "label": l, "value": float(v) if isinstance(v, (Decimal, float)) else v, "unit": u} for k, l, v, u in items]

    def _document_hashes(self) -> Dict[str, str]:
        invoice = self.nominee
        documents = {
            "invoice": invoice,
            "purchase_order": self.pos[invoice.po_number],
            "bill_of_lading": self.bls[invoice.invoice_no],
        }
        return {name: sha256_of(doc.model_dump(mode="json")) for name, doc in documents.items()}

    def _draft_letter(self, option: LiquidityOption, locked: Dict[str, Any]) -> str:
        self._gate("cfo_assistant", "draft_text", Tier.L1_ANALYZE, {"pack": option.id})
        template = self._letter_template(option, locked)
        prompt = (
            "Write a short, factual cover letter for a funding pack. Use only the numbers in this JSON "
            f"and add no others: {json.dumps(locked, sort_keys=True)}. Facts: seller "
            f"{self.profile['name']}, invoice {self.nominee.invoice_no} of {self.nominee.buyer_name}, "
            f"product: {option.name}. End with the sentence 'Synthetic demo data.'"
        )
        result = self.llm.complete_structured(
            prompt, LetterDraft, LetterDraft(text=template),
            directory=self.contacts.get("staff_directory"), locked_metrics=locked,
        )
        return result.value.text

    def _letter_template(self, option: LiquidityOption, locked: Dict[str, Any]) -> str:
        run = self.forecast_run_id
        return (
            f"Dear {self.lender_name},\n\n"
            f"{self.profile['name']} asks to fund invoice {self.nominee.invoice_no} "
            f"({self.nominee.buyer_name}) through {option.name}. The invoice has a face value of "
            f"USD {locked['invoice_amount_usd']:,.2f} and falls due in {locked['days_outstanding']} days. "
            f"We request USD {locked['advance_usd']:,.2f}. Our weekly cash forecast shows a cash shortfall of "
            f"USD {locked['shortfall_usd']:,.2f} in week {locked['first_shortfall_week']} "
            f"[source: forecast run {run}]. The estimated annualised cost is {locked['apr_pct']:.1f}%. "
            "The attached pack lists the SHA-256 hash of every source document and the registry check "
            "shows this invoice has not been financed before.\n\nSynthetic demo data."
        )

    def request_approval(self) -> Dict[str, Any]:
        """Ask for the Director's OTP. Returns the challenge shown in the approval dialog."""
        if self.state is not CaseState.AWAITING_APPROVAL or self._pack_payload is None:
            raise ValueError("no pack is awaiting approval")
        self._gate("coordinator", "submit_pack", Tier.L3_EXTERNAL, self._pack_payload)  # logged AWAITING_APPROVAL
        self._challenge = self.otp.issue_challenge("submit_pack", self._pack_payload)
        return {
            "action_hash": self._challenge.action_hash,
            "expires_at": self._challenge.expires_at.isoformat(),
            "instructions": self._challenge.instructions,
        }

    def approve(self, code: str) -> Dict[str, Any]:
        """Verify the OTP for this exact pack and, only then, submit it."""
        if self._challenge is None or self._pack_payload is None:
            raise ValueError("request approval before entering a code")
        payload = self._pack_payload
        result = self.otp.verify(self._challenge, code, action_type="submit_pack", payload=payload)
        self.gate.record_approval(CASE_ID, result.approval, result.error, tool="submit_pack")
        if not result.ok:
            return {"ok": False, "error": result.error}
        if self.registry.is_registered(self.nominee) and self.selected_option().type == "factoring":
            return {"ok": False, "error": "DoubleFinancingBlocked"}
        decision = self._gate("coordinator", "submit_pack", Tier.L3_EXTERNAL, payload, approval=result.approval)
        if decision.decision is not Decision.ALLOWED:
            return {"ok": False, "error": decision.reason}
        lender_ref = self._lender_submit(payload)
        block = None
        if self.selected_option().type == "factoring":
            block = self.registry.register(self.nominee, self._bundle_sha, lender_ref)
        self.case.move_to(CaseState.SUBMITTED)
        self.pack.update(status="SUBMITTED", lender_ref=lender_ref, registry_block=block)
        self._challenge = None
        self._save()
        return {"ok": True, "error": None, "lender_ref": lender_ref}

    def retry_double_financing(self) -> Dict[str, Any]:
        """Demo: try to finance the same invoice again. The registry refuses and the attempt is logged."""
        if self.nominee is None or not self.registry.is_registered(self.nominee):
            return {"blocked": False, "error": None, "message": "Nothing to retry: the invoice is not registered yet."}
        try:
            self.registry.register(self.nominee, self._bundle_sha or "retry", "RETRY")
        except DoubleFinancingBlocked as error:
            self.audit.append(
                case_id=CASE_ID, agent="coordinator", tool="submit_pack", tier=Tier.L3_EXTERNAL,
                decision=Decision.BLOCKED, reason="DoubleFinancingBlocked",
                input_payload={"invoice_no": self.nominee.invoice_no},
            )
            return {"blocked": True, "error": "DoubleFinancingBlocked", "message": str(error)}
        raise RuntimeError("registry accepted a duplicate invoice")  # unreachable if the registry works

    def tamper_draft(self) -> Dict[str, Any]:
        """Demo: edit the drafted letter to contain an invented number and show the number lock rejects it."""
        letter = self.pack.get("letter_text")
        if not letter:
            return {"ok": False, "offending": [], "message": "Prepare a pack first."}
        locked = {m["key"]: m["value"] for m in self.pack["locked_metrics"]}
        invented = letter.replace("USD " + f"{locked['advance_usd']:,.2f}", "USD 52,000", 1)
        verdict = number_check.check(invented, locked)
        self.audit.append(
            case_id=CASE_ID, agent="cfo_assistant", tool="draft_text", tier=Tier.L1_ANALYZE,
            decision=Decision.REJECTED, reason=f"number check rejected: {', '.join(verdict.offending)}",
            input_payload={"pack_id": self.pack["pack_id"]},
        )
        return {
            "ok": verdict.ok,
            "offending": verdict.offending,
            "message": "Draft rejected: it contains a number that is not in the locked metrics.",
        }

    def simulate(self, params: ScenarioParams):
        """What-if run for the sliders (engine call; the UI never calculates)."""
        self._gate("cfo_assistant", "run_scenario", Tier.L1_ANALYZE, params.model_dump())
        return run_simulation(self.forecast_inputs, params)

    def reset(self) -> CaseState:
        """Fresh demo: clear the audit log and registry for this evidence folder and rerun the Monday flow."""
        for path in (self.audit_path, self.registry_path):
            if path.exists():
                path.unlink()
        return self.weekly_run()

    # -------------------------------------------------------------- persistence
    def _save(self) -> None:
        self.case.data = {
            "state": self.state.value,
            "paid_invoices": sorted(self.paid),
            "reconciliation": self.recon_rows,
            "forecast_run_id": self.forecast_run_id,
            "first_shortfall_week": self.forecast.first_shortfall_week if self.forecast else None,
            "shortfall_usd": float(self.forecast.shortfall_usd) if self.forecast and self.forecast.shortfall_usd else None,
            "verification": self.verification,
            "nominee": self.nominee.invoice_no if self.nominee else None,
            "options": to_contract(self.options),
            "selected_option_id": self.selected_option_id,
            "alerts": self.alerts,
            "pack": {k: v for k, v in self.pack.items() if k != "letter_text"},
        }
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        (self.cases_dir / f"{CASE_ID}.json").write_text(
            json.dumps(self.case.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8"
        )
