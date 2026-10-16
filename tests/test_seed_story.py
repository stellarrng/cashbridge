"""Run the engines on the seed data and check the story targets (Step 3.1)."""

import filecmp
import json
import sys
from datetime import date
from decimal import Decimal

import pytest

from config.settings import SANDBOX_INPUTS_DIR
from core.forecasting_engine import forecast_13w, simulate
from core.funding_evaluator import FundingRequest, rank_options
from core.matching_engine import reconcile, three_way_match
from data import loader, seed_sandbox
from schemas.document_schemas import MatchStatus, ReconStatus
from schemas.forecast_schemas import ScenarioParams
from security import injection_guard
from security.bec_fraud_detector import BecVerdict, analyze, is_valid_vn_tax_id


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    directory = tmp_path_factory.mktemp("seed")
    seed_sandbox.write_all(directory)
    return directory


@pytest.fixture(scope="module")
def story(seeded):
    """Reconcile every bank transaction in id order, as the Monday run does."""
    invoices = loader.invoices(seeded)
    paid, results = [], {}
    for txn in sorted(loader.bank_txns(seeded), key=lambda t: t.txn_id):
        result = reconcile(txn, [i for i in invoices if i.invoice_no not in paid])
        results[txn.txn_id] = result
        if result.status is ReconStatus.BOOKED:
            paid += result.matched_invoices
    return results, paid


# ------------------------------------------------------------- file hygiene
def test_seed_is_byte_identical_across_runs(seeded, tmp_path):
    seed_sandbox.write_all(tmp_path)
    for name in seed_sandbox.FILES:
        assert filecmp.cmp(seeded / name, tmp_path / name, shallow=False), name


def test_every_file_is_labelled_synthetic_and_names_say_so(seeded):
    for name in seed_sandbox.FILES:
        data = json.loads((seeded / name).read_text())
        assert data["_label"] == "SYNTHETIC DEMO DATA", name
    for invoice in loader.invoices(seeded):
        assert invoice.buyer_name.endswith("(SYNTHETIC)")
    assert loader.company(seeded)["name"].endswith("(SYNTHETIC)")


def test_committed_seed_matches_a_fresh_run(seeded):
    for name in seed_sandbox.FILES:
        assert filecmp.cmp(seeded / name, SANDBOX_INPUTS_DIR / name, shallow=False), f"run make seed ({name})"


def test_payment_history_covers_twelve_months(seeded):
    records = loader.read("payment_history.json", seeded)["records"]
    first = min(date.fromisoformat(r["issue_date"]) for r in records)
    assert (date(2026, 10, 19) - first).days >= 330
    assert len(records) >= 30


def test_seller_tax_id_is_valid_and_in_issuer_registry(seeded):
    profile = loader.company(seeded)
    assert is_valid_vn_tax_id(profile["seller_tax_id"], frozenset(profile["issuer_registry"]))


# ----------------------------------------------------------------------- CCC
def test_ccc_is_computed_from_the_ledger_near_targets(seeded):
    ccc = loader.ledger_ccc(seeded)
    assert 80 <= ccc.ccc <= 84
    assert abs(ccc.dio - 35) <= 2 and abs(ccc.dso - 75) <= 2 and abs(ccc.dpo - 28) <= 2
    assert ccc.ccc == round(ccc.dio + ccc.dso - ccc.dpo, 1)


# ------------------------------------------------------------ reconciliation
def test_story_wire_is_subset_sum_with_35_dollar_fee(story):
    result = story[0]["TXN-0912"]
    assert result.tier == 3 and result.status is ReconStatus.BOOKED
    assert set(result.matched_invoices) == {"INV-1021", "INV-1022", "INV-1024"}
    assert result.gap == Decimal("35") and result.gap_reason == "bank_fee"


def test_other_transactions_follow_the_ui_sample(story):
    results, _ = story
    assert results["TXN-0913"].tier == 1 and results["TXN-0913"].matched_invoices == ["INV-1025"]
    assert results["TXN-0914"].status is ReconStatus.NEEDS_HUMAN


# ------------------------------------------------------------------ forecast
def test_first_negative_week_is_seven_and_advance_covers_it(seeded, story):
    forecast = forecast_13w(loader.forecast_inputs(story[1], seeded))
    assert forecast.first_shortfall_week == 7
    assert Decimal(40000) <= forecast.shortfall_usd <= Decimal(47000)
    assert all(row.closing >= 0 for row in forecast.weeks[:6])
    catalog = loader.lender_catalog(seeded)
    request = FundingRequest(invoice_id="INV-1030", invoice_amount_usd=Decimal(60000), days_outstanding=60)
    advance = rank_options(request, catalog)[0].amount_usd
    assert advance >= forecast.shortfall_usd


def test_shortfall_drivers_are_the_deposit_and_the_late_us_invoice(seeded, story):
    forecast = forecast_13w(loader.forecast_inputs(story[1], seeded))
    refs = {item.source_ref: item.amount_usd for item in forecast.attribution}
    assert refs["doc:PO-2214"] == Decimal("27600.00")
    assert "inv:INV-1026" in refs
    assert sum(refs.values()) == forecast.shortfall_usd


def test_what_if_sliders_change_the_seed_forecast(seeded, story):
    inputs = loader.forecast_inputs(story[1], seeded)
    for params in (
        ScenarioParams(dso_change_days=15),
        ScenarioParams(deposit_pct=10),
        ScenarioParams(tariff_shared_pct=50),
        ScenarioParams(fx_change_pct=-5),
    ):
        out = simulate(inputs, params)
        assert out.delta.min_closing_after_usd != out.delta.min_closing_before_usd, params


# ------------------------------------------------------------------- funding
def test_liquidity_menu_matches_the_spec(seeded):
    due = next(i.due_date for i in loader.invoices(seeded) if i.invoice_no == "INV-1030")
    request = FundingRequest(
        invoice_id="INV-1030", invoice_amount_usd=Decimal(60000), days_outstanding=(due - date(2026, 10, 19)).days
    )
    menu = rank_options(request, loader.lender_catalog(seeded))
    assert [o.id for o in menu] == ["factoring_inv1030", "bridge_loan", "early_discount", "overdraft"]
    assert [round(o.apr_pct, 1) for o in menu[:3]] == pytest.approx([17.1, 18.2, 37.2], abs=0.1)
    assert menu[3].ineligible_reason == "No overdraft facility on file"


# -------------------------------------------------------------- verification
def _three_way(seeded, invoice_no):
    invoice = next(i for i in loader.invoices(seeded) if i.invoice_no == invoice_no)
    po = next(p for p in loader.purchase_orders(seeded) if p.po_number == invoice.po_number)
    bl = next(b for b in loader.bills_of_lading(seeded) if b.invoice_no == invoice_no)
    return three_way_match(po, invoice, bl)


def test_inv1030_is_eligible(seeded):
    assert _three_way(seeded, "INV-1030").status is MatchStatus.ELIGIBLE


def test_inv1027_is_flagged_for_two_missing_packages(seeded):
    result = _three_way(seeded, "INV-1027")
    assert result.status is MatchStatus.FLAGGED
    assert result.differences == ["B/L packages 118 vs invoice 120"]


def test_all_other_invoices_are_eligible(seeded):
    for invoice in loader.invoices(seeded):
        if invoice.invoice_no != "INV-1027":
            assert _three_way(seeded, invoice.invoice_no).status is MatchStatus.ELIGIBLE, invoice.invoice_no


# --------------------------------------------------------------------- inbox
def test_bec_email_is_blocked_and_normal_mail_is_clean(seeded):
    directory = loader.contacts(seeded)
    verdicts = {e.email_id: analyze(e, directory) for e in loader.emails(seeded)}
    assert verdicts["EML-003"].verdict is BecVerdict.BLOCKED
    assert "Lookalike domain of oakline-home.com" in verdicts["EML-003"].reasons
    for clean in ("EML-001", "EML-002", "EML-005"):
        assert verdicts[clean].verdict is BecVerdict.CLEAN, clean


def test_injection_email_is_flagged_as_data(seeded):
    email = next(e for e in loader.emails(seeded) if e.email_id == "EML-004")
    assert injection_guard.inspect(email.body).suspicious
    assert not injection_guard.inspect(next(e for e in loader.emails(seeded) if e.email_id == "EML-005").body).suspicious


def test_buyer_reply_is_present_for_the_collections_step(seeded):
    reply = next(e for e in loader.emails(seeded) if e.email_id == "EML-005")
    assert "will pay on Nov 20" in reply.body
