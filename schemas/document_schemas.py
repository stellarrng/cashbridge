"""
Pydantic v2 models for trade documents, bank transactions, and 3-way matching.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import date


class Currency(str, Enum):
    USD = "USD"
    JPY = "JPY"
    CNY = "CNY"


class MatchStatus(str, Enum):
    UNMATCHED = "UNMATCHED"
    PARTIAL = "PARTIAL"
    VERIFIED_3WAY = "VERIFIED_3WAY"
    DISCREPANCY_FLAGGED = "DISCREPANCY_FLAGGED"
    RECONCILED = "RECONCILED"
    FINANCED = "FINANCED"


class PurchaseOrderItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float


class PurchaseOrder(BaseModel):
    po_number: str = Field(..., description="Unique Purchase Order identifier")
    buyer_name: str
    buyer_tax_id: str
    issue_date: date
    currency: Currency
    amount: float = Field(gt=0, description="Total PO value in foreign currency")
    items: List[PurchaseOrderItem] = Field(default_factory=list)
    payment_terms: str = "Net 60"
    status: str = "OPEN"


class BillOfLading(BaseModel):
    bl_number: str = Field(..., description="Bill of Lading tracking number")
    carrier: str
    vessel_name: str
    voyage_number: str
    port_of_loading: str
    port_of_discharge: str
    shipped_on_board_date: date
    container_ids: List[str] = Field(default_factory=list)
    goods_description: str
    gross_weight_kg: float


class InvoiceLineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class CommercialInvoice(BaseModel):
    invoice_id: str = Field(..., description="Unique Commercial Invoice ID e.g. INV-2026-101")
    po_reference: str
    buyer_name: str
    buyer_tax_id: str
    issue_date: date
    due_date: date
    due_week: int = Field(default=9, ge=1, le=13, description="Projected week of settlement in 13-week model")
    currency: Currency
    amount: float = Field(gt=0)
    usd_amount: float = Field(gt=0, description="Amount converted to USD via locked deterministic rate")
    items: List[InvoiceLineItem] = Field(default_factory=list)
    match_status: MatchStatus = MatchStatus.UNMATCHED
    document_bundle_sha256: Optional[str] = None
    is_pledged_for_financing: bool = False
    financing_partner: Optional[str] = None


class BankTxn(BaseModel):
    txn_id: str = Field(..., description="Wire transfer identifier e.g. TXN-9901")
    txn_date: date
    amount: float = Field(gt=0, description="Gross credit to company bank account")
    currency: Currency
    usd_amount: float
    sender_name: str
    sender_account_masked: str
    sender_swift_masked: str
    reference_memo: str
    reconciled: bool = False
    matched_invoice_ids: List[str] = Field(default_factory=list)
    intermediary_fee_variance_usd: float = 0.0


class TradeBundle(BaseModel):
    bundle_id: str
    invoice_id: str
    po: Optional[PurchaseOrder] = None
    bl: Optional[BillOfLading] = None
    invoice: CommercialInvoice
    match_confidence: float = 0.0
    status: MatchStatus = MatchStatus.UNMATCHED
    discrepancy_reasons: List[str] = Field(default_factory=list)
    bundle_sha256: Optional[str] = None


class SubsetSumMatchResult(BaseModel):
    txn_id: str
    incoming_wire_amount: float
    matched_invoice_ids: List[str]
    matched_invoices_gross_usd: float
    intermediary_bank_fee_variance_usd: float
    is_valid_match: bool
    reconciliation_status: str
    period_lock_hash: Optional[str] = None
