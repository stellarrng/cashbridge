"""CashBridge configuration constants (instructions.md section 2.2).

All company data in this project is SYNTHETIC. Secrets are read from the
environment or a local ``.env`` file only; nothing secret is stored in code.
"""

from __future__ import annotations

import os
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional at runtime
    load_dotenv = None
if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------- paths
DATA_DIR = BASE_DIR / "data"
SANDBOX_INPUTS_DIR = DATA_DIR / "sandbox_inputs"
EXECUTION_EVIDENCE_DIR = DATA_DIR / "execution_evidence"
AUDIT_LOG_PATH = EXECUTION_EVIDENCE_DIR / "sandbox_operation_logs.jsonl"
INVOICE_REGISTRY_PATH = EXECUTION_EVIDENCE_DIR / "invoice_registry.json"
CASES_DIR = DATA_DIR / "cases"
# Live UI session state. Kept apart from the committed evidence so clicking Reset never touches it.
# On serverless hosts (Vercel) only /tmp is writable, so the folder moves there automatically.
from config.runtime_mode import runtime_dir as _runtime_dir  # noqa: E402

RUNTIME_DIR = _runtime_dir(BASE_DIR)

SYNTHETIC_LABEL = "SYNTHETIC DEMO DATA"
COMPANY_NAME = "Binh Duong Timberworks Co., Ltd. (SYNTHETIC)"
PARTNER_FACTOR_NAME = "Partner Factor (FCI two-factor model, MOCK)"

# ------------------------------------------------- FX (assumed demo rates)
# VND per one unit of currency. Labelled "assumed demo rates" wherever shown.
USD_VND = 26_000
JPY_VND = 175
CNY_VND = 3_650
FX_VND_PER_UNIT: Mapping[str, Decimal] = {
    "USD": Decimal(USD_VND),
    "JPY": Decimal(JPY_VND),
    "CNY": Decimal(CNY_VND),
    "VND": Decimal(1),
}
CURRENCY_MINOR_DIGITS: Mapping[str, int] = {"USD": 2, "JPY": 0, "CNY": 2, "VND": 0}
FX_NOTE = "Assumed demo rate USD/VND 26,000"

# ------------------------------------------------------------ tolerances
INTERMEDIARY_FEE_TOLERANCE_USD = Decimal("50")  # per incoming wire
THREE_WAY_AMOUNT_TOLERANCE = Decimal("0.01")  # in invoice currency
MAX_SUBSET_SIZE = 6
EXTRACTION_CONFIDENCE_THRESHOLD = 0.85

# ------------------------------------------------------------ forecasting
FORECAST_WEEKS = 13
MIN_CASH_BUFFER_USD = Decimal("10000")  # below this: at_risk; below 0: shortfall
LATE_PAYMENT_DELAY_WEEKS = 4  # late remainder arrives in due week + 4
FX_STRESS_PCT = Decimal("2")
# Hypothetical tariff used only by the "tariff shared %" what-if control.
# It is a scenario assumption, not a statement about any current tariff rate.
SCENARIO_TARIFF_RATE_PCT = Decimal("10")
CONCENTRATION_ALERT_PCT = Decimal("40")

# CCC calibration targets. The seed data is tuned towards these and tests check
# the engine lands near them; the engine itself never reads this constant.
CCC_TARGET_DAYS = {"dio": 35, "dso": 75, "dpo": 28, "ccc": 82}

# --------------------------------------------------------------- security
OTP_VALIDITY_SECONDS = 120
DEMO_OTP_SECRET = "JBSWY3DPEHPK3PXP"  # public demo secret, printed in the README
OTP_SECRET = os.getenv("OTP_SECRET", "").strip() or DEMO_OTP_SECRET

# -------------------------------------------------------------------- LLM
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_TIMEOUT_SECONDS = 8


def is_demo_mode(env: Optional[Mapping[str, str]] = None) -> bool:
    """Return True when no LLM API key is configured (offline deterministic mode)."""
    source = os.environ if env is None else env
    return not source.get("LLM_API_KEY", "").strip()


DEMO_MODE = is_demo_mode()


class Tier(str, Enum):
    """The 5-tier permission model (instructions.md section 3, Rule 2)."""

    L0_READ = "L0_READ"
    L1_ANALYZE = "L1_ANALYZE"
    L2_INTERNAL_WRITE = "L2_INTERNAL_WRITE"
    L3_EXTERNAL = "L3_EXTERNAL"
    L4_MONEY_MOVEMENT = "L4_MONEY_MOVEMENT"

    @property
    def rank(self) -> int:
        """Numeric order of the tier (L0 = 0 ... L4 = 4)."""
        return int(self.value[1])
