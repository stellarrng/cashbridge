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

from agents.cfo_assistant import CfoAssistant
from agents.coordinator import Coordinator
from agents.llm_client import LlmClient
from config.settings import EXECUTION_EVIDENCE_DIR, FX_NOTE, RUNTIME_DIR, SANDBOX_INPUTS_DIR, USD_VND
from core.forecasting_engine import compute_ccc
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
    "pdf_path", "lender_ref", "registry_block",
)


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
        self._start()

    # ------------------------------------------------------------------ setup
    def _start(self) -> None:
        """Every server start is a fresh demo session: the previous session's audit log and registry are cleared."""
        self.coord.reset()
        self.assistant = CfoAssistant(self.coord)
        self._chat = [self._briefing()]

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
        return {"role": "assistant", "text": text, "citations": citations, "mode": self.coord.llm.current_mode()}

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
            "buyer_risk": [],
            "evidence": self._evidence(),
        }

    def _meta(self) -> Dict[str, Any]:
        c = self.coord
        return {
            "mode": c.llm.current_mode(),
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

    def _pii_inspector(self) -> Dict[str, str]:
        inspector = self.coord.llm.pii_inspector()
        offline = self.coord.llm.current_mode() == "offline-demo"
        return {
            **inspector,
            "note": "Preview only: offline mode, nothing was sent to a cloud model." if offline
            else "Text as sent to the model provider.",
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
        reply = self.assistant.ask(text)
        self._chat += [{"role": "user", "text": text, "citations": [], "mode": reply["mode"]}, reply]
        return reply

    def choose_option(self, option_id: str) -> Dict[str, Any]:
        return self._try(lambda: self.coord.choose_option(option_id))

    def prepare_pack(self) -> Dict[str, Any]:
        def action() -> None:
            outcome = self.coord.prepare_pack()
            if not outcome.get("ok"):
                raise ValueError(outcome.get("error", "the pack could not be prepared"))

        return self._try(action)

    def request_otp(self) -> Dict[str, Any]:
        return self.coord.request_approval()

    def approve(self, code: str) -> Dict[str, Any]:
        result = self.coord.approve(code)
        return {"ok": result["ok"], "error": result["error"], "snapshot": self.get_snapshot()}

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
        self._last_error = None
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
