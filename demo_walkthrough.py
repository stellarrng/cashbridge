#!/usr/bin/env python3
"""
CashBridge end-to-end walkthrough — the loop that matters, start to finish.

    python demo_walkthrough.py

This exists because the README previously told reviewers to run
`python data/seed_sandbox.py` and `streamlit run ui/app.py`. Neither file
exists; `agents/`, `api/`, `ui/` and `tests/` were all empty directories. A
reviewer following those instructions saw an immediate crash.

EACH RUN GETS ITS OWN EVIDENCE DIRECTORY under `data/demo_runs/`. The first
version of this script wrote into the committed `data/execution_evidence/`,
so a second run raised DoubleFinancingError on INV-2026-103 — and the packaged
archive shipped with that registry already populated, so the demo failed on
first run from the ZIP. Nothing here reads or writes committed evidence, and
nothing is deleted to make room: a demo that wipes an operational audit trail
to start cleanly has replaced one bug with a worse one.

What runs here is the real deterministic core, on synthetic data:

    forecast the cash curve
      -> verify the documents behind a receivable
      -> compare financing options on one basis
      -> register the pledge
      -> gate the external submission behind a human OTP

Every figure printed is computed, not quoted. Nothing contacts a bank, a funder
or an LLM.
"""

from datetime import date

from config import runtime
from config.settings import PermissionLevel
from core.forecasting_engine import calculate_ccc, run_13_week_forecast
from core.matching_engine import run_3way_match
from core.funding_evaluator import evaluate_liquidity_options, summarise_comparison
from core.cryptographic_registry import (
    register_invoice,
    verify_chain_integrity,
    get_chain_head,
    DoubleFinancingError,
)
from schemas.document_schemas import (
    BillOfLading,
    CommercialInvoice,
    Currency,
    InvoiceLineItem,
    PurchaseOrder,
    PurchaseOrderItem,
    TradeBundle,
)
from security.otp_verifier import generate_otp_session, verify_otp
from security.permission_gatekeeper import (
    request_permission,
    verify_log_integrity,
    PermissionDeniedError,
    OTPRequiredError,
)
from config.settings import DEMO_OTP

LINE = "=" * 78


def header(n: int, title: str) -> None:
    print(f"\n{LINE}\n  STEP {n}: {title}\n{LINE}")


def money(x: float) -> str:
    return f"${x:,.2f}"


# ─────────────────────────────────────────────────────────────────────────────

def step_1_forecast():
    header(1, "ANTICIPATE — 13-week cash curve")

    ccc = calculate_ccc()
    print(f"Cash conversion cycle: {ccc.ccc_days:.0f} days")
    print(f"  {ccc.liquidity_drag_commentary}\n")

    f = run_13_week_forecast()
    print(f"{'Week':<14}{'Opening':>13}{'AR in':>13}{'Out':>13}{'Closing':>14}")
    for r in f.weekly_breakdown:
        out = r.fixed_opex + r.supplier_deposits
        flag = "  <-- below zero" if r.closing_cash < 0 else ""
        print(
            f"{r.week_label:<14}{money(r.opening_cash):>13}{money(r.ar_inflows):>13}"
            f"{money(out):>13}{money(r.closing_cash):>14}{flag}"
        )

    print(f"\nFirst week below zero : W{f.first_shortfall_week}")
    print(f"Trough                : W{f.lowest_cash_week} at {money(f.lowest_cash_balance)}")
    print(f"Weeks in deficit      : {f.weeks_in_deficit} ({f.deficit_duration_weeks} weeks)")
    print(f"Ends horizon negative : {f.ends_period_in_deficit}")
    print(f"Operating buffer      : {money(f.minimum_cash_buffer)}")
    print(f"PEAK FUNDING NEED     : {money(f.peak_funding_need_usd)} "
          f"(needed by W{f.funding_needed_by_week})")
    print(
        "\nNote: the facility is sized against the TROUGH plus the operating\n"
        "buffer, not against the first week that dips. Sizing to W"
        f"{f.first_shortfall_week} "
        f"({money(abs(f.weekly_breakdown[f.first_shortfall_week - 1].closing_cash))})\n"
        "would underfund the business by "
        f"{money(f.peak_funding_need_usd - abs(f.weekly_breakdown[f.first_shortfall_week - 1].closing_cash))}."
    )
    return f


def step_2_verify():
    header(2, "PROVE — document verification")

    invoice = CommercialInvoice(
        invoice_id="INV-2026-103",
        po_reference="PO-4471",
        buyer_name="Nordic Home Retail",
        buyer_tax_id="US-5566778899",
        issue_date=date(2026, 9, 1),
        due_date=date(2026, 11, 30),
        currency=Currency.USD,
        amount=65_000.0,
        usd_amount=65_000.0,
        items=[InvoiceLineItem(description="Oak dining chairs", quantity=1200,
                               unit_price=54.1666667, amount=65_000.0)],
    )
    po = PurchaseOrder(
        po_number="PO-4471", buyer_name="Nordic Home Retail",
        buyer_tax_id="US-5566778899", issue_date=date(2026, 8, 20),
        currency=Currency.USD, amount=65_000.0,
        items=[PurchaseOrderItem(description="Oak dining chairs", quantity=1200,
                                 unit_price=54.1666667, total=65_000.0)],
    )
    bl = BillOfLading(
        bl_number="MAEU-7781234", carrier="Maersk", vessel_name="MV Horizon",
        voyage_number="V-204E", port_of_loading="Haiphong",
        port_of_discharge="Long Beach", shipped_on_board_date=date(2026, 8, 28),
        container_ids=["MSCU1234567"], goods_description="Oak dining chairs",
        gross_weight_kg=18_420.5,
    )

    result = run_3way_match(
        TradeBundle(bundle_id="BND-103", invoice_id=invoice.invoice_id,
                    invoice=invoice, po=po, bl=bl)
    )
    print(f"Status     : {result.status.value}")
    print(f"Confidence : {result.match_confidence}")
    print(f"Bundle hash: {result.bundle_sha256}")
    print(f"\nChecks performed ({len(result.checks_performed)}):")
    for c in result.checks_performed:
        print(f"  [x] {c}")
    print("\nWhat this result does NOT establish:")
    for c in result.checks_not_performed:
        print(f"  [ ] {c}")
    return result


def step_3_compare(forecast, bundle):
    header(3, "COMPARE — financing options on one basis")

    need = forecast.peak_funding_need_usd
    options = evaluate_liquidity_options(
        invoice_id=bundle.invoice_id,
        invoice_amount_usd=bundle.invoice.amount,
        days_until_due=45,
        cash_need_usd=need,
    )

    print(f"Cash gap to close: {money(need)}\n")
    for o in options:
        mark = "OK " if o.covers_need else "GAP"
        print(f"[{mark}] #{o.rank} {o.provider}")
        print(f"       effective APR   : {o.effective_apr_pct:.2f}%"
              + (f"  (headline {o.nominal_quoted_rate_pct}%)"
                 if o.nominal_quoted_rate_pct is not None else ""))
        print(f"       simple cost p.a.: {o.annualized_simple_cost_pct:.2f}%")
        print(f"       gross advance   : {money(o.gross_advance_usd)}")
        print(f"       fees / cost     : {money(o.total_cost_usd)}")
        print(f"       CASH IN HAND    : {money(o.cash_in_hand_usd)}")
        if o.reserve_held_usd:
            print(f"       reserve held    : {money(o.reserve_held_usd)} "
                  f"(returned only when the buyer pays)")
        print(f"       term            : {o.days_financed} days")
        print(f"       coverage        : {o.coverage_pct:.1f}%"
              + (f"  short by {money(o.residual_gap_usd)}" if o.residual_gap_usd else ""))
        print(f"       cash flows      : " + ", ".join(
            f"d{f.day} {money(f.amount_usd)}" for f in o.cash_flows))
        print(f"       -> {o.recommendation_verdict}")
        if o.is_mock_partner:
            print(f"       (!) SIMULATED TERMS — no signed funding partner")
        print()

    s = summarise_comparison(options)
    print(f"Options evaluated      : {s['options_evaluated']}")
    print(f"Options closing the gap: {s['options_that_close_the_gap']}")
    print(f"Recommended            : {s['recommended_option_id']} at "
          f"{s['recommended_effective_apr_pct']}% effective "
          f"({s['recommended_simple_cost_pct']}% simple), "
          f"{s['recommended_facility_count']} facility/facilities")
    print(f"\n{s['rate_basis_note']}")
    print(f"\n{s['disclaimer']}")
    print(
        "\nNote: ranking by APR alone would have put the factoring line first.\n"
        "It has the lowest APR and the largest shortfall — cheap capital that\n"
        "does not close the gap does not prevent the shortfall."
    )
    return options[0]


def step_4_register(bundle, option):
    header(4, "REGISTER — pledge the receivable")

    # A package is several facilities with several counterparties. Only a
    # facility that takes SECURITY over the receivable belongs in the pledge
    # registry. The first version of this script registered the whole package
    # under one `financing_partner` string with the combined advance — which
    # recorded security that two of the three products never take, and
    # flattened two funders into one.
    secured = [f for f in option.facilities if f.pledges_receivable]
    unsecured = [f for f in option.facilities if not f.pledges_receivable]

    print(f"Selected option : {option.option_id}")
    print(f"Facilities      : {len(option.facilities)}")
    for f in option.facilities:
        kind = "SECURED on the invoice" if f.pledges_receivable else "not secured on the invoice"
        print(f"  - {f.provider}")
        print(f"      {money(f.cash_in_hand_usd)} | {kind}")

    if not secured:
        print("\nNo facility takes security over this receivable; "
              "nothing to register.")
        return None

    block = None
    for f in secured:
        block = register_invoice(
            invoice_id=bundle.invoice_id,
            document_bundle_sha256=bundle.bundle_sha256,
            financing_partner=f.provider,
            advance_amount_usd=f.cash_in_hand_usd,
        )
        print(f"\nBlock #{block['block_index']} written")
        print(f"  invoice     : {block['invoice_id']}")
        print(f"  partner     : {block['financing_partner']}")
        print(f"  advance     : {money(block['advance_amount_usd'])}")
        print(f"  prev hash   : {block['previous_block_hash'][:32]}...")
        print(f"  block hash  : {block['block_hash'][:32]}...")
        print(f"  scope       : {block['scope_note']}")

    for f in unsecured:
        print(f"\nNot registered: {f.provider}")
        print(f"  {f.option_type} takes no security over the invoice, so recording "
              f"it as a pledge\n  would assert a charge that does not exist.")

    print("\nSecond pledge of the same invoice:")
    try:
        register_invoice(bundle.invoice_id, bundle.bundle_sha256, "Another Funder", 50_000.0)
        print("  NOT BLOCKED — this is a defect")
    except DoubleFinancingError as exc:
        print(f"  BLOCKED: {exc}")

    print("\nSame documents resubmitted under a new invoice number:")
    try:
        register_invoice("INV-2026-103-A", bundle.bundle_sha256, "Another Funder", 50_000.0)
        print("  NOT BLOCKED — this is a defect")
    except DoubleFinancingError as exc:
        print(f"  BLOCKED: {exc}")

    integrity = verify_chain_integrity()
    print(f"\nChain integrity: valid={integrity['is_valid']}, "
          f"blocks={integrity['block_count']}")
    print(f"Head hash to anchor externally: {get_chain_head()}")
    print(
        "  A chain verified only against itself proves nothing to a party who\n"
        "  does not trust the operator. Anchor this hash with the funder."
    )
    return block


def step_5_approve(bundle, option, block):
    header(5, "APPROVE — human gate on the external action")

    print("Attempting submission with no approval:")
    try:
        request_permission(PermissionLevel.L3_EXTERNAL_OTP,
                           "SUBMIT_FUNDING_PACK", bundle.invoice_id)
        print("  SUBMITTED — this is a defect")
    except OTPRequiredError as exc:
        print(f"  REFUSED: {exc}")

    session = generate_otp_session("SUBMIT_FUNDING_PACK", bundle.invoice_id)
    print(f"\n{session['message']}")

    print("\nSubmitting a blank code:")
    print(f"  verified={verify_otp(session['session_id'], '')['verified']}")

    print("\nSubmitting the correct code:")
    outcome = verify_otp(session["session_id"], DEMO_OTP, actor="CFO_DEMO_USER")
    print(f"  verified={outcome['verified']}")

    result = request_permission(
        PermissionLevel.L3_EXTERNAL_OTP, "SUBMIT_FUNDING_PACK",
        bundle.invoice_id, otp_session_id=session["session_id"],
    )
    print(f"  gate status: {result['status']}")

    print("\nReusing the same approval for a second action:")
    try:
        request_permission(PermissionLevel.L3_EXTERNAL_OTP, "SUBMIT_FUNDING_PACK",
                           bundle.invoice_id, otp_session_id=session["session_id"])
        print("  ALLOWED — this is a defect")
    except OTPRequiredError:
        print("  REFUSED: approval was consumed on first use")

    print("\nAttempting to move money:")
    try:
        request_permission(PermissionLevel.L4_MONEY_MOVEMENT,
                           "TRANSFER_FUNDS", "ACC-889211")
        print("  ALLOWED — this is a defect")
    except PermissionDeniedError as exc:
        print(f"  HARD BLOCKED: {exc}")

    log = verify_log_integrity()
    print(f"\nAudit log: valid={log['is_valid']}, entries={log['entry_count']}")
    print(f"Head hash: {log['head_hash']}")


def main():
    run_dir = runtime.use_fresh_run_directory("demo")

    print(LINE)
    print("  CashBridge — deterministic core walkthrough")
    print("  ALL DATA IS SYNTHETIC. No bank, funder or LLM is contacted.")
    print("  Funding partner terms are SIMULATED; no agreement exists.")
    print(f"  Evidence for this run: {run_dir}")
    print("  (a fresh directory each run; committed evidence is never touched)")
    print(LINE)

    forecast = step_1_forecast()
    bundle = step_2_verify()
    option = step_3_compare(forecast, bundle)
    block = step_4_register(bundle, option)
    step_5_approve(bundle, option, block)

    print(f"\n{LINE}")
    print(f"  Walkthrough complete. Evidence written to:")
    print(f"    {run_dir}")
    print("  Run `pytest -q` for the automated checks behind it.")
    print(LINE)


if __name__ == "__main__":
    main()
