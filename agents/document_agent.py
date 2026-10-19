"""Document agent: reads scanned documents into typed fields, each with a confidence.

The scans here are simulated OCR text. The agent finds each labelled field, notes the page it was
on and scores its confidence:

  0.97  label found and the value parsed cleanly
  0.60  value only parsed after fixing look-alike characters (O for 0, l for 1, S for 5, B for 8)
  0.30  label found but the value is unreadable
  0.00  label not found

Any required field below 0.85 means NEEDS_HUMAN: nothing is built from a guess. Only documents
with every field confident are turned into typed models and passed to the matching engine. A
model, when configured, may do the reading instead, but its values must appear in the document
text or the rule-based reading is used.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel

from agents.llm_client import LlmClient
from config.settings import EXTRACTION_CONFIDENCE_THRESHOLD
from schemas.document_schemas import (
    BillOfLading,
    CommercialInvoice,
    Currency,
    ExtractedField,
    Money,
    PurchaseOrder,
)

CLEAN, REPAIRED, UNREADABLE, MISSING = 0.97, 0.60, 0.30, 0.0
_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})
_PAGE = re.compile(r"^--- page (\d+) ---$")

# (field, printed label, kind)
SPECS: Dict[str, List[Tuple[str, str, str]]] = {
    "invoice": [
        ("invoice_no", "Invoice No", "text"), ("po_number", "PO Number", "text"), ("seller_tax_id", "Seller Tax ID", "digits"),
        ("buyer_id", "Buyer ID", "text"), ("buyer_name", "Buyer", "text"), ("market", "Market", "text"),
        ("currency", "Currency", "currency"), ("amount", "Total Amount", "money"), ("quantity", "Quantity", "int"),
        ("package_count", "Packages", "int"), ("port_of_loading", "Port of Loading", "text"),
        ("port_of_discharge", "Port of Discharge", "text"), ("issue_date", "Issue Date", "date"), ("due_date", "Due Date", "date"),
    ],
    "purchase_order": [
        ("po_number", "PO Number", "text"), ("seller_tax_id", "Seller Tax ID", "digits"), ("buyer_id", "Buyer ID", "text"),
        ("buyer_name", "Buyer", "text"), ("currency", "Currency", "currency"), ("amount", "Total Amount", "money"),
        ("quantity", "Quantity", "int"), ("package_count", "Packages", "int"), ("port_of_loading", "Port of Loading", "text"),
        ("port_of_discharge", "Port of Discharge", "text"), ("issue_date", "Issue Date", "date"),
    ],
    "bill_of_lading": [
        ("bl_number", "B/L No", "text"), ("invoice_no", "Invoice No", "text"), ("seller_tax_id", "Seller Tax ID", "digits"),
        ("buyer_id", "Buyer ID", "text"), ("quantity", "Quantity", "int"), ("package_count", "Packages", "int"),
        ("port_of_loading", "Port of Loading", "text"), ("port_of_discharge", "Port of Discharge", "text"),
        ("shipped_on_board_date", "Shipped On Board", "date"),
    ],
}


class Extraction(BaseModel):
    """Everything read from one document."""

    doc_type: str
    fields: Dict[str, ExtractedField]
    min_confidence: float
    needs_human: bool
    reason: Optional[str] = None

    def value(self, name: str) -> Any:
        return self.fields[name].value

    def low_fields(self, threshold: float = EXTRACTION_CONFIDENCE_THRESHOLD) -> List[ExtractedField]:
        return [f for f in self.fields.values() if f.confidence < threshold]


def _parse(kind: str, raw: str) -> Tuple[Any, float, Optional[str]]:
    """Return (value, confidence, note)."""
    raw = raw.strip()
    if kind in ("text",):
        return raw, CLEAN, None
    if kind == "currency":
        code = raw.upper()
        return (code, CLEAN, None) if code in {c.value for c in Currency} else (None, UNREADABLE, f"unknown currency '{raw}'")
    if kind == "date":
        try:
            return date.fromisoformat(raw), CLEAN, None
        except ValueError:
            return None, UNREADABLE, f"'{raw}' is not a date"
    if kind in ("digits", "int", "money"):
        cleaned = re.sub(r"^(USD|JPY|CNY|VND)\s*", "", raw).replace(",", "")
        repaired = cleaned.translate(_LOOKALIKES)
        pattern = {"digits": r"\d+", "int": r"\d+", "money": r"\d+(?:\.\d+)?"}[kind]
        if re.fullmatch(pattern, cleaned):
            return _number(kind, cleaned), CLEAN, None
        if re.fullmatch(pattern, repaired):
            return _number(kind, repaired), REPAIRED, f"read '{raw}' as {repaired}"
        return None, UNREADABLE, f"'{raw}' is not a number"
    return raw, CLEAN, None


def _number(kind: str, text: str) -> Any:
    return text if kind == "digits" else int(text) if kind == "int" else Decimal(text)


def rule_extract(text: str, doc_type: str, threshold: float = EXTRACTION_CONFIDENCE_THRESHOLD) -> Extraction:
    """Read ``text`` with the labelled-line rules. Deterministic and offline."""
    if doc_type not in SPECS:
        raise ValueError(f"unknown document type '{doc_type}'")
    page, found = 1, {}
    for line in text.splitlines():
        marker = _PAGE.match(line.strip())
        if marker:
            page = int(marker.group(1))
            continue
        label, sep, value = line.partition(":")
        if sep and label.strip() not in found:
            found[label.strip()] = (value, page)
    fields: Dict[str, ExtractedField] = {}
    for name, label, kind in SPECS[doc_type]:
        if label not in found:
            fields[name] = ExtractedField(value=None, confidence=MISSING, page=None, reason=f"'{label}' not found")
            continue
        raw, field_page = found[label]
        value, confidence, note = _parse(kind, raw)
        fields[name] = ExtractedField(value=value, confidence=confidence, page=field_page, reason=note)
    return _summarise(doc_type, fields, threshold)


def _summarise(doc_type: str, fields: Dict[str, ExtractedField], threshold: float) -> Extraction:
    low = {name: f for name, f in fields.items() if f.confidence < threshold}
    smallest = min((f.confidence for f in fields.values()), default=0.0)
    reason = None
    if low:
        reason = "; ".join(f"{name} ({f.confidence:.2f}: {f.reason})" for name, f in low.items())
    return Extraction(doc_type=doc_type, fields=fields, min_confidence=smallest, needs_human=bool(low), reason=reason)


def _grounded(extraction: Extraction, text: str) -> bool:
    """A model's numeric values must literally appear in the document text (judged by the field's declared kind)."""
    digits_only = re.sub(r"[,\s]", "", text)
    for name, _, kind in SPECS[extraction.doc_type]:
        field = extraction.fields.get(name)
        if kind not in ("digits", "int", "money") or field is None or field.value is None:
            continue
        try:
            number = Decimal(str(field.value).replace(",", ""))
        except InvalidOperation:
            return False
        variants = {str(field.value).replace(",", ""), f"{number:.2f}", str(int(number)), format(number.normalize(), "f")}
        if not any(v in digits_only for v in variants):
            return False
    return True


def _typed(extraction: Extraction) -> Extraction:
    """Give values read by a model the same types the rules produce (Decimal, int, date)."""
    kinds = {name: kind for name, _, kind in SPECS[extraction.doc_type]}
    fields = {}
    for name, field in extraction.fields.items():
        if field.value is None or name not in kinds:
            fields[name] = field
            continue
        value, confidence, note = _parse(kinds[name], str(field.value))
        fields[name] = field.model_copy(update={"value": value, "confidence": min(field.confidence, confidence), "reason": note or field.reason})
    return extraction.model_copy(update={"fields": fields})


class DocumentAgent:
    """Reads scans and builds typed documents from confident fields only."""

    def __init__(self, llm: Optional[LlmClient] = None, threshold: float = EXTRACTION_CONFIDENCE_THRESHOLD) -> None:
        self.llm = llm
        self.threshold = threshold

    def extract(self, text: str, doc_type: str) -> Extraction:
        # Always local rule/OCR extraction. No uploaded document reaches a hosted
        # language model, even if LLM_API_KEY happens to be configured.
        return rule_extract(text, doc_type, self.threshold)

    # ------------------------------------------------------------- typed models
    def build_invoice(self, e: Extraction) -> Optional[CommercialInvoice]:
        if e.needs_human or e.doc_type != "invoice":
            return None
        v = e.value
        currency = Currency(v("currency"))
        return CommercialInvoice(
            invoice_no=v("invoice_no"), po_number=v("po_number"), seller_tax_id=v("seller_tax_id"), buyer_id=v("buyer_id"),
            buyer_name=v("buyer_name"), market=v("market"), currency=currency, amount=Money.from_amount(v("amount"), currency),
            quantity=v("quantity"), package_count=v("package_count"), port_of_loading=v("port_of_loading"),
            port_of_discharge=v("port_of_discharge"), issue_date=v("issue_date"), due_date=v("due_date"),
        )

    def build_po(self, e: Extraction) -> Optional[PurchaseOrder]:
        if e.needs_human or e.doc_type != "purchase_order":
            return None
        v = e.value
        currency = Currency(v("currency"))
        return PurchaseOrder(
            po_number=v("po_number"), seller_tax_id=v("seller_tax_id"), buyer_id=v("buyer_id"), buyer_name=v("buyer_name"),
            currency=currency, amount=Money.from_amount(v("amount"), currency), quantity=v("quantity"),
            package_count=v("package_count"), port_of_loading=v("port_of_loading"), port_of_discharge=v("port_of_discharge"),
            issue_date=v("issue_date"),
        )

    def build_bl(self, e: Extraction) -> Optional[BillOfLading]:
        if e.needs_human or e.doc_type != "bill_of_lading":
            return None
        v = e.value
        return BillOfLading(
            bl_number=v("bl_number"), invoice_no=v("invoice_no"), seller_tax_id=v("seller_tax_id"), buyer_id=v("buyer_id"),
            quantity=v("quantity"), package_count=v("package_count"), port_of_loading=v("port_of_loading"),
            port_of_discharge=v("port_of_discharge"), shipped_on_board_date=v("shipped_on_board_date"),
        )
