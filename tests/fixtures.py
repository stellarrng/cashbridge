"""Synthetic fixtures shared by tests. All data is SYNTHETIC."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List

from schemas.document_schemas import (
    BankTxn,
    BillOfLading,
    CommercialInvoice,
    Currency,
    Money,
    PurchaseOrder,
)
from schemas.forecast_schemas import DepositPlan, ForecastInputs, OpenReceivable

SELLER_TAX_ID = "0312345678"
US_BUYER = "B-US-01"
JP_BUYER = "B-JP-01"


def usd(amount: str) -> Money:
    return Money.from_amount(Decimal(amount), Currency.USD)


def make_invoice(no: str, amount, buyer: str = US_BUYER, **overrides) -> CommercialInvoice:
    data = dict(
        invoice_no=no,
        po_number="PO-" + no[-4:],
        seller_tax_id=SELLER_TAX_ID,
        buyer_id=buyer,
        buyer_name="Oakline Home LLC (SYNTHETIC)",
        market="US",
        currency=Currency.USD,
        amount=amount if isinstance(amount, Money) else usd(amount),
        quantity=120,
        package_count=120,
        port_of_loading="Cat Lai",
        port_of_discharge="Los Angeles",
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 11, 30),
    )
    data.update(overrides)
    return CommercialInvoice(**data)


def open_invoices() -> List[CommercialInvoice]:
    """The six open invoices of the US buyer (instructions.md section 2.3)."""
    amounts = {
        "INV-1021": "15200",
        "INV-1022": "18455",
        "INV-1023": "22100",
        "INV-1024": "15000",
        "INV-1025": "9870",
        "INV-1026": "31480",
    }
    return [make_invoice(no, amt) for no, amt in amounts.items()]


def wire(amount: str = "48620", reference: str = "INV1021 1022 1024") -> BankTxn:
    return BankTxn(
        txn_id="TXN-0912",
        txn_date=date(2026, 10, 19),
        amount=usd(amount),
        buyer_id=US_BUYER,
        sender_name="Oakline Home LLC (SYNTHETIC)",
        reference=reference,
    )


def matching_po_bl(invoice: CommercialInvoice):
    po = PurchaseOrder(
        po_number=invoice.po_number,
        seller_tax_id=invoice.seller_tax_id,
        buyer_id=invoice.buyer_id,
        buyer_name=invoice.buyer_name,
        currency=invoice.currency,
        amount=invoice.amount,
        quantity=invoice.quantity,
        package_count=invoice.package_count,
        port_of_loading=invoice.port_of_loading,
        port_of_discharge=invoice.port_of_discharge,
        issue_date=date(2026, 9, 1),
    )
    bl = BillOfLading(
        bl_number="BL-" + invoice.invoice_no[-4:],
        invoice_no=invoice.invoice_no,
        seller_tax_id=invoice.seller_tax_id,
        buyer_id=invoice.buyer_id,
        quantity=invoice.quantity,
        package_count=invoice.package_count,
        port_of_loading=invoice.port_of_loading,
        port_of_discharge=invoice.port_of_discharge,
        shipped_on_board_date=date(2026, 10, 1),
    )
    return po, bl


def receivable(inv_id: str, amount: Money, due: date, p: float, market="US", buyer=US_BUYER) -> OpenReceivable:
    return OpenReceivable(
        invoice_id=inv_id,
        buyer_id=buyer,
        buyer_name="Buyer " + buyer,
        market=market,
        amount=amount,
        due_date=due,
        p_on_time=p,
    )


def base_forecast_inputs(**overrides) -> ForecastInputs:
    """Fixture whose first negative week is 7 with a shortfall of about USD 44.8k."""
    receivables = [
        receivable("INV-1021", usd("15200"), date(2026, 10, 22), 0.98),
        receivable("INV-1022", usd("18455"), date(2026, 10, 25), 0.98),
        receivable("INV-1024", usd("15000"), date(2026, 10, 27), 0.98),
        receivable("INV-1025", usd("9870"), date(2026, 11, 3), 0.95),
        receivable("INV-1023", usd("22100"), date(2026, 11, 10), 0.90),
        receivable("INV-1026", usd("31480"), date(2026, 11, 24), 0.42),
        receivable("INV-1030", usd("60000"), date(2026, 12, 18), 0.90, market="JP", buyer=JP_BUYER),
    ]
    deposits = [
        DepositPlan(ref="PO-2214", week=7, po_value_usd=Decimal("92000"), pct=Decimal("30"), adjustable=True)
    ]
    data = dict(
        start_date=date(2026, 10, 19),
        opening_cash_usd=Decimal("61200"),
        weekly_fixed_costs_usd=Decimal("20000"),
        payroll_usd=Decimal("15000"),
        receivables=receivables,
        deposits=deposits,
    )
    data.update(overrides)
    return ForecastInputs(**data)
