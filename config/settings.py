"""
Configuration and constants for CashBridge SME Finance Copilot.

All parameters, tolerances, permission tiers and deterministic FX rates live here.

NOTE ON "EXPECTED" VALUES
-------------------------
Earlier versions of this file carried a BENCHMARK_APR_OPTIONS table with
hard-coded `expected_apr` numbers that the engine then reproduced. That is
backwards: the engine must derive the numbers, and the test-suite golden values
must be computed independently (see tests/golden_values.py). This file now only
carries *product terms* (advance rates, fee rates, discount terms) — never
expected outputs.
"""

from pathlib import Path
from enum import Enum
import os

# ── Base directories ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SANDBOX_INPUTS_DIR = DATA_DIR / "sandbox_inputs"
EXECUTION_EVIDENCE_DIR = DATA_DIR / "execution_evidence"

AUDIT_HASH_REGISTRY_PATH = EXECUTION_EVIDENCE_DIR / "audit_hash_registry.json"
OPERATION_LOGS_PATH = EXECUTION_EVIDENCE_DIR / "sandbox_operation_logs.jsonl"

# ── Operational mode ─────────────────────────────────────────────────────────
# DEMO_MODE=true  -> fixed OTP, mock lender responses, synthetic data.
# DEMO_MODE=false -> OTPs are randomly generated; no lender integration exists,
#                    so external submission is refused rather than simulated.
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")
DEMO_OTP = "123456"

OTP_TTL_SECONDS = 300          # Session lifetime
OTP_MAX_ATTEMPTS = 3           # Attempts before a session is burned


# ── 5-tier permission state machine ──────────────────────────────────────────
class PermissionLevel(str, Enum):
    L0_READ = "L0_READ"                      # Read-only data ingestion
    L1_ANALYZE = "L1_ANALYZE"                # Calculations, forecasts, drafts
    L2_INTERNAL_WRITE = "L2_INTERNAL_WRITE"  # Ledger updates, period locks
    L3_EXTERNAL_OTP = "L3_EXTERNAL_OTP"      # External submission (OTP gated)
    L4_MONEY_MOVEMENT = "L4_MONEY_MOVEMENT"  # Funds transfer (HARD-BLOCKED)


# ── Deterministic FX rates (demo only — NOT a live rate feed) ────────────────
# These are frozen sandbox rates so demo output is reproducible. A production
# deployment must pull dated rates from the bank/accounting system and record
# the rate date alongside every converted figure.
FX_RATES_TO_USD = {
    "USD": 1.0,
    "JPY": 0.0067,
    "CNY": 0.14,
}
FX_RATE_DATE = "2026-10-16"          # Rate as-of date, carried into audit logs
USD_VND_RATE = 25_400.0              # Demo rate for VND settlement reporting
FX_CONVERSION_SPREAD_PCT = 0.35      # Typical bank spread on USD->VND, %

# ── Matching and reconciliation tolerances ───────────────────────────────────
# Tolerance is applied in the INVOICE'S OWN currency, not post-USD-conversion:
# a $0.01 USD tolerance on a JPY invoice silently permits a ~1.5 JPY mismatch.
PO_INVOICE_TOLERANCE_NATIVE = {
    "USD": 0.01,
    "JPY": 1.0,
    "CNY": 0.01,
}
PO_INVOICE_TOLERANCE_DEFAULT = 0.01

# Max intermediary / correspondent wire deduction accepted without review.
CORRESPONDENT_BANK_FEE_TOLERANCE_USD = 50.00

# Subset-sum guard: exhaustive search is 2^n. Above this, refuse and ask a human
# rather than silently truncating the search space.
SSMP_MAX_OPEN_INVOICES = 18

# ── Sandbox company baseline (synthetic) ─────────────────────────────────────
DEFAULT_COMPANY = {
    "name": "Pacific Timber & Garment Exports Ltd.",
    "registration_no": "VN-EXPORT-889211-HK",
    "tax_id": "VN9876543210",
    "base_currency": "USD",
    "dio_days": 38.0,
    "dso_days": 68.0,
    "dpo_days": 24.0,
    "ccc_days": 82.0,  # 38 + 68 - 24 = 82
    "opening_cash_week_1": 42000.0,
    "fixed_weekly_opex": 12500.0,
}

# ── Forecast parameters ──────────────────────────────────────────────────────
FORECAST_WEEKS = 13
DEFAULT_WEEK_3_SUPPLIER_DEPOSIT = 18000.0
DEFAULT_WEEK_6_SUPPLIER_DEPOSIT = 55000.0

# Minimum cash the business wants to keep on hand at all times. Financing sized
# to "get back to exactly zero" leaves no operating buffer, which is not a
# fundable plan — the peak need is measured against this floor.
MINIMUM_CASH_BUFFER_USD = 10_000.0

# ── Financing product terms (inputs, not expected outputs) ───────────────────
FINANCING_PRODUCTS = {
    "WEBANK_FACTORING": {
        "provider": "WeBank Partner Supply Chain Factoring",
        "option_type": "FACTORING",
        "advance_rate": 0.85,            # % of invoice face advanced
        "fee_rate_on_advance": 0.01125,  # Discount fee charged on the advance
        "flat_fee_usd": 110.0,           # Platform / documentation fee
        "fee_deducted_upfront": True,    # Fee netted off the advance at drawdown
        "reserve_released_on_payment": True,  # The 15% holdback returns later
        "is_mock_partner": True,         # No signed partner — simulated terms
    },
    "EARLY_PAYMENT_DISCOUNT": {
        "provider": "Customer Early-Payment Discount (2/10 Net 55)",
        "option_type": "EARLY_DISCOUNT",
        "discount_rate_pct": 2.0,        # d in "d/10 net N"
        "discount_period_days": 10,      # Pay-by day to earn the discount
        "net_terms_days": 55,            # Original due day
        "is_mock_partner": False,        # Depends only on the buyer agreeing
    },
    "UNSECURED_BRIDGE": {
        "provider": "Traditional Unsecured Working Capital Bridge",
        "option_type": "UNSECURED_BRIDGE",
        "nominal_apr_pct": 18.90,        # Lender's quoted rate
        "origination_fee_pct": 0.0,      # No fee quoted; shown as a disclosure
        "interest_paid_at_maturity": True,
        "is_mock_partner": True,
    },
}

DAYS_PER_YEAR = 365
