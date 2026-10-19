"""Load the SYNTHETIC sandbox inputs into typed models.

This is the only place that reads ``data/sandbox_inputs/``; the engines in ``core/``
stay free of file access.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from agents.buyer_risk_agent import BuyerRiskAgent
from config.settings import SANDBOX_INPUTS_DIR
from core.forecasting_engine import compute_ccc
from core.funding_evaluator import LenderCatalog
from schemas.document_schemas import (
    BankTxn,
    BillOfLading,
    CommercialInvoice,
    Currency,
    Email,
    Money,
    PurchaseOrder,
)
from schemas.forecast_schemas import (
    CCCMetrics,
    DepositPlan,
    ForecastInputs,
    LedgerSnapshot,
    OpenReceivable,
)


def read(name: str, directory: Path = SANDBOX_INPUTS_DIR) -> Dict[str, Any]:
    """Read one seed JSON file."""
    return json.loads((Path(directory) / name).read_text(encoding="utf-8"))


def _money(raw: Dict[str, str]) -> Money:
    return Money.from_amount(Decimal(raw["amount"]), Currency(raw["currency"]))


def _with_money(record: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in record.items() if k != "p_on_time"}
    out["amount"] = _money(record["amount"])
    return out


def company(directory: Path = SANDBOX_INPUTS_DIR) -> Dict[str, Any]:
    return read("company_profile.json", directory)


def contacts(directory: Path = SANDBOX_INPUTS_DIR) -> Dict[str, Any]:
    return read("contacts.json", directory)


def invoices(directory: Path = SANDBOX_INPUTS_DIR) -> List[CommercialInvoice]:
    return [CommercialInvoice(**_with_money(r)) for r in read("trade_documents.json", directory)["invoices"]]


def purchase_orders(directory: Path = SANDBOX_INPUTS_DIR) -> List[PurchaseOrder]:
    return [PurchaseOrder(**_with_money(r)) for r in read("trade_documents.json", directory)["purchase_orders"]]


def bills_of_lading(directory: Path = SANDBOX_INPUTS_DIR) -> List[BillOfLading]:
    return [BillOfLading(**r) for r in read("trade_documents.json", directory)["bills_of_lading"]]


def bank_txns(directory: Path = SANDBOX_INPUTS_DIR) -> List[BankTxn]:
    return [BankTxn(**_with_money(r)) for r in read("bank_statements.json", directory)["transactions"]]


def emails(directory: Path = SANDBOX_INPUTS_DIR) -> List[Email]:
    return [Email(**r) for r in read("emails_inbox.json", directory)["emails"]]


def scanned_documents(directory: Path = SANDBOX_INPUTS_DIR) -> List[Dict[str, Any]]:
    """Simulated OCR text of scanned documents."""
    return read("scanned_documents.json", directory)["documents"]


def lender_catalog(directory: Path = SANDBOX_INPUTS_DIR) -> LenderCatalog:
    raw = {k: v for k, v in read("lender_catalog.json", directory).items() if k in LenderCatalog.model_fields}
    return LenderCatalog(**raw)


def ledger_ccc(directory: Path = SANDBOX_INPUTS_DIR) -> CCCMetrics:
    """CCC computed by the engine from the seed ledger."""
    return compute_ccc(LedgerSnapshot(**company(directory)["ledger"]))


def on_time_probabilities(directory: Path = SANDBOX_INPUTS_DIR) -> Dict[str, float]:
    """On-time probability for every invoice, from the model fitted on the payment history."""
    agent = BuyerRiskAgent(read("payment_history.json", directory)["records"])
    return {inv.invoice_no: agent.p_on_time(inv) for inv in invoices(directory)}


def forecast_inputs(
    reconciled_invoice_nos: Iterable[str] = (),
    directory: Path = SANDBOX_INPUTS_DIR,
    p_on_time: Optional[Dict[str, float]] = None,
) -> ForecastInputs:
    """Build forecast inputs. Invoices already paid (reconciled) are left out.

    On-time probabilities come from the buyer risk model unless a map is passed in.
    """
    profile = company(directory)
    docs = read("trade_documents.json", directory)
    paid = set(reconciled_invoice_nos)
    start = date.fromisoformat(profile["as_of"])
    p_on_time = p_on_time if p_on_time is not None else on_time_probabilities(directory)
    receivables = [
        OpenReceivable(
            invoice_id=inv.invoice_no,
            buyer_id=inv.buyer_id,
            buyer_name=inv.buyer_name,
            market=inv.market,
            amount=inv.amount,
            due_date=inv.due_date,
            p_on_time=p_on_time.get(inv.invoice_no, 1.0),
        )
        for inv in invoices(directory)
        if inv.invoice_no not in paid
    ]
    deposits = []
    for item in docs["supplier_deposits"]:
        due = date.fromisoformat(item["due_date"])
        deposits.append(
            DepositPlan(
                ref=item["ref"],
                week=(due - start).days // 7 + 1,
                po_value_usd=Decimal(item["po_value_usd"]),
                pct=Decimal(item["pct"]),
                adjustable=item["adjustable"],
            )
        )
    return ForecastInputs(
        start_date=start,
        opening_cash_usd=Decimal(profile["opening_cash_usd"]),
        weekly_fixed_costs_usd=Decimal(profile["weekly_fixed_costs_usd"]),
        payroll_usd=Decimal(profile["payroll_usd"]),
        receivables=receivables,
        deposits=deposits,
    )


def billings(directory: Path = SANDBOX_INPUTS_DIR) -> List[tuple]:
    """(issue_date, usd_amount) for each invoice in the 12-month payment history."""
    out = []
    for record in read("payment_history.json", directory)["records"]:
        money = Money.from_amount(Decimal(record["amount"]), Currency(record["currency"]))
        out.append((date.fromisoformat(record["issue_date"]), money.to_usd()))
    return out
