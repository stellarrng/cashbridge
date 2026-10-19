"""Document agent, scanned-document checks and the full reminder ladder (Step 5.2)."""

import json
from datetime import date
from decimal import Decimal

import pytest

from agents import collections_agent as ca
from agents.coordinator import Coordinator
from agents.document_agent import DocumentAgent, rule_extract
from agents.llm_client import LlmClient
from config.settings import Tier
from data import loader, seed_sandbox
from schemas.agent_schemas import CaseState
from schemas.document_schemas import MatchStatus
from scripts.run_demo_story import StoryClock
from core.matching_engine import three_way_match
from security import number_check

INVOICE_TEXT = (
    "COMMERCIAL INVOICE\n--- page 1 ---\nInvoice No: INV-9\nPO Number: PO-9\nSeller Tax ID: 0312345678\nBuyer ID: B-US-01\n"
    "Buyer: Oakline Home LLC (SYNTHETIC)\nMarket: US\nCurrency: USD\n--- page 2 ---\nTotal Amount: 1,250.50\nQuantity: 10\n"
    "Packages: 10\nPort of Loading: Cat Lai\nPort of Discharge: Los Angeles\nIssue Date: 2026-10-01\nDue Date: 2026-11-30"
)


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("doc_inputs")
    seed_sandbox.write_all(folder)
    return folder


def coordinator(inputs, tmp_path):
    return Coordinator(inputs_dir=inputs, evidence_dir=tmp_path / "e", cases_dir=tmp_path / "c", clock=StoryClock())


# --------------------------------------------------------------- extraction
def test_clean_scan_is_read_with_high_confidence_and_pages():
    e = rule_extract(INVOICE_TEXT, "invoice")
    assert not e.needs_human and e.min_confidence == 0.97 and e.reason is None
    assert e.fields["amount"].value == Decimal("1250.50") and e.fields["amount"].page == 2
    assert e.fields["invoice_no"].page == 1 and e.fields["due_date"].value == date(2026, 11, 30)


def test_lookalike_characters_are_repaired_but_scored_low_and_sent_to_a_human():
    e = rule_extract(INVOICE_TEXT.replace("1,250.50", "1,25O.5O"), "invoice")
    assert e.needs_human and e.min_confidence == 0.60
    assert e.fields["amount"].value == Decimal("1250.50") and "read '1,25O.5O' as" in e.fields["amount"].reason
    assert DocumentAgent().build_invoice(e) is None  # nothing is built from a guess


def test_missing_and_unreadable_fields_block_the_document():
    missing = rule_extract(INVOICE_TEXT.replace("Due Date: 2026-11-30", ""), "invoice")
    assert missing.needs_human and missing.fields["due_date"].confidence == 0.0 and "not found" in missing.reason
    garbled = rule_extract(INVOICE_TEXT.replace("Quantity: 10", "Quantity: ten"), "invoice")
    assert garbled.fields["quantity"].confidence == 0.30 and garbled.needs_human


def test_threshold_is_the_spec_value():
    assert DocumentAgent().threshold == 0.85


def test_confident_invoice_becomes_a_typed_model():
    invoice = DocumentAgent().build_invoice(rule_extract(INVOICE_TEXT, "invoice"))
    assert invoice.invoice_no == "INV-9" and invoice.amount.minor_units == 125050 and invoice.package_count == 10


def test_unknown_document_type_is_refused():
    with pytest.raises(ValueError):
        rule_extract("x", "receipt")


def test_live_model_values_must_appear_in_the_document():
    class Provider:
        def __init__(self, amount):
            self.amount = amount

        def __call__(self, messages, model, timeout):
            e = rule_extract(INVOICE_TEXT, "invoice")
            data = json.loads(e.model_dump_json())
            data["fields"]["amount"]["value"] = self.amount
            return json.dumps(data)

    honest = DocumentAgent(LlmClient(base_url="x", model="m", api_key="k", provider=Provider("1250.50")))
    assert honest.extract(INVOICE_TEXT, "invoice").fields["amount"].value == Decimal("1250.50")
    invented = DocumentAgent(LlmClient(base_url="x", model="m", api_key="k", provider=Provider("9999.00")))
    assert invented.extract(INVOICE_TEXT, "invoice").fields["amount"].value == Decimal("1250.50")  # fell back to the rules


# ------------------------------------------------------- coordinator + seed
def test_seed_scans_of_inv_1030_match_the_records_and_pass_the_three_way_match(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    c.weekly_run()
    rows = {r["doc_id"]: r for r in c.scans}
    for doc in ("SCAN-INV-1030", "SCAN-PO-1030", "SCAN-BL-1030"):
        assert rows[doc]["status"] == "READ" and rows[doc]["matches_record"] is True and rows[doc]["min_confidence"] >= 0.85
    assert rows["SCAN-INV-1030"]["three_way"] == "ELIGIBLE"
    assert c.state is CaseState.INVOICE_VERIFIED


def test_the_poor_scan_is_flagged_for_a_person(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    c.weekly_run()
    poor = next(r for r in c.scans if r["doc_id"] == "SCAN-INV-1036")
    assert poor["status"] == "NEEDS_HUMAN" and poor["matches_record"] is None
    assert {f["name"] for f in poor["low_fields"]} == {"amount", "package_count", "due_date"}
    assert "read '1O,5OO.OO' as 10500.00" in poor["reason"]


def test_a_nominated_invoice_with_an_unreadable_scan_stops_the_case(inputs, tmp_path):
    bad = tmp_path / "bad_inputs"
    seed_sandbox.write_all(bad)
    scans = json.loads((bad / "scanned_documents.json").read_text())
    scans["documents"][0]["text"] = scans["documents"][0]["text"].replace("60,000.00", "6O,OOO.OO")
    (bad / "scanned_documents.json").write_text(json.dumps(scans))
    c = coordinator(bad, tmp_path)
    assert c.weekly_run() is CaseState.NEEDS_HUMAN
    assert "scanned documents need a human" in c.case.needs_human_reason


def test_a_scan_that_disagrees_with_the_record_raises_an_alert_and_stops_the_case(inputs, tmp_path):
    odd = tmp_path / "odd_inputs"
    seed_sandbox.write_all(odd)
    scans = json.loads((odd / "scanned_documents.json").read_text())
    scans["documents"][2]["text"] = scans["documents"][2]["text"].replace("Packages: 200", "Packages: 198")  # the bill of lading
    (odd / "scanned_documents.json").write_text(json.dumps(scans))
    c = coordinator(odd, tmp_path)
    assert c.weekly_run() is CaseState.NEEDS_HUMAN
    assert any(a["type"] == "DOCUMENT" and "package count" in " ".join(a["reasons"]) for a in c.alerts)


def test_the_document_agent_only_uses_its_own_tools(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    c.weekly_run()
    lines = [json.loads(l) for l in c.audit_path.read_text().splitlines()]
    mine = {l["tool"] for l in lines if l["agent"] == "document_agent"}
    assert mine == {"read_documents", "three_way_match"} and all(l["decision"] == "ALLOWED" for l in lines if l["agent"] == "document_agent")


# ------------------------------------------------------------------- ladder
def invoice(no="INV-1026"):
    return next(i for i in loader.invoices() if i.invoice_no == no)


def test_ladder_has_five_rungs_around_the_due_date():
    rungs = ca.ladder(invoice())
    assert [(r.offset_days, r.stage) for r in rungs] == [(-3, "gentle"), (0, "gentle"), (7, "firm"), (15, "firm"), (30, "escalation")]
    assert [r.scheduled_date.isoformat() for r in rungs] == ["2026-11-21", "2026-11-24", "2026-12-01", "2026-12-09", "2026-12-24"]


def test_next_rung_moves_forward_with_the_calendar():
    inv = invoice()
    assert ca.next_rung(inv, date(2026, 10, 19)).offset_days == -3
    assert ca.next_rung(inv, date(2026, 11, 22)).offset_days == 0
    assert ca.next_rung(inv, date(2026, 12, 2)).offset_days == 15
    assert ca.next_rung(inv, date(2027, 6, 1)).offset_days == 30  # past the ladder: stay on the last rung


@pytest.mark.parametrize("no,language,marker", [("INV-1026", "en", "Dear Oakline"), ("INV-1028", "ja", "御中"), ("INV-1029", "zh", "财务部")])
def test_drafts_use_the_buyers_language(no, language, marker):
    inv = invoice(no)
    assert ca.language_for(inv) == language
    assert marker in ca.draft_reminder(inv, ca.ladder(inv)[2])


def test_every_rung_in_every_language_passes_the_number_lock():
    for no in ("INV-1026", "INV-1028", "INV-1029"):
        inv = invoice(no)
        for rung in ca.ladder(inv):
            text = ca.draft_reminder(inv, rung)
            locked = {"amount": float(inv.amount.amount), "days": rung.offset_days}
            assert number_check.check(text, locked).ok, (no, rung, text)
            assert "Synthetic demo data" in text


def test_firm_and_escalation_drafts_state_the_days_overdue():
    inv = invoice()
    assert "7 days overdue" in ca.draft_reminder(inv, ca.ladder(inv)[2])
    assert "30 days overdue" in ca.draft_reminder(inv, ca.ladder(inv)[4])


# ------------------------------------------------- schedule, approval and sending
def test_schedule_covers_every_open_invoice_with_real_dates(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    c.weekly_run()
    rows = c.collection_schedule()
    assert {r["invoice_id"] for r in rows} == {i.invoice_no for i in c.open_invoices()} and len(rows) >= 10
    assert all(r["status"] == "scheduled" and r["stage"] in ("gentle", "firm", "escalation") for r in rows)
    assert {r["language"] for r in rows} == {"en", "ja", "zh"}


def test_nothing_is_sent_without_the_directors_otp(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    c.weekly_run()
    c.draft_reminder("INV-1026")
    with pytest.raises(ValueError):
        c.request_send_reminder("INV-1026")  # the accountant has not approved the first email yet
    c.approve_draft("INV-1026", "Lan")
    c.request_send_reminder("INV-1026")
    wrong = "000000" if c.otp.current_code() != "000000" else "111111"
    assert c.approve_send_reminder(wrong) == {"ok": False, "error": "invalid_code"}
    assert c.outbox == []
    assert c.approve_send_reminder(c.otp.current_code()) == {"ok": True, "error": None}
    assert len(c.outbox) == 1 and next(r for r in c.reminders)["status"] == "sent"
    lines = [json.loads(l) for l in c.audit_path.read_text().splitlines()]
    sends = [(l["decision"]) for l in lines if l["tool"] == "send_email"]
    assert sends == ["AWAITING_APPROVAL", "REJECTED", "APPROVED", "ALLOWED"]


def test_the_otp_for_one_email_cannot_send_another(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    c.weekly_run()
    c.draft_reminder("INV-1026")
    c.approve_draft("INV-1026")
    c.request_send_reminder("INV-1026")
    c._send_pending["payload"] = {**c._send_pending["payload"], "body_sha256": "f" * 64}  # the email text changed after approval was asked
    assert c.approve_send_reminder(c.otp.current_code()) == {"ok": False, "error": "payload_mismatch"}
    assert c.outbox == []


def test_a_second_email_to_the_same_buyer_skips_the_accountant_but_still_needs_otp(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    c.weekly_run()
    c.draft_reminder("INV-1026")
    c.approve_draft("INV-1026")
    c.request_send_reminder("INV-1026")
    c.approve_send_reminder(c.otp.current_code())
    second = c.draft_reminder("INV-1027")  # same buyer, Oakline
    assert second["first_for_buyer"] is False and second["status"] == "awaiting_approval"
    c.request_send_reminder("INV-1027")  # a fresh challenge: the first email's approval cannot be reused
    assert c.approve_send_reminder(c.otp.current_code()) == {"ok": True, "error": None}
    assert [r["status"] for r in c.reminders] == ["sent", "sent"] and len(c.outbox) == 2


def test_the_collections_agent_cannot_send_email():
    from config.tool_allowlist import tools_for

    assert "send_email" not in tools_for("collections_agent") and "send_email" in tools_for("coordinator")
