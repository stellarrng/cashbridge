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
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from agents import collections_agent
from agents.buyer_risk_agent import BuyerRiskAgent
from agents.document_agent import DocumentAgent, Extraction
from agents.llm_client import LlmClient
from api import lender_connector_mock
from config.settings import (
    CASES_DIR,
    EXECUTION_EVIDENCE_DIR,
    SANDBOX_INPUTS_DIR,
    Tier,
)
from core.forecasting_engine import compute_ccc, forecast_13w
from core.forecasting_engine import simulate as run_simulation
from core.funding_evaluator import FundingRequest, rank_options
from core.invoice_registry import DoubleFinancingBlocked, InvoiceRegistry, invoice_key
from core.matching_engine import reconcile, three_way_match
from core.metrics import monthly_billing_volatility_pct, negative_cash_weeks, receivable_shares_pct, top_buyer_share_pct
from core.pdf_compiler import DocSummary, PackData, bundle_sha256, compile_pack
from core.period_lock import PeriodLocks
from data import loader
from schemas.agent_schemas import CaseFile, CaseState, Decision, GateDecision, PaymentPromise
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
INJECTION_REASONS = {
    "override_instructions": "Tells the reader to ignore its instructions",
    "role_change": "Tries to change the reader's role",
    "action_command": "Asks for an action such as sending or approving",
    "tool_name": "Names an internal tool",
}
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


class Coordinator:
    """State machine for one demo case. Paths, clock and LLM client are injectable."""

    def __init__(
        self,
        inputs_dir: Path = SANDBOX_INPUTS_DIR,
        evidence_dir: Path = EXECUTION_EVIDENCE_DIR,
        cases_dir: Path = CASES_DIR,
        clock: Clock = _utc_now,
        llm: Optional[LlmClient] = None,
        lender_submit: Callable[[Dict[str, Any]], str] = lender_connector_mock.submit,
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
        self.scanned = loader.scanned_documents(d)
        self.risk = BuyerRiskAgent(loader.read("payment_history.json", d)["records"])
        self.p_on_time = {inv.invoice_no: self.risk.p_on_time(inv) for inv in self.all_invoices}
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
        self.docs = DocumentAgent(self.llm)
        self.scans: List[Dict[str, Any]] = []
        self.scan_checks: Dict[str, List[str]] = {}
        self.outbox: List[Dict[str, Any]] = []
        self._send_pending: Optional[Dict[str, Any]] = None
        self.promises: List[PaymentPromise] = []
        self.reminders: List[Dict[str, Any]] = []
        self.pack: Dict[str, Any] = self._empty_pack()
        self._pack_payload: Optional[Dict[str, Any]] = None
        self._bundle_sha: Optional[str] = None
        self._pack_generated_at = self._clock()
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
            self._score_buyers()
            self._scan_documents()
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
            # What a cloud model would be shown if it summarised this email: masked and quoted as data.
            self.llm.preview(f"{email.subject}\n{email.body}", self.contacts.get("staff_directory"))
        elif injection.suspicious:
            alert = {
                "id": self._next_alert_id(),
                "type": "INJECTION",
                "severity": "high",
                "sender": email.sender,
                "subject": email.subject,
                "reasons": [INJECTION_REASONS[hit] for hit in injection.hits],
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
        self.forecast_inputs = self._inputs_with_promises()
        self.forecast = forecast_13w(self.forecast_inputs)
        self.case.move_to(CaseState.FORECASTED)
        if self.forecast.first_shortfall_week is None:
            self.case.move_to(CaseState.CLOSED)
        else:
            self.case.move_to(CaseState.SHORTFALL_DETECTED)

    def _inputs_with_promises(self):
        inputs = loader.forecast_inputs(self.paid, self.inputs_dir, p_on_time=self.p_on_time)
        promised = {p.invoice_id: p.promised_date for p in self.promises}
        receivables = [
            r.model_copy(update={"promised_date": promised[r.invoice_id]}) if r.invoice_id in promised else r
            for r in inputs.receivables
        ]
        return inputs.model_copy(update={"receivables": receivables})

    def _score_buyers(self) -> None:
        """Read the payment history and fit the on-time model; its probabilities drive the forecast."""
        self._gate("buyer_risk_agent", "read_payment_history", Tier.L0_READ, {"months": 12})
        self._gate("buyer_risk_agent", "score_buyer_risk", Tier.L1_ANALYZE, {"invoices": len(self.p_on_time)})

    def buyer_risk_rows(self) -> List[Dict[str, Any]]:
        """Contract rows for the buyer risk panel, from the receivables the forecast uses."""
        receivables = self.forecast_inputs.receivables if self.forecast_inputs else []
        return self.risk.table(receivables, receivable_shares_pct(receivables))

    def _scan_documents(self) -> None:
        """Read every scanned document, compare it with the system record and run the 3-way match on full sets."""
        built: Dict[str, Dict[str, Any]] = {}
        for scan in self.scanned:
            self._gate("document_agent", "read_documents", Tier.L0_READ, {"doc_id": scan["doc_id"]})
            extraction = self.docs.extract(scan["text"], scan["doc_type"])
            model = {"invoice": self.docs.build_invoice, "purchase_order": self.docs.build_po, "bill_of_lading": self.docs.build_bl}[
                scan["doc_type"]
            ](extraction)
            differences = self._differences(scan, model) if model is not None else []
            problems = list(differences)
            if extraction.needs_human:
                problems.append(f"low confidence: {extraction.reason}")
            self.scan_checks.setdefault(scan["invoice_no"], []).extend(problems)
            built.setdefault(scan["invoice_no"], {})[scan["doc_type"]] = model
            self.scans.append(
                {
                    "doc_id": scan["doc_id"],
                    "doc_type": scan["doc_type"],
                    "invoice_no": scan["invoice_no"],
                    "status": "NEEDS_HUMAN" if extraction.needs_human else "READ",
                    "min_confidence": extraction.min_confidence,
                    "reason": extraction.reason,
                    "matches_record": None if extraction.needs_human or model is None else not differences,
                    "differences": differences,
                    "low_fields": [
                        {"name": n, "value": None if f.value is None else str(f.value), "confidence": f.confidence, "page": f.page}
                        for n, f in extraction.fields.items() if f.confidence < self.docs.threshold
                    ],
                    "fields_read": len(extraction.fields),
                }
            )
            if differences:
                self.alerts.append(
                    {"id": self._next_alert_id(), "type": "DOCUMENT", "severity": "high", "sender": scan["doc_id"],
                     "subject": f"Scanned {scan['doc_type'].replace('_', ' ')} differs from the record",
                     "reasons": differences, "action_hint": "A person must compare the scan with the original before it is used."}
                )
        for invoice_no, docs in built.items():
            if all(docs.get(k) is not None for k in ("invoice", "purchase_order", "bill_of_lading")):
                self._gate("document_agent", "three_way_match", Tier.L1_ANALYZE, {"invoice": invoice_no, "source": "scans"})
                result = three_way_match(docs["purchase_order"], docs["invoice"], docs["bill_of_lading"])
                for row in self.scans:
                    if row["invoice_no"] == invoice_no and row["doc_type"] == "invoice":
                        row["three_way"] = result.status.value
                if result.status is not MatchStatus.ELIGIBLE:
                    self.scan_checks.setdefault(invoice_no, []).extend(result.differences)

    def _differences(self, scan: Dict[str, Any], model: Any) -> List[str]:
        """How a scanned document disagrees with the system record of the same document."""
        record: Any
        if scan["doc_type"] == "invoice":
            record = next((i for i in self.all_invoices if i.invoice_no == scan["invoice_no"]), None)
            keys = ("amount", "currency", "buyer_id", "quantity", "package_count", "issue_date", "due_date")
        elif scan["doc_type"] == "purchase_order":
            invoice = next((i for i in self.all_invoices if i.invoice_no == scan["invoice_no"]), None)
            record = self.pos.get(invoice.po_number) if invoice else None
            keys = ("amount", "currency", "buyer_id", "quantity", "package_count")
        else:
            record = self.bls.get(scan["invoice_no"])
            keys = ("buyer_id", "quantity", "package_count", "port_of_loading", "port_of_discharge")
        if record is None:
            return []
        out = []
        for key in keys:
            a, b = getattr(model, key), getattr(record, key)
            if a != b:
                shown = lambda x: x.display() if hasattr(x, "display") else str(getattr(x, "value", x))  # noqa: E731
                out.append(f"{scan['doc_type'].replace('_', ' ')} {key.replace('_', ' ')}: scan {shown(a)} vs record {shown(b)}")
        return out

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
        problems = self.scan_checks.get(self.nominee.invoice_no, [])
        if problems:
            self.case.move_to(CaseState.NEEDS_HUMAN, "scanned documents need a human: " + "; ".join(problems))
            return
        self.case.move_to(CaseState.INVOICE_VERIFIED)

    def _process_inbox(self) -> None:
        self._gate("coordinator", "read_inbox", Tier.L0_READ, {"emails": len(self.emails)})
        for email in self.emails:
            self.on_email(email)

    def _next_alert_id(self) -> str:
        return f"AL-{len(self.alerts) + 1:02d}"

    # ------------------------------------------------------------- collections
    def collection_schedule(self) -> List[Dict[str, Any]]:
        """Next reminder for every open invoice. Invoices with a drafted reminder show that draft's status."""
        drafted = {r["invoice_id"]: r for r in self.reminders}
        rows: List[Dict[str, Any]] = []
        for invoice in sorted(self.open_invoices(), key=lambda i: i.invoice_no):
            if invoice.invoice_no in drafted:
                rows.append({k: v for k, v in drafted[invoice.invoice_no].items() if k != "text"})
                continue
            rung = collections_agent.next_rung(invoice, self.as_of)
            rows.append(
                {"invoice_id": invoice.invoice_no, "buyer": invoice.buyer_name, "stage": rung.stage,
                 "due_offset_days": rung.offset_days, "scheduled_date": rung.scheduled_date.isoformat(), "status": "scheduled",
                 "language": collections_agent.language_for(invoice)}
            )
        return rows

    def draft_reminder(self, invoice_no: str) -> Dict[str, Any]:
        """Draft the next rung of the ladder in the buyer's language.

        The first email to a buyer waits for the accountant to approve the draft; every send needs the Director's OTP.
        """
        invoice = next((i for i in self.open_invoices() if i.invoice_no == invoice_no), None)
        if invoice is None:
            raise ValueError(f"{invoice_no} is not an open invoice")
        self._gate("collections_agent", "draft_text", Tier.L1_ANALYZE, {"invoice": invoice_no})
        rung = collections_agent.next_rung(invoice, self.as_of)
        text = collections_agent.draft_reminder(invoice, rung)
        locked = {"amount": float(invoice.amount.amount), "days": rung.offset_days}
        verdict = number_check.check(text, locked)
        if not verdict.ok:
            raise ValueError(f"reminder failed the number check: {verdict.offending}")
        first = invoice.buyer_id not in {r["buyer_id"] for r in self.outbox}
        reminder = {
            "invoice_id": invoice_no,
            "buyer": invoice.buyer_name,
            "buyer_id": invoice.buyer_id,
            "stage": rung.stage,
            "due_offset_days": rung.offset_days,
            "scheduled_date": rung.scheduled_date.isoformat(),
            "status": "draft" if first else "awaiting_approval",
            "language": collections_agent.language_for(invoice),
            "first_for_buyer": first,
            "text": text,
        }
        self.reminders = [r for r in self.reminders if r["invoice_id"] != invoice_no] + [reminder]
        self._save()
        return reminder

    def approve_draft(self, invoice_no: str, approver: str = "Lan") -> Dict[str, Any]:
        """The accountant approves a first-email draft. Sending it is a separate L3 action that needs the Director's OTP."""
        reminder = next((r for r in self.reminders if r["invoice_id"] == invoice_no and r["status"] == "draft"), None)
        if reminder is None:
            raise ValueError(f"no draft reminder for {invoice_no}")
        self.audit.append(
            case_id=CASE_ID, agent="collections_agent", tool="draft_text", tier=Tier.L1_ANALYZE,
            decision=Decision.APPROVED, reason=f"draft approved by {approver}; sending needs Director OTP",
            input_payload={"invoice": invoice_no},
        )
        reminder["status"] = "awaiting_approval"
        self._save()
        return reminder

    def request_send_reminder(self, invoice_no: str) -> Dict[str, Any]:
        """Ask for the Director's OTP to send an approved reminder. The code is bound to this exact email."""
        reminder = next((r for r in self.reminders if r["invoice_id"] == invoice_no and r["status"] == "awaiting_approval"), None)
        if reminder is None:
            raise ValueError(f"no approved reminder waiting to be sent for {invoice_no}")
        payload = {"invoice_no": invoice_no, "stage": reminder["stage"], "buyer_id": reminder["buyer_id"],
                   "body_sha256": sha256_of(reminder["text"])}
        self._gate("coordinator", "send_email", Tier.L3_EXTERNAL, payload)  # logged AWAITING_APPROVAL
        challenge = self.otp.issue_challenge("send_email", payload)
        self._send_pending = {"payload": payload, "challenge": challenge, "invoice_no": invoice_no}
        return {"action_hash": challenge.action_hash, "expires_at": challenge.expires_at.isoformat(), "instructions": challenge.instructions}

    def approve_send_reminder(self, code: str) -> Dict[str, Any]:
        """Verify the OTP and, only then, send (the mock outbox records the email)."""
        if self._send_pending is None:
            raise ValueError("request approval before entering a code")
        pending = self._send_pending
        result = self.otp.verify(pending["challenge"], code, action_type="send_email", payload=pending["payload"])
        self.gate.record_approval(CASE_ID, result.approval, result.error, tool="send_email")
        if not result.ok:
            return {"ok": False, "error": result.error}
        decision = self._gate("coordinator", "send_email", Tier.L3_EXTERNAL, pending["payload"], approval=result.approval)
        if decision.decision is not Decision.ALLOWED:
            return {"ok": False, "error": decision.reason}
        reminder = next(r for r in self.reminders if r["invoice_id"] == pending["invoice_no"])
        reminder["status"] = "sent"
        self.outbox.append({"invoice_id": reminder["invoice_id"], "buyer_id": reminder["buyer_id"], "stage": reminder["stage"],
                            "language": reminder["language"], "body_sha256": pending["payload"]["body_sha256"]})
        self._send_pending = None
        self._save()
        return {"ok": True, "error": None}

    def on_buyer_reply(self, email: Email) -> Optional[Dict[str, Any]]:
        """Read a buyer reply. A stated payment date becomes a promise and the forecast is rerun.

        The reply is data only: it is guard-scanned first, and it can change a date in the
        forecast but can never trigger an action.
        """
        if self.on_email(email) is not None:
            return None
        invoice_no = collections_agent.invoice_in_text(f"{email.subject} {email.body}")
        invoice = next((i for i in self.open_invoices() if i.invoice_no == invoice_no), None)
        if invoice is None:
            return None
        self._gate("collections_agent", "parse_reply", Tier.L1_ANALYZE, {"email_id": email.email_id})
        promise = collections_agent.parse_payment_promise(email.body, invoice_no, invoice.buyer_name, self.as_of)
        if promise is None:
            return None
        before = self.forecast
        self.promises.append(promise)
        decision = self._gate("coordinator", "run_forecast", Tier.L1_ANALYZE, {"promise": promise.invoice_id})
        self.forecast_run_id = f"fc-{decision.audit_seq:04d}"
        self.forecast_inputs = self._inputs_with_promises()
        self.forecast = forecast_13w(self.forecast_inputs)
        self._save()
        return {
            "promise": promise,
            "first_shortfall_week_before": before.first_shortfall_week,
            "first_shortfall_week_after": self.forecast.first_shortfall_week,
            "shortfall_before_usd": before.shortfall_usd,
            "shortfall_after_usd": self.forecast.shortfall_usd,
        }

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

    def prepare_pack(self, prepared_by: Optional[str] = None) -> Dict[str, Any]:
        """Lock metrics, hash the documents, draft the letter, run the number check.

        ``prepared_by`` records the human (or the human who ran the Autopilot) so the approver can be
        checked against it: the person who prepares a pack may not approve it.
        """
        option = self.selected_option()
        if self.state is not CaseState.INVOICE_VERIFIED or option is None:
            raise ValueError("choose an option first")
        if option.type not in ("factoring", "loan"):
            return {"ok": False, "error": "Early-payment discounts are agreed with the buyer; there is no lender pack."}
        metrics = self._locked_metrics(option)
        locked = {m["key"]: m["value"] for m in metrics}
        docs = self._document_hashes()
        bundle_sha = bundle_sha256(docs, locked)
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
        self._pack_generated_at = self._clock()
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
            "prepared_by": prepared_by,
            "approved_by": None,
        }
        self._write_pdf(option)
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

    @property
    def pack_pdf_file(self) -> Optional[Path]:
        """The Verifiable Funding Pack PDF for the current pack, if one has been written."""
        return self.evidence_dir / self.pack["pdf_path"] if self.pack.get("pdf_path") else None

    def _write_pdf(self, option: LiquidityOption) -> None:
        """Compile the pack PDF (again after submission, so it also carries the registry block and lender reference)."""
        invoice = self.nominee
        po, bl = self.pos[invoice.po_number], self.bls[invoice.invoice_no]
        match = three_way_match(po, invoice, bl)
        block = self.pack.get("registry_block")
        docs = [
            DocSummary(title="Commercial invoice", rows=[
                ["Invoice no", invoice.invoice_no], ["Buyer", invoice.buyer_name], ["Amount", invoice.amount.display()],
                ["Issued", invoice.issue_date.isoformat()], ["Due", invoice.due_date.isoformat()],
                ["Quantity / packages", f"{invoice.quantity} / {invoice.package_count}"],
                ["Route", f"{invoice.port_of_loading} to {invoice.port_of_discharge}"]]),
            DocSummary(title="Purchase order", rows=[["PO number", po.po_number], ["Amount", po.amount.display()],
                                                     ["Quantity / packages", f"{po.quantity} / {po.package_count}"]]),
            DocSummary(title="Bill of lading", rows=[["B/L number", bl.bl_number], ["Quantity / packages", f"{bl.quantity} / {bl.package_count}"],
                                                     ["Route", f"{bl.port_of_loading} to {bl.port_of_discharge}"],
                                                     ["Shipped on board", bl.shipped_on_board_date.isoformat()]]),
        ]
        scan_lines = [
            f"{s['doc_id']}: {'read' if s['status'] == 'READ' else 'needs a person'}, lowest confidence {s['min_confidence']:.2f}"
            + (", matches the record" if s["matches_record"] else "")
            for s in self.scans if s["invoice_no"] == invoice.invoice_no
        ]
        ccc = compute_ccc(self.ledger)
        formulas = [
            ["Cash conversion cycle", f"CCC = DIO + DSO - DPO = {ccc.dio:g} + {ccc.dso:g} - {ccc.dpo:g} = {ccc.ccc:g} days (from the ledger)"],
            ["Annualised cost", f"APR = total cost / net funds received x 365 / days outstanding. This product: total cost USD "
                                f"{option.cost_breakdown['total_usd']:,.2f}, funds USD {option.amount_usd:,.2f}, {(invoice.due_date - self.as_of).days} days, "
                                f"APR {option.apr_pct:.2f}%. Net funds are the amount received after any upfront fee."],
            ["13-week forecast", "Expected inflow = invoice value x chance of on-time payment, in the due week; the late share arrives four weeks "
                                 "later. Closing = opening + inflows - outflows. First shortfall = first week with closing below zero."],
            ["3-way match", "Invoice and purchase order amounts within 0.01; quantity, package count, ports and buyer must agree."],
            ["Registry key", "SHA-256 of seller tax ID | invoice no | buyer | currency | amount in minor units | issue date."],
            ["Bundle hash", "SHA-256 of canonical JSON {documents: document hashes, metrics: locked metrics}, keys sorted, no spaces."],
        ]
        data = PackData(
            pack_id=self.pack["pack_id"], company=self.profile["name"], lender=self.lender_name, product=option.name,
            generated_at=self._pack_generated_at, forecast_run=self.forecast_run_id or "n/a", invoice_no=invoice.invoice_no,
            amount_requested=f"USD {option.amount_usd:,.2f}", letter_text=self.pack["letter_text"],
            locked_metrics=[[m["label"], formatted] for m, formatted in ((m, self._metric_text(m)) for m in self.pack["locked_metrics"])],
            documents=docs, three_way_status=match.status.value, three_way_differences=match.differences, scan_lines=scan_lines,
            document_hashes=self.pack["document_hashes"], bundle_sha256=self._bundle_sha, action_hash=self.pack["action_hash"],
            registry_check=(f"Registered in block {block['block_index']}" if block else "No entry for this invoice key at preparation"),
            registry_key=invoice_key(invoice), registry_head=(block["previous_block_hash"] if block else self.registry.head_hash()),
            registry_block=block, lender_ref=self.pack.get("lender_ref"),
            attribution=[[a.driver, f"USD {a.amount_usd:,.2f}"] for a in self.forecast.attribution], formulas=formulas,
        )
        relative = Path("packs") / f"{self.pack['pack_id']}.pdf"
        compile_pack(data, self.evidence_dir / relative)
        self.pack["pdf_path"] = str(relative)

    @staticmethod
    def _metric_text(metric: Dict[str, Any]) -> str:
        unit, value = metric["unit"], metric["value"]
        if unit == "USD":
            return f"USD {value:,.2f}"
        if unit == "%":
            return f"{value:.1f}%"
        return f"Week {value:g}" if unit == "week" else f"{value:g} {unit}"

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
        # Local audited template, never send firm/buyer/invoice data to an LLM.
        return self._letter_template(option, locked)

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

    def approve(self, code: str, approver: Optional[str] = None) -> Dict[str, Any]:
        """Verify the OTP for this exact pack and, only then, submit it.

        With ``approver`` set, segregation of duties is enforced before the code is even checked
        (so a refused self-approval does not spend the one-time code).
        """
        if self._challenge is None or self._pack_payload is None:
            raise ValueError("request approval before entering a code")
        payload = self._pack_payload
        preparer = self.pack.get("prepared_by")
        if approver is not None and preparer is not None and approver == preparer:
            self.audit.append(
                case_id=CASE_ID, agent="coordinator", tool="submit_pack", tier=Tier.L3_EXTERNAL,
                decision=Decision.REJECTED, reason="Segregation of duties: the preparer cannot approve the same pack",
                input_payload={"pack_id": self.pack.get("pack_id"), "approver": approver},
            )
            return {"ok": False, "error": "segregation_of_duties"}
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
        self.pack.update(status="SUBMITTED", lender_ref=lender_ref, registry_block=block, approved_by=approver)
        self._write_pdf(self.selected_option())
        self._challenge = None
        self._save()
        return {"ok": True, "error": None, "lender_ref": lender_ref}

    def reject_pack(self, by: str, reason: str) -> Dict[str, Any]:
        """The Director declines a pack awaiting approval. Nothing leaves the system; the case waits for the preparer."""
        if self.state is not CaseState.AWAITING_APPROVAL:
            raise ValueError("no pack is awaiting approval")
        reason = (reason or "no reason given").strip()[:300]
        self.audit.append(
            case_id=CASE_ID, agent="coordinator", tool="submit_pack", tier=Tier.L3_EXTERNAL,
            decision=Decision.REJECTED, reason=f"Rejected by {by}: {reason}",
            input_payload={"pack_id": self.pack.get("pack_id")},
        )
        self.case.move_to(CaseState.NEEDS_HUMAN, f"Director rejected the pack: {reason}")
        self.pack.update(status="REJECTED_BY_DIRECTOR", rejected_by=by, rejection_reason=reason)
        self._pack_payload, self._challenge = None, None
        self._save()
        return {"ok": True}

    def reopen_after_rejection(self) -> Dict[str, Any]:
        """The preparer takes a rejected pack back to the option-choice step."""
        if self.state is not CaseState.NEEDS_HUMAN or self.pack.get("status") != "REJECTED_BY_DIRECTOR":
            raise ValueError("there is no rejected pack to rework")
        self.case.move_to(CaseState.INVOICE_VERIFIED)
        self.selected_option_id = None
        self.pack = self._empty_pack()
        self._save()
        return {"ok": True}

    def record_bank_decision(self, decision: str, reviewer: str, note: str = "") -> Dict[str, Any]:
        """A named human at the lender records the credit decision on the submitted pack (MOCK lender)."""
        if decision not in ("APPROVE_FUNDING", "REQUEST_INFO", "DECLINE"):
            raise ValueError("decision must be APPROVE_FUNDING, REQUEST_INFO or DECLINE")
        if self.state is not CaseState.SUBMITTED:
            raise ValueError("only a submitted pack can receive a lender decision")
        note = (note or "").strip()[:500]
        if decision != "APPROVE_FUNDING" and not note:
            raise ValueError("explain a decline or an information request")
        payload = {"pack_id": self.pack.get("pack_id"), "decision": decision, "note_sha256": sha256_of({"note": note})}
        self._gate("bank_reviewer", "record_credit_decision", Tier.L2_INTERNAL_WRITE, payload, human_approver=reviewer)
        if decision == "APPROVE_FUNDING":
            self.case.move_to(CaseState.FUNDED)
            self.pack.update(status="FUNDED_MOCK")
        elif decision == "DECLINE":
            self.case.move_to(CaseState.REJECTED)
            self.pack.update(status="DECLINED_BY_LENDER")
        self._save()
        return {"ok": True, "decision": decision}

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
            "message": "The draft contains a number that is not in the locked metrics, so it cannot be sent.",
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
            "collections": {
                "schedule": self.collection_schedule(),
                "promises": [
                    {"invoice_id": p.invoice_id, "buyer": p.buyer,
                     "promised_date": p.promised_date.isoformat(), "source_text": p.source_text}
                    for p in self.promises
                ],
            },
            "pack": {k: v for k, v in self.pack.items() if k != "letter_text"},
        }
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        (self.cases_dir / f"{CASE_ID}.json").write_text(
            json.dumps(self.case.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8"
        )
