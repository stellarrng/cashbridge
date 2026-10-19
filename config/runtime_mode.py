"""Deployment mode: DEMO (default) or PRODUCTION, and the fail-closed checks for PRODUCTION.

DEMO keeps the zero-setup judge experience: one-click demo accounts, the public demo OTP secret,
an ephemeral session secret if none is configured, and the reset / tamper demonstrations.

PRODUCTION refuses to start if any demo shortcut would still be active:
  * OTP_SECRET unset or equal to the public demo secret
  * CASHBRIDGE_SESSION_SECRET unset or shorter than 32 characters
  * no configured user accounts (CASHBRIDGE_USERS_FILE / CASHBRIDGE_USERS_JSON)
and it disables one-click demo login, demo reset and the tamper demonstrations.

This is a deployment guard for a SYNTHETIC MVP. It is not a production security certification.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Mapping, Optional

DEMO = "demo"
PRODUCTION = "production"


def mode(env: Optional[Mapping[str, str]] = None) -> str:
    source = os.environ if env is None else env
    value = source.get("CASHBRIDGE_ENV", DEMO).strip().lower()
    return PRODUCTION if value in {"prod", "production"} else DEMO


def is_production(env: Optional[Mapping[str, str]] = None) -> bool:
    return mode(env) == PRODUCTION


def is_serverless(env: Optional[Mapping[str, str]] = None) -> bool:
    """Vercel / AWS Lambda style runtimes where only /tmp is writable."""
    source = os.environ if env is None else env
    return bool(source.get("VERCEL") or source.get("AWS_LAMBDA_FUNCTION_NAME"))


def runtime_dir(base_dir: Path, env: Optional[Mapping[str, str]] = None) -> Path:
    """Writable folder for the live session (audit log, registry, packs)."""
    source = os.environ if env is None else env
    configured = source.get("CASHBRIDGE_RUNTIME_DIR", "").strip()
    if configured:
        return Path(configured)
    if is_serverless(source):
        return Path("/tmp/cashbridge/runtime")
    return base_dir / "data" / "runtime"


def production_problems(env: Optional[Mapping[str, str]] = None) -> List[str]:
    """Every reason PRODUCTION mode must refuse to start. Empty list means ready."""
    from config.settings import DEMO_OTP_SECRET

    source = os.environ if env is None else env
    problems: List[str] = []
    otp = source.get("OTP_SECRET", "").strip()
    if not otp:
        problems.append("OTP_SECRET is not set")
    elif otp == DEMO_OTP_SECRET:
        problems.append("OTP_SECRET is the public demo secret")
    if len(source.get("CASHBRIDGE_SESSION_SECRET", "").strip()) < 32:
        problems.append("CASHBRIDGE_SESSION_SECRET must be at least 32 characters")
    if not (source.get("CASHBRIDGE_USERS_FILE", "").strip() or source.get("CASHBRIDGE_USERS_JSON", "").strip()):
        problems.append("no user accounts configured (CASHBRIDGE_USERS_FILE or CASHBRIDGE_USERS_JSON)")
    return problems


class ProductionConfigError(RuntimeError):
    """Raised at start-up when PRODUCTION mode is requested with demo shortcuts still active."""


def assert_safe_to_start(env: Optional[Mapping[str, str]] = None) -> None:
    if is_production(env):
        problems = production_problems(env)
        if problems:
            raise ProductionConfigError("Refusing to start in PRODUCTION mode: " + "; ".join(problems))
