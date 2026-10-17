"""Number lock: the hallucination-prevention control for LLM-written text.

Every number in a draft must be one of the locked metrics for the case (formatting
aside: 48,000 / 48000 / 48k / USD 48,000.00 / 17.1%). Dates, invoice and document IDs and
``[source: ...]`` citations are not counted. Any other number rejects the draft, and the
caller falls back to a template.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, List, Mapping, Set

from pydantic import BaseModel

_IGNORED = [
    re.compile(r"\[source:[^\]]*\]", re.IGNORECASE),
    re.compile(r"\{metric:[^}]*\}"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b[A-Za-z]{1,6}-?\d{2,}(?:-\d+)*\b"),  # INV-1030, INV1021, PO-2214, fc-0007, TXN-0912
]
_NUMBER = re.compile(
    r"(?P<cur>USD|VND|JPY|CNY|\$)?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<suf>[kKmM](?![A-Za-z]))?\s?(?P<pct>%)?"
)


class NumberCheckResult(BaseModel):
    """Matches the UI contract ``pack.number_check`` shape."""

    ok: bool
    offending: List[str]


def _flatten(value: Any) -> Iterable[Decimal]:
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _flatten(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _flatten(item)
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float, Decimal)):
        yield Decimal(str(value))
        yield abs(Decimal(str(value)))  # a minus sign is formatting: "USD -187,485" is the locked -187,485.39


def _decimals_of(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def _value_of(match: re.Match) -> Decimal:
    value = Decimal(match.group("num").replace(",", ""))
    suffix = (match.group("suf") or "").lower()
    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000
    return value


def _is_locked(value: Decimal, places: int, locked: Set[Decimal]) -> bool:
    if value in locked:
        return True
    quantum = Decimal(1).scaleb(-places)
    return any(lock.quantize(quantum, rounding=ROUND_HALF_UP) == value for lock in locked)


def check(text: str, locked_metrics: Mapping[str, Any]) -> NumberCheckResult:
    """Reject ``text`` if it contains a number that is not in ``locked_metrics``."""
    locked = set(_flatten(locked_metrics))
    cleaned = text
    for pattern in _IGNORED:
        cleaned = pattern.sub(" ", cleaned)
    offending: List[str] = []
    for match in _NUMBER.finditer(cleaned):
        value = _value_of(match)
        if not _is_locked(value, _decimals_of(match.group("num")), locked):
            offending.append(match.group(0).strip())
    return NumberCheckResult(ok=not offending, offending=offending)
