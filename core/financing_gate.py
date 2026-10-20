"""Server-side Data Reliability Gate in front of every financing action (fail closed).

Financing actions are: drafting a funding pack, approving/releasing it to a lender, Autopilot in
execute mode, and a lender recording APPROVE_FUNDING. Each one calls :func:`check` first.

When the gate is ON the action proceeds only if a server-held quality manifest
(``CASHBRIDGE_QUALITY_MANIFEST_PATH``) assesses as ``READY_FOR_DRAFT``: all required sources present,
fresh, reconciled, and every source independently verified. Verification never comes from the
manifest's own ``verified_by`` text. It comes from:

* PRODUCTION: signed attestations only (``CASHBRIDGE_SOURCE_ATTESTATIONS_PATH`` +
  ``CASHBRIDGE_ATTESTATION_KEY``; see core/source_attestation.py);
* DEMO: signed attestations, or the operator's legacy server-side list ``CASHBRIDGE_VERIFIED_SOURCE_IDS``.

Gate ON/OFF:
* PRODUCTION: always on. ``CASHBRIDGE_REQUIRE_DATA_GATE=0`` is ignored.
* DEMO: off unless ``CASHBRIDGE_REQUIRE_DATA_GATE=1`` (keeps the zero-setup SYNTHETIC demo runnable).

Any read/parse failure blocks the action. A pass is not a credit decision or proof of authenticity.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from config import runtime_mode
from core import source_attestation
from core.data_reliability import assess

MAX_MANIFEST_BYTES = 100_000
FINANCING_ACTIONS = ("prepare_pack", "approve_release", "autopilot_execute", "lender_approve_funding")


class GateBlocked(Exception):
    def __init__(self, detail: str, issues: Optional[list] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.issues = issues or []


def enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    source = os.environ if env is None else env
    if runtime_mode.is_production(source):
        return True
    return source.get("CASHBRIDGE_REQUIRE_DATA_GATE", "0").strip() == "1"


def _manifest(source: Mapping[str, str]) -> Dict[str, Any]:
    raw = source.get("CASHBRIDGE_QUALITY_MANIFEST_PATH", "").strip()
    if not raw:
        raise GateBlocked("A server-verified quality manifest is required before any financing action")
    try:
        path = Path(raw).resolve(strict=True)
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("manifest too large")
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GateBlocked("Quality attestation invalid or inaccessible") from error
    if not isinstance(manifest, dict):
        raise GateBlocked("Quality attestation invalid or inaccessible")
    return manifest


def _verified_ids(manifest: Mapping[str, Any], source: Mapping[str, str], today: Optional[date]) -> Dict[str, Any]:
    ids: set = set()
    rejected: list = []
    att_path = source.get("CASHBRIDGE_SOURCE_ATTESTATIONS_PATH", "").strip()
    if att_path:
        try:
            records = source_attestation.load(att_path)
            signed, rejected = source_attestation.verified_source_ids(
                manifest.get("sources") or [], records, source.get("CASHBRIDGE_ATTESTATION_KEY", ""), today)
        except source_attestation.AttestationError as error:
            raise GateBlocked("Source attestations invalid or inaccessible") from error
        ids |= signed
    if not runtime_mode.is_production(source):
        ids |= set(source.get("CASHBRIDGE_VERIFIED_SOURCE_IDS", "").split(",")) - {""}
    return {"ids": frozenset(ids), "rejected": rejected}


def evaluate(env: Optional[Mapping[str, str]] = None, today: Optional[date] = None) -> Dict[str, Any]:
    """Current gate state for display. Never raises; a failure reads as BLOCKED."""
    source = os.environ if env is None else env
    if not enabled(source):
        return {"enabled": False, "gate": "OFF_DEMO", "allows_financing": True,
                "notice": "DEMO mode: the data gate is off so the SYNTHETIC story runs. Production always enforces it."}
    try:
        manifest = _manifest(source)
        verified = _verified_ids(manifest, source, today)
        quality = assess(manifest, today=today, verified_ids=verified["ids"])
    except GateBlocked as blocked:
        return {"enabled": True, "gate": "BLOCKED_FOR_FINANCING", "allows_financing": False, "reason": blocked.detail, "issues": []}
    except (ValueError, KeyError, TypeError):
        return {"enabled": True, "gate": "BLOCKED_FOR_FINANCING", "allows_financing": False,
                "reason": "Quality attestation invalid or inaccessible", "issues": []}
    return {"enabled": True, "gate": quality["gate"], "allows_financing": quality["gate"] == "READY_FOR_DRAFT",
            "quality_index": quality["quality_index"], "dimensions": quality["dimensions"], "issues": quality["issues"],
            "rejected_attestations": verified["rejected"], "external_authenticity_verified": False}


def check(action: str, env: Optional[Mapping[str, str]] = None, today: Optional[date] = None) -> Dict[str, Any]:
    """Raise :class:`GateBlocked` unless ``action`` may proceed. Returns the gate state otherwise."""
    if action not in FINANCING_ACTIONS:
        raise GateBlocked(f"unknown financing action {action!r}")
    state = evaluate(env, today)
    if state["allows_financing"]:
        return state
    if state.get("reason"):
        raise GateBlocked(state["reason"])
    codes = sorted({i["code"] for i in state.get("issues", [])})
    raise GateBlocked("Financial action blocked by data reliability gate: " + ", ".join(codes), state.get("issues"))
