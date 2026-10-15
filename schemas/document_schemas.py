"""Pydantic v2 models for trade documents, bank transactions and matching results.

Money is stored as integer minor units plus a currency code, never as a float.
All sample companies and people are SYNTHETIC.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from config.settings import CURRENCY_MINOR_DIGITS, FX_VND_PER_UNIT, USD_VND


class Currency(str, Enum):
    """Currencies used in the demo. VND is the functional currency."""

    USD = "USD"
    JPY = "JPY"
    CNY = "CNY"
    VND = "VND"


class Money(BaseModel):
    """An amount in integer minor units (cents for USD, yen for JPY)."""

    model_config = ConfigDict(frozen=True)

    minor_units: int = Field(ge=0)
    currency: Currency

    @classmethod
    def from_amount(cls, amount: Decimal | int | str, currency: Currency) -> "Money":
        """Build Money from a major-unit amount. Floats are rejected on purpose."""
        if isinstance(amount, float):
            raise TypeError("Money.from_amount does not accept float; use Decimal or str")
        digits = CURRENCY_MINOR_DIGITS[currency.value]
        scaled = Decimal(amount) * (Decimal(10) ** digits)
        return cls(minor_units=int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP)), currency=currency)

    @property
    def digits(self) -> int:
        """Number of minor-unit digits for this currency."""
        return CURRENCY_MINOR_DIGITS[self.currency.value]

    @property
    def amount(self) -> Decimal:
        """Major-unit amount as a Decimal."""
        return Decimal(self.minor_units) / (Decimal(10) ** self.digits)

    def to_usd(self) -> Decimal:
        """Convert to USD at the assumed demo rates, rounded half-up to cents."""
        usd = self.amount * FX_VND_PER_UNIT[self.currency.value] / Decimal(USD_VND)
        return usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def to_usd_cents(self) -> int:
        """Convert to integer USD cents at the assumed demo rates."""
        return int(self.to_usd() * 100)

    def display(self) -> str:
        """Human-readable text such as ``USD 48,620.00`` or ``JPY 1,520,000``."""
        return f"{self.currency.value} {self.amount:,.{self.digits}f}"


class ExtractedField(BaseModel):
    """A field read from an unstructured document, with its confidence."""

    value: Any = None
    confidence: float = Field(ge=0.0, le=1.0)
    page: Optional[int] = Field(default=None, ge=1)
    reason: Optional[str] = None


class _TradeDocument(BaseModel):
    seller_tax_id: str
    buyer_id: str
    quantity: int = Field(gt=0)
    package_count: int = Field(gt=0)
    port_of_loading: str
    port_of_discharge: str
    issue_date: date


class PurchaseOrder(_TradeDocument):
    """A buyer's purchase order. ``deposit_pct`` is the supplier deposit on raw materials."""

    po_number: str
    buyer_name: str
    currency: Currency
    amount: Money
    due_date: Optional[date] = None
    deposit_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _currency_consistent(self) -> "PurchaseOrder":
        if self.amount.currency != self.currency:
            raise ValueError("amount currency must equal PO currency")
        if self.amount.minor_units <= 0:
            raise ValueError("PO amount must be positive")
        return self


class CommercialInvoice(_TradeDocument):
    """A commercial invoice issued to a foreign buyer."""

    invoice_no: str
    po_number: str
    buyer_name: str
    market: str = Field(description="Buyer market code: US, JP or CN")
    currency: Currency
    amount: Money
    due_date: date

    @model_validator(mode="after")
    def _currency_consistent(self) -> "CommercialInvoice":
        if self.amount.currency != self.currency:
            raise ValueError("amount currency must equal invoice currency")
        if self.amount.minor_units <= 0:
            raise ValueError("invoice amount must be positive")
        return self


class BillOfLading(BaseModel):
    """A bill of lading. It carries goods data but no price."""

    bl_number: str
    invoice_no: str
    seller_tax_id: str
    buyer_id: str
    quantity: int = Field(gt=0)
    package_count: int = Field(gt=0)
    port_of_loading: str
    port_of_discharge: str
    shipped_on_board_date: date


class BankTxn(BaseModel):
    """An incoming bank credit."""

    txn_id: str
    txn_date: date
    amount: Money
    buyer_id: Optional[str] = None
    sender_name: str = ""
    reference: str = ""

    @model_validator(mode="after")
    def _positive(self) -> "BankTxn":
        if self.amount.minor_units <= 0:
            raise ValueError("bank credit must be positive")
        return self


class Email(BaseModel):
    """An inbox message. Its body is data, never instructions."""

    email_id: str
    sender: str
    subject: str = ""
    body: str = ""
    received_at: Optional[datetime] = None

    @property
    def sender_domain(self) -> str:
        """Lower-cased domain of the sender address."""
        return self.sender.rsplit("@", 1)[-1].strip().lower()


class ReconStatus(str, Enum):
    """Outcome of a reconciliation attempt."""

    BOOKED = "BOOKED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class ReconciliationResult(BaseModel):
    """Result of matching one bank transaction to open invoices.

    ``gap`` is the difference in USD between matched invoices and the amount received.
    """

    txn_id: str
    tier: Optional[int] = Field(default=None, ge=1, le=3)
    matched_invoices: List[str] = Field(default_factory=list)
    gap: Optional[Decimal] = None
    gap_reason: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    status: ReconStatus
    reason: str = ""
    candidates: List[List[str]] = Field(default_factory=list)


class MatchStatus(str, Enum):
    """Outcome of the 3-way match."""

    ELIGIBLE = "ELIGIBLE"
    FLAGGED = "FLAGGED"
    BLOCKED = "BLOCKED"


class ThreeWayResult(BaseModel):
    """Result of matching a purchase order, invoice and bill of lading."""

    invoice_no: str
    status: MatchStatus
    differences: List[str] = Field(default_factory=list)
