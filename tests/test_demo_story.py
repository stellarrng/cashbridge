"""The headless demo story, mock lender connector, anchors and minimal collections (Step 3.4)."""

import json
from datetime import date

import pytest

from agents.collections_agent import draft_reminder, invoice_in_text, parse_payment_promise
from api import lender_connector_mock
from data import loader
from scripts import run_demo_story
from scripts.anchor_head import anchor
from security.audit_log import AuditLog, verify_chain
from core.invoice_registry import InvoiceRegistry

EVIDENCE_FILES = ("sandbox_operation_logs.jsonl", "invoice_registry.json", "story_summary.md", "ANCHORS.md")


@pytest.fixture(scope="module")
def story(tmp_path_factory):
    evidence = tmp_path_factory.mktemp("evidence")
    outcomes = run_demo_story.run(evidence, log=lambda _text: None)
    return evidence, outcomes


def lines(evidence):
    return [json.loads(l) for l in (evidence / "sandbox_operation_logs.jsonl").read_text().splitlines()]


def test_all_eleven_steps_pass_in_order(story):
    _, outcomes = story
    assert [o.step for o in outcomes] == list(range(1, 12))


def test_every_evidence_file_is_written(story):
    evidence, _ = story
    for name in EVIDENCE_FILES:
        assert (evidence / name).stat().st_size > 0, name


def test_audit_log_has_every_tier_and_the_required_decisions(story):
    evidence, _ = story
    seen = {(l["tier"], l["decision"]) for l in lines(evidence)}
    for needed in (
        ("L0_READ", "ALLOWED"), ("L1_ANALYZE", "ALLOWED"), ("L2_INTERNAL_WRITE", "ALLOWED"),
        ("L2_INTERNAL_WRITE", "AWAITING_APPROVAL"), ("L3_EXTERNAL", "AWAITING_APPROVAL"),
        ("L3_EXTERNAL", "APPROVED"), ("L3_EXTERNAL", "ALLOWED"), ("L3_EXTERNAL", "REJECTED"),
        ("L3_EXTERNAL", "BLOCKED"), ("L4_MONEY_MOVEMENT", "BLOCKED"), ("L1_ANALYZE", "REJECTED"),
    ):
        assert needed in seen, needed
    ok, broken, checked = verify_chain(evidence / "sandbox_operation_logs.jsonl")
    assert ok and broken is None and checked == len(lines(evidence))


def test_registry_holds_inv_1030_and_verifies(story):
    evidence, _ = story
    registry = InvoiceRegistry(evidence / "invoice_registry.json")
    assert len(registry.blocks()) == 1 and registry.verify_chain() == (True, None)


def test_anchor_matches_the_chain_heads(story):
    evidence, _ = story
    anchors = (evidence / "ANCHORS.md").read_text()
    assert AuditLog(evidence / "sandbox_operation_logs.jsonl").head_hash() in anchors
    assert InvoiceRegistry(evidence / "invoice_registry.json").head_hash() in anchors


def test_a_rewritten_log_no_longer_matches_its_anchor(story, tmp_path):
    evidence, _ = story
    copy = tmp_path / "audit.jsonl"
    rows = (evidence / "sandbox_operation_logs.jsonl").read_text().splitlines()
    copy.write_text("\n".join(rows[:-1]) + "\n")  # drop the newest line: chain still valid
    assert verify_chain(copy)[0]
    assert AuditLog(copy).head_hash() not in (evidence / "ANCHORS.md").read_text()


def test_summary_mentions_every_outcome(story):
    evidence, outcomes = story
    summary = (evidence / "story_summary.md").read_text()
    assert "SYNTHETIC DEMO DATA" in summary
    for needle in ("INV-1021", "week 7", "17.1%", "ELIGIBLE", "FLAGGED", "BLOCKED", "DoubleFinancingBlocked",
                   "invalid_code", "2026-11-20", "verify_chain passed"):
        assert needle in summary, needle
    assert len(outcomes) == 11


def test_story_output_is_byte_identical_on_every_run(story, tmp_path):
    evidence, _ = story
    second = tmp_path / "second"
    run_demo_story.run(second, log=lambda _text: None)
    for name in EVIDENCE_FILES:
        assert (evidence / name).read_bytes() == (second / name).read_bytes(), name


def test_story_rerun_replaces_stale_evidence(story):
    evidence, _ = story
    before = len(lines(evidence))
    run_demo_story.run(evidence, log=lambda _text: None)
    assert len(lines(evidence)) == before


# ------------------------------------------------------------- connector
PAYLOAD = {"pack_id": "PACK-1", "invoice_no": "INV-1030", "option_id": "factoring_inv1030",
           "bundle_sha256": "a" * 64, "amount_usd": "48000.00"}


def test_connector_formats_a_labelled_mock_payload():
    out = lender_connector_mock.format_payload(PAYLOAD)
    assert out["mock"] and out["synthetic"] and out["schema"] == "cashbridge.funding_pack.v1"
    assert out["lender"] == "Partner Factor (FCI two-factor model, MOCK)"
    assert "webank" not in json.dumps(out).lower()


def test_connector_reference_is_deterministic_and_payload_specific():
    first = lender_connector_mock.submit(PAYLOAD)
    assert first.startswith("MOCK-") and first == lender_connector_mock.submit(PAYLOAD)
    assert first != lender_connector_mock.submit({**PAYLOAD, "amount_usd": "1.00"})


# ----------------------------------------------------------- anchor script
def test_anchor_refuses_a_broken_chain(story, tmp_path):
    evidence, _ = story
    broken = tmp_path / "evidence"
    broken.mkdir()
    rows = (evidence / "sandbox_operation_logs.jsonl").read_text().splitlines()
    del rows[3]
    (broken / "sandbox_operation_logs.jsonl").write_text("\n".join(rows) + "\n")
    with pytest.raises(SystemExit):
        anchor(broken)
    assert not (broken / "ANCHORS.md").exists()


def test_anchor_appends_a_row_per_run(story, tmp_path):
    evidence, _ = story
    copy = tmp_path / "e"
    copy.mkdir()
    for name in ("sandbox_operation_logs.jsonl", "invoice_registry.json"):
        (copy / name).write_bytes((evidence / name).read_bytes())
    anchor(copy)
    anchor(copy)
    rows = [l for l in (copy / "ANCHORS.md").read_text().splitlines() if l.startswith("| 20")]
    assert len(rows) == 2


# ----------------------------------------------------- minimal collections
def test_promise_parser_reads_dates_with_and_without_year():
    today = date(2026, 10, 19)
    one = parse_payment_promise("We will pay on Nov 20.", "INV-1026", "Oakline", today)
    assert one.promised_date == date(2026, 11, 20) and one.invoice_id == "INV-1026"
    assert parse_payment_promise("we will pay on 3rd December 2026", "I", "B", today) is None  # day-first not supported
    assert parse_payment_promise("We will pay on December 3rd, 2027", "I", "B", today).promised_date == date(2027, 12, 3)
    assert parse_payment_promise("We will pay on Jan 5", "I", "B", today).promised_date == date(2027, 1, 5)


@pytest.mark.parametrize("text", ["Thanks, received.", "We will pay soon.", "will pay on Feb 31", "will pay on Foo 12"])
def test_promise_parser_ignores_replies_without_a_valid_date(text):
    assert parse_payment_promise(text, "I", "B", date(2026, 10, 19)) is None


def test_invoice_in_text():
    assert invoice_in_text("Re: Payment reminder INV-1026") == "INV-1026"
    assert invoice_in_text("see inv 1021") == "INV-1021" and invoice_in_text("nothing here") is None


def test_reminder_only_states_the_amount_and_due_date():
    invoice = next(i for i in loader.invoices() if i.invoice_no == "INV-1026")
    text = draft_reminder(invoice)
    assert "USD 31,480.00" in text and "2026-11-24" in text and "Synthetic demo data" in text
