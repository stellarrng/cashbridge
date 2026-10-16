"""Run the 11-step demo story (instructions.md section 9) headless and write the evidence.

    python scripts/run_demo_story.py        (or: make story)

It seeds a fresh SYNTHETIC input copy in a temporary folder, drives the coordinator through
every step, checks each outcome, and regenerates in ``data/execution_evidence/``:
sandbox_operation_logs.jsonl, invoice_registry.json, story_summary.md and ANCHORS.md.

Time is simulated (07:00 UTC, one second per call) so the evidence is byte-identical on every
run. The TOTP code is generated from the demo secret inside this script: that is demo
automation standing in for the Director's authenticator app.
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.coordinator import Coordinator  # noqa: E402
from config.settings import EXECUTION_EVIDENCE_DIR, Tier  # noqa: E402
from data import seed_sandbox  # noqa: E402
from schemas.agent_schemas import CaseState  # noqa: E402
from scripts.anchor_head import anchor  # noqa: E402
from security import number_check  # noqa: E402
from security.audit_log import verify_chain  # noqa: E402

START = datetime(2026, 10, 19, 7, 0, 0, tzinfo=timezone.utc)
BUYER_REPLY_ID = "EML-005"


class StoryFailed(Exception):
    """A story step did not produce the expected outcome."""


class StoryClock:
    """Simulated clock: starts at 07:00 UTC and advances one second per call."""

    def __init__(self) -> None:
        self._now = START - timedelta(seconds=1)

    def __call__(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


@dataclass
class Outcome:
    step: int
    title: str
    result: str


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise StoryFailed(message)


def _usd(value: Decimal) -> str:
    return f"USD {value:,.2f}"


def run(evidence_dir: Path = EXECUTION_EVIDENCE_DIR, log: Callable[[str], None] = print) -> List[Outcome]:
    """Run the story and return one Outcome per step. Raises StoryFailed on any mismatch."""
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for name in ("sandbox_operation_logs.jsonl", "invoice_registry.json", "story_summary.md", "ANCHORS.md"):
        (evidence_dir / name).unlink(missing_ok=True)

    outcomes: List[Outcome] = []

    def record(step: int, title: str, result: str) -> None:
        outcomes.append(Outcome(step, title, result))
        log(f"STEP {step:>2}  {title}\n         {result}")

    with tempfile.TemporaryDirectory() as workdir:
        work = Path(workdir)
        seed_sandbox.write_all(work / "inputs")
        coord = Coordinator(
            inputs_dir=work / "inputs", evidence_dir=evidence_dir, cases_dir=work / "cases", clock=StoryClock()
        )
        
        def lines() -> List[dict]:
            return [json.loads(l) for l in coord.audit_path.read_text().splitlines()]

        def seq_of(tool: str, decision: str) -> int:
            return next(l["seq"] for l in lines() if l["tool"] == tool and l["decision"] == decision)

        # ---- 07:00 weekly trigger runs reconcile, forecast, options, verification, inbox
        coord.weekly_run()
        expect(coord.state is CaseState.INVOICE_VERIFIED, f"Monday run ended in {coord.state.value}")

        # 1
        wire = next(r for r in coord.recon_rows if r["txn_id"] == "TXN-0912")
        expect(wire["tier"] == 3 and wire["status"] == "BOOKED", "wire was not booked by subset-sum")
        expect(set(wire["matched_invoices"]) == {"INV-1021", "INV-1022", "INV-1024"}, "wrong invoices matched")
        expect(wire["gap"] == 35 and wire["gap_reason"] == "bank_fee", "gap is not a USD 35 bank fee")
        record(1, "07:00 trigger: reconcile the USD 48,620 wire",
               f"Tier 1 failed; Tier 3 subset-sum matched {', '.join(sorted(wire['matched_invoices']))}; "
               f"gap USD 35 booked as bank fee; L2 ledger write logged (audit line {seq_of('ledger_write', 'ALLOWED')}).")

        # 2
        forecast = coord.forecast
        expect(forecast.first_shortfall_week == 7, f"first shortfall week is {forecast.first_shortfall_week}")
        drivers = [a for a in forecast.attribution if a.source_ref != "ledger:baseline"]
        expect(any(a.source_ref == "doc:PO-2214" for a in drivers), "deposit missing from attribution")
        expect(any(a.source_ref.startswith("inv:") for a in drivers), "late invoice missing from attribution")
        top_drivers = sorted(drivers, key=lambda a: a.amount_usd, reverse=True)[:2]
        record(2, "Forecast reruns: week 7 shortfall",
               f"First negative week {forecast.first_shortfall_week}, shortfall {_usd(forecast.shortfall_usd)}; main drivers: "
               + "; ".join(f"{a.driver} ({_usd(a.amount_usd)})" for a in top_drivers)
               + f"; {len(drivers) - len(top_drivers)} smaller late-invoice drivers. State SHORTFALL_DETECTED.")

        # 3
        menu = coord.options
        expect([o.id for o in menu][:3] == ["factoring_inv1030", "bridge_loan", "early_discount"], "ranking order is wrong")
        expect(not menu[3].eligible and menu[3].id == "overdraft", "overdraft should be ineligible")
        record(3, "Funding evaluator ranks the liquidity menu",
               " < ".join(f"{o.name} {o.apr_pct:.1f}%" for o in menu[:3]) + f"; overdraft not eligible ({menu[3].ineligible_reason}). State OPTIONS_RANKED.")

        # 4
        rows = {r["invoice_id"]: r for r in coord.verification}
        expect(rows["INV-1030"]["status"] == "ELIGIBLE" and rows["INV-1030"]["registry_status"] == "NOT_REGISTERED", "INV-1030")
        expect(rows["INV-1027"]["status"] == "FLAGGED", "INV-1027 should be flagged")
        record(4, "Verification: 3-way match and registry check",
               f"INV-1030 ELIGIBLE (registry has no entry); INV-1027 FLAGGED ({'; '.join(rows['INV-1027']['differences'])}), excluded. "
               "State INVOICE_VERIFIED.")

        # 5
        bec = next(a for a in coord.alerts if a["type"] == "BEC")
        expect(coord.blocked_fraud_count == 1, "BEC email was not blocked")
        refused = coord.gate.check("coordinator", "update_payee", Tier.L4_MONEY_MOVEMENT, coord.case.case_id,
                                   {"reason": "change requested by the BEC email"})
        expect(refused.decision.value == "BLOCKED", "L4 payee change was not blocked")
        injection = [a for a in coord.alerts if a["type"] == "INJECTION"]
        record(5, "Inbox: BEC email blocked",
               f"{bec['sender']} BLOCKED ({'; '.join(bec['reasons'])}); critical alert raised. "
               f"A payee change (L4) is refused by the gatekeeper (audit line {refused.audit_seq}). "
               f"{len(injection)} injection email treated as data.")

        # 6
        top = next(o for o in coord.options if o.eligible)
        locked = {"week": forecast.first_shortfall_week, "shortfall": forecast.shortfall_usd,
                  "amount": top.amount_usd, "apr": top.apr_pct}
        message = (
            f"Week {locked['week']} is expected to be short by {_usd(forecast.shortfall_usd)}. Cheapest option: "
            f"{top.name} for {_usd(top.amount_usd)} at about {top.apr_pct:.1f}% a year. "
            f"[source: forecast run {coord.forecast_run_id}] [source: funding:{top.id}]"
        )
        expect(number_check.check(message, locked).ok, "CFO message failed the number check")
        coord.choose_option(top.id)
        expect(coord.prepare_pack()["ok"], "pack could not be prepared")
        expect(coord.state is CaseState.AWAITING_APPROVAL, "pack is not awaiting approval")
        record(6, "CFO assistant briefs Minh; Minh prepares the pack",
               f"\"{message}\" Pack {coord.pack['pack_id']}: metrics locked, documents hashed, letter passed the number check. "
               "State AWAITING_APPROVAL.")

        # 7
        tampered = coord.tamper_draft()
        expect(tampered["ok"] is False and tampered["offending"] == ["USD 52,000"], "tampered draft was not rejected")
        record(7, "Negative test: tampered draft",
               f"Draft with an invented number was rejected by the number check ({', '.join(tampered['offending'])}).")

        # 8
        challenge = coord.request_approval()
        wrong = coord.approve("000000" if coord.otp.current_code() != "000000" else "111111")
        expect(wrong == {"ok": False, "error": "invalid_code"}, "wrong OTP was not refused")
        result = coord.approve(coord.otp.current_code())  # demo automation: the Director's authenticator
        expect(result["ok"] and coord.state is CaseState.SUBMITTED, "approval did not submit the pack")
        block = coord.pack["registry_block"]
        expect(block is not None and coord.registry.verify_chain() == (True, None), "registry write failed")
        record(8, "Minh approves with OTP; pack submitted to the mock lender",
               f"A wrong code was refused (invalid_code). OTP bound to action_hash {challenge['action_hash'][:12]}... accepted; "
               f"submit_pack allowed (audit line {seq_of('submit_pack', 'ALLOWED')}); lender ref {result['lender_ref']}; "
               f"registry block {block['block_index']} written for INV-1030. State SUBMITTED.")

        # 9
        again = coord.retry_double_financing()
        expect(again["blocked"] and again["error"] == "DoubleFinancingBlocked", "double financing was not blocked")
        record(9, "Negative test: finance INV-1030 a second time",
               f"DoubleFinancingBlocked raised; registry still has {len(coord.registry.blocks())} block.")

        # 10
        reminder = coord.draft_reminder("INV-1026")
        approved = coord.approve_draft("INV-1026", "Lan")
        reply = next(e for e in coord.emails if e.email_id == BUYER_REPLY_ID)
        effect = coord.on_buyer_reply(reply)
        expect(effect is not None and effect["promise"].promised_date.isoformat() == "2026-11-20", "promise not parsed")
        after = effect["shortfall_after_usd"]
        expect(after is None or after < effect["shortfall_before_usd"], "the promise did not improve the forecast")
        record(10, "Collections: reminder drafted, buyer promises a date",
               f"Gentle reminder for INV-1026 drafted (scheduled {reminder['scheduled_date']}) and approved by Lan "
               f"(status {approved['status']}; sending needs the Director's OTP). Reply \"{effect['promise'].source_text}\" "
               f"became a promise for {effect['promise'].promised_date}; week-7 shortfall "
               f"{_usd(effect['shortfall_before_usd'])} -> {_usd(after) if after is not None else 'none'}.")

        # 11
        ok, broken, checked = verify_chain(coord.audit_path)
        expect(ok, f"audit chain broken at line {broken}")
        tiers = {l["tier"]: set() for l in lines()}
        for l in lines():
            tiers[l["tier"]].add(l["decision"])
        expect("APPROVED" in tiers["L3_EXTERNAL"] and "ALLOWED" in tiers["L3_EXTERNAL"], "no approved L3 lines")
        expect(tiers["L4_MONEY_MOVEMENT"] == {"BLOCKED"}, "L4 lines must all be BLOCKED")
        anchor_row = anchor(evidence_dir, clock=StoryClock())
        record(11, "Audit chain verified and anchored",
               f"verify_chain passed over {checked} lines; tiers logged: {', '.join(sorted(tiers))}; "
               f"head hashes written to ANCHORS.md.")

        _write_summary(evidence_dir, outcomes, coord, checked, anchor_row)
    return outcomes


def _write_summary(evidence_dir: Path, outcomes: List[Outcome], coord: Coordinator, lines: int, anchor_row: str) -> None:
    pack = coord.pack
    table = "\n".join(f"| {o.step} | {o.title} | {o.result.replace('|', '/')} |" for o in outcomes)
    text = f"""# Demo story summary (SYNTHETIC DEMO DATA)

Generated by `scripts/run_demo_story.py` for Binh Duong Timberworks Co., Ltd. (SYNTHETIC).
Time is simulated (07:00 UTC, one second per call) so this file is identical on every run.
The OTP code was generated from the public demo secret inside the script (demo automation).

| Step | What happened | Outcome |
|---|---|---|
{table}

## Evidence produced

- `sandbox_operation_logs.jsonl`: {lines} hash-chained lines (tamper-evident), one per gatekeeper decision.
- `invoice_registry.json`: {len(coord.registry.blocks())} block, head `{coord.registry.head_hash()}`.
- `ANCHORS.md`: {anchor_row.strip()}
- Pack `{pack['pack_id']}`: action hash `{pack['action_hash']}`, bundle SHA-256 `{pack['bundle_sha256']}`.

Honest limits: the registry lives inside one SME installation, so it cannot stop the same invoice
being financed at a second lender; anchoring the head hashes in git is the only protection against
a local rewrite of the chains.
"""
    (evidence_dir / "story_summary.md").write_text(text, encoding="utf-8")


def main() -> None:
    try:
        run()
    except StoryFailed as failure:
        raise SystemExit(f"STORY FAILED: {failure}")
    print("\nAll 11 steps passed. Evidence written to data/execution_evidence/.")


if __name__ == "__main__":
    main()
