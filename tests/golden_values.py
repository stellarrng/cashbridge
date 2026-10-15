"""
Independently derived expected values.

The point of this file is that it does NOT import anything from `core/`. Every
figure below is written out as explicit arithmetic from the product terms, so
a test comparing engine output against it is a real check rather than the
engine agreeing with itself.

This replaces the previous arrangement, where `config/settings.py` carried an
`expected_apr` for each product and `funding_evaluator.py` contained

    if invoice_id == "INV-2026-103":
        net_advance_a = 55250.00
        total_fee_a   = 731.25

so that the output matched the spec. That is not a passing test; that is a
copy. (The spec figure was wrong in any case: 55,250 x 1.125% = 621.5625,
which plus the 110 flat fee is 731.5625, not 731.25.)

Anyone checking this submission can recompute every number here with a
calculator from the stated terms.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Reference invoice
# ─────────────────────────────────────────────────────────────────────────────
INVOICE_ID = "INV-2026-103"
INVOICE_FACE_USD = 65_000.00
DAYS_UNTIL_DUE = 45

# ─────────────────────────────────────────────────────────────────────────────
# 13-week cash flow, worked out week by week
#   opening 42,000 | weekly opex 12,500
#   AR: W2 20,000 | W4 30,000 | W5 24,650 | W9 65,000 | W11 42,000
#   supplier deposits: W3 18,000 | W6 55,000
# ─────────────────────────────────────────────────────────────────────────────
EXPECTED_CLOSING_CASH = {
    1:   42_000 - 12_500,                               #  29,500
    2:   29_500 + 20_000 - 12_500,                      #  37,000
    3:   37_000 - 12_500 - 18_000,                      #   6,500
    4:    6_500 + 30_000 - 12_500,                      #  24,000
    5:   24_000 + 24_650 - 12_500,                      #  36,150
    6:   36_150 - 12_500 - 55_000,                      # -31,350
    7:  -31_350 - 12_500,                               # -43,850
    8:  -43_850 - 12_500,                               # -56,350
    9:  -56_350 + 65_000 - 12_500,                      #  -3,850
    10:  -3_850 - 12_500,                               # -16,350
    11: -16_350 + 42_000 - 12_500,                      #  13,150
    12:  13_150 - 12_500,                               #     650
    13:     650 - 12_500,                               # -11,850
}

# Week 6 is the FIRST week below zero. Week 8 is the trough. The previous
# README, docstrings and demo narrative all treated week 6 as the number that
# sizes the facility, which understates the need by $25,000.
EXPECTED_FIRST_SHORTFALL_WEEK = 6
EXPECTED_TROUGH_WEEK = 8
EXPECTED_TROUGH_BALANCE = -56_350.00
EXPECTED_WEEKS_IN_DEFICIT = [6, 7, 8, 9, 10, 13]
EXPECTED_ENDS_IN_DEFICIT = True

# Peak need = the largest weekly gap below the operating buffer, because a
# retained injection lifts every subsequent week equally.
MINIMUM_BUFFER = 10_000.00
EXPECTED_PEAK_FUNDING_NEED = 10_000 - (-56_350)          # 66,350.00
EXPECTED_PEAK_DEFICIT_NO_BUFFER = 56_350.00

# ─────────────────────────────────────────────────────────────────────────────
# Option A — factoring: 85% advance, 1.125% on the advance, $110 flat,
#                       fee deducted at drawdown
# ─────────────────────────────────────────────────────────────────────────────
FACTORING_GROSS_ADVANCE = 65_000.00 * 0.85               # 55,250.00
FACTORING_RESERVE = 65_000.00 - 55_250.00                #  9,750.00
FACTORING_TOTAL_FEE = round(55_250.00 * 0.01125 + 110.00, 2)   # 731.56
FACTORING_CASH_IN_HAND = round(55_250.00 - 731.56, 2)          # 54,518.44
FACTORING_SIMPLE_COST = round((731.56 / 54_518.44) * (365 / 45) * 100, 2)   # 10.88
# Effective APR: the business receives 54,518.44 on day 0 and, at day 45, gives
# up the 65,000 invoice while the 9,750 reserve comes back — a net obligation
# of 55,250. Annualised with compounding, actual/365:
#     (55,250 / 54,518.44) ^ (365/45) - 1
FACTORING_EFFECTIVE_APR = round(((55_250.00 / 54_518.44) ** (365 / 45) - 1) * 100, 2)  # 11.42

# ─────────────────────────────────────────────────────────────────────────────
# Option B — early payment discount, terms 2/10 net 55
#   acceleration = 55 - 10 = 45 days (derived from the terms, not from
#   whatever happens to be left on the invoice)
# ─────────────────────────────────────────────────────────────────────────────
DISCOUNT_DAYS_ACCELERATED = 55 - 10                      # 45
DISCOUNT_COST = round(65_000.00 * 0.02, 2)               # 1,300.00
DISCOUNT_CASH_IN_HAND = 65_000.00 - 1_300.00             # 63,700.00
DISCOUNT_SIMPLE_COST = round((1_300.00 / 63_700.00) * (365 / 45) * 100, 2)   # 16.55
# Effective: 63,700 received on day 0, 65,000 forgone on day 45.
DISCOUNT_EFFECTIVE_APR = round(((65_000.00 / 63_700.00) ** (365 / 45) - 1) * 100, 2)   # 17.81

# ─────────────────────────────────────────────────────────────────────────────
# Option C — unsecured bridge at a quoted 18.90%, simple interest settled at
#            maturity, no origination fee. Sized to the cash need.
# ─────────────────────────────────────────────────────────────────────────────
BRIDGE_NOMINAL_APR = 18.90
# Drawn amount is capped at the invoice face value in the engine.
BRIDGE_DRAWN = 65_000.00
BRIDGE_INTEREST = round(65_000.00 * 0.189 * (45 / 365), 2)      # 1,514.59
# With no fee and interest at maturity, the SIMPLE annualised cost must equal
# the quoted rate exactly. The EFFECTIVE rate is higher, because compounding.
BRIDGE_SIMPLE_COST = round((1_514.59 / 65_000.00) * (365 / 45) * 100, 2)  # 18.90
# Effective: 65,000 drawn on day 0, 66,514.59 repaid on day 45. Higher than the
# quoted 18.90% because the quote is a simple rate and does not compound.
BRIDGE_EFFECTIVE_APR = round(((66_514.59 / 65_000.00) ** (365 / 45) - 1) * 100, 2)  # 20.54

# ─────────────────────────────────────────────────────────────────────────────
# Coverage against the real need
# ─────────────────────────────────────────────────────────────────────────────
# Against the $66,350 peak need, no single option closes the gap:
#   factoring       54,518.44  -> short by 11,831.56
#   early discount  63,700.00  -> short by  2,650.00
#   bridge          65,000.00  -> short by  1,350.00
# This is the finding the old APR-only ranking hid: the "RECOMMENDED" option
# was the one that left the largest hole.
EXPECTED_NO_SINGLE_OPTION_COVERS = True
FACTORING_RESIDUAL_GAP = round(66_350.00 - 54_518.44, 2)
DISCOUNT_RESIDUAL_GAP = round(66_350.00 - 63_700.00, 2)
BRIDGE_RESIDUAL_GAP = round(66_350.00 - 65_000.00, 2)

# ─────────────────────────────────────────────────────────────────────────────
# CCC
# ─────────────────────────────────────────────────────────────────────────────
EXPECTED_CCC_DAYS = 38.0 + 68.0 - 24.0                   # 82.0


# ─────────────────────────────────────────────────────────────────────────────
# Facility structure
# ─────────────────────────────────────────────────────────────────────────────
# Only factoring takes security over the receivable, so only it belongs in the
# anti-double-financing registry. A buyer discount settles the invoice and a
# bridge is unsecured; registering either as a pledge would be wrong, and
# registering a two-facility package as one pledge (as the demo previously did)
# conflates two counterparties into one.
FACILITIES_THAT_PLEDGE_THE_RECEIVABLE = {"FACTORING"}

# Two facilities that both pledge the same receivable cannot be combined, and
# factoring cannot be combined with a buyer discount on the same invoice.
INCOMPATIBLE_PAIRS = [("FACTORING", "EARLY_DISCOUNT")]
