"""
Configuration and constants for CashBridge SME Finance Copilot.
All parameters, tolerances, permission tiers, and deterministic FX rates are centralized here.
"""

from pathlib import Path
from enum import Enum
import os

# Base Directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SANDBOX_INPUTS_DIR = DATA_DIR / "sandbox_inputs"
EXECUTION_EVIDENCE_DIR = DATA_DIR / "execution_evidence"

AUDIT_HASH_REGISTRY_PATH = EXECUTION_EVIDENCE_DIR / "audit_hash_registry.json"
OPERATION_LOGS_PATH = EXECUTION_EVIDENCE_DIR / "sandbox_operation_logs.jsonl"

# Operational Mode
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")
DEMO_OTP = "123456"

# 5-Tier Permission State Machine Constants
class PermissionLevel(str, Enum):
    L0_READ = "L0_READ"                     # Read-only data ingestion
    L1_ANALYZE = "L1_ANALYZE"               # Calculations, cash flow forecasts, draft messaging
    L2_INTERNAL_WRITE = "L2_INTERNAL_WRITE" # Ledger updates, high-confidence reconciliation, period locks
    L3_EXTERNAL_OTP = "L3_EXTERNAL_OTP"     # External loan pack submissions, debt collection emails (OTP gated)
    L4_MONEY_MOVEMENT = "L4_MONEY_MOVEMENT" # Banking funds transfer (HARD-BLOCKED, Zero Autonomy)

# Deterministic FX Rates (Locked to USD base)
FX_RATES_TO_USD = {
    "USD": 1.0,
    "JPY": 0.0067,
    "CNY": 0.14,
}

# Matching and Reconciliation Tolerances
PO_INVOICE_TOLERANCE_USD = 0.01          # 3-way match allowable variance
CORRESPONDENT_BANK_FEE_TOLERANCE_USD = 50.00  # Max intermediary wire deduction (SSMP epsilon)

# Sandbox Company Baseline
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

# Default Forecast Milestones
FORECAST_WEEKS = 13
DEFAULT_WEEK_3_SUPPLIER_DEPOSIT = 18000.0
DEFAULT_WEEK_6_SUPPLIER_DEPOSIT = 55000.0  # Timber & Textile deposits causing Week 6 deficit
EXPECTED_WEEK_6_DEFICIT_USD = -31350.0

# True APR Benchmark Presets for $65,000 / 45-day invoice
BENCHMARK_APR_OPTIONS = {
    "WEBANK_FACTORING": {
        "provider": "WeBank Partner Supply Chain Factoring",
        "advance_rate": 0.85,
        "fee_rate": 0.01125,
        "fixed_fee": 110.0,
        "expected_apr": 10.74,
    },
    "EARLY_PAYMENT_DISCOUNT": {
        "provider": "Customer Early-Payment Discount (2/10 Net 55)",
        "discount_rate": 0.02,
        "expected_apr": 16.55,
    },
    "UNSECURED_BRIDGE": {
        "provider": "Traditional Unsecured Working Capital Bridge",
        "fixed_apr": 18.90,
    },
}
