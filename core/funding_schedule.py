"""One funding timeline shared by the quote, the 13-week cash view and the settlement scenarios.

Before v9 the factoring quote charged interest from the quote date to the invoice due date while the
coverage chart showed the money arriving in the first shortfall week, and settlement subtracted the
whole repayment in the due week although the forecast expected part of the invoice later. A
``FundingSchedule`` fixes the dates once and everything else reads them:

* quote_date        when the terms were computed
* drawdown_date     when the money reaches the SME (for a pack released today: today)
* expected_settlement_date  invoice due date (factoring) or end of term (loan)
* interest          principal x rate x actual days financed / 365, half-up to the cent
* recourse          'recourse' (SME repays if the buyer never pays) or 'non_recourse' (the factor bears it)

Factoring cash, the textbook way (e.g. Klapper 2005, World Bank WP 3593): the buyer pays the factor;
the factor keeps advance + fee + interest to the day it is paid and remits the rest (the rebate) to the
SME. Relative to the base forecast, which already contains the invoice receipt, the SME therefore gets
+advance at drawdown and, at each expected receipt, loses the receipt and gains its share of the rebate:
net -share x (advance + fee + interest to that receipt date). Nothing is counted twice, and over a horizon
that contains every receipt the net effect equals minus the expected financing cost, to the cent.

"Annualised cost" here is CashBridge's internal convention (simple, Actual/365); it is not a legal APR
in every market.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

CENT = Decimal("0.01")
RECOURSE_TYPES = ("recourse", "non_recourse")
SCENARIOS = {"on_time": 0, "late_30": 30}
DEFAULT_RECOURSE_DAYS = 90  # buyer default is established this many days after the due date


def cents(x: Decimal) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FundingSchedule:
    option_id: str
    option_type: str  # "factoring" or "loan"
    quote_date: date
    drawdown_date: date
    expected_settlement_date: date
    principal_usd: Decimal          # advance (factoring) or loan amount
    rate_pa_pct: Decimal
    upfront_fee_usd: Decimal = Decimal(0)     # loan arrangement fee, deducted at drawdown
    settlement_fee_usd: Decimal = Decimal(0)  # factoring fee on the invoice, taken from the collection
    fee_basis: str = "invoice"
    invoice_usd: Optional[Decimal] = None
    recourse: Optional[str] = None
    recourse_days: int = DEFAULT_RECOURSE_DAYS
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.drawdown_date < self.quote_date:
            raise ValueError("drawdown cannot be before the quote")
        if self.expected_settlement_date < self.drawdown_date:
            raise ValueError("settlement cannot be before drawdown")
        if self.option_type == "factoring" and self.recourse not in RECOURSE_TYPES:
            raise ValueError("factoring needs a recourse type")

    # ------------------------------------------------------------------ money
    def days_to(self, day: date) -> int:
        return max(0, (day - self.drawdown_date).days)

    def interest_to(self, day: date) -> Decimal:
        return cents(self.principal_usd * self.rate_pa_pct / 100 * self.days_to(day) / 365)

    @property
    def days_financed(self) -> int:
        return self.days_to(self.expected_settlement_date)

    @property
    def interest_usd(self) -> Decimal:
        return self.interest_to(self.expected_settlement_date)

    @property
    def fees_usd(self) -> Decimal:
        return self.upfront_fee_usd + self.settlement_fee_usd

    @property
    def total_cost_usd(self) -> Decimal:
        return self.fees_usd + self.interest_usd

    @property
    def net_received_usd(self) -> Decimal:
        return self.principal_usd - self.upfront_fee_usd

    @property
    def reserve_usd(self) -> Optional[Decimal]:
        return None if self.invoice_usd is None else self.invoice_usd - self.principal_usd

    def annualised_cost_pct(self) -> float:
        if self.days_financed <= 0 or self.net_received_usd <= 0:
            raise ValueError("annualised cost needs a positive tenor and net funds")
        return float((self.total_cost_usd / self.net_received_usd * Decimal(365) / Decimal(self.days_financed) * 100)
                     .quantize(CENT, rounding=ROUND_HALF_UP))

    # ------------------------------------------------------------------ settlement scenarios
    def outcome(self, scenario: str) -> Dict[str, Any]:
        """What the SME pays and receives if the buyer pays on time, 30 days late, or never (factoring)."""
        if self.option_type == "loan":
            return {"scenario": scenario, "settlement_date": self.expected_settlement_date.isoformat(),
                    "repayment_usd": float(self.principal_usd + self.interest_usd), "total_cost_usd": float(self.total_cost_usd),
                    "credit_loss_borne_by": "SME (a loan is repaid whatever the buyer does)"}
        if scenario in SCENARIOS:
            paid = self.expected_settlement_date + timedelta(days=SCENARIOS[scenario])
            interest = self.interest_to(paid)
            cost = self.settlement_fee_usd + interest
            rebate = self.invoice_usd - self.principal_usd - cost
            return {"scenario": scenario, "buyer_pays_on": paid.isoformat(), "days_financed": self.days_to(paid),
                    "interest_usd": float(interest), "total_cost_usd": float(cost), "rebate_to_sme_usd": float(rebate),
                    "sme_pays_factor_usd": 0.0, "credit_loss_borne_by": "nobody (buyer paid)"}
        if scenario == "default":
            cutoff = self.expected_settlement_date + timedelta(days=self.recourse_days)
            interest = self.interest_to(cutoff)
            if self.recourse == "recourse":
                owed = self.principal_usd + self.settlement_fee_usd + interest
                return {"scenario": scenario, "recourse_date": cutoff.isoformat(), "interest_usd": float(interest),
                        "sme_pays_factor_usd": float(owed), "rebate_to_sme_usd": 0.0,
                        "total_cost_usd": float(self.settlement_fee_usd + interest),
                        "credit_loss_borne_by": f"SME (recourse: repays advance, fee and interest by {cutoff.isoformat()})",
                        "sme_loses_invoice_usd": float(self.invoice_usd)}
            return {"scenario": scenario, "interest_usd": 0.0, "sme_pays_factor_usd": 0.0, "rebate_to_sme_usd": 0.0,
                    "total_cost_usd": float(self.invoice_usd - self.principal_usd),
                    "credit_loss_borne_by": "factor (non-recourse); the SME keeps the advance and forfeits the reserve"}
        raise ValueError(f"unknown scenario {scenario!r}")

    def scenarios(self) -> List[Dict[str, Any]]:
        return [self.outcome(s) for s in ("on_time", "late_30", "default")] if self.option_type == "factoring" else [self.outcome("on_time")]

    # ------------------------------------------------------------------ cash adjustments
    def cash_adjustments(self, invoice_receipts: Sequence[Tuple[date, Decimal]] = ()) -> List[Tuple[date, Decimal]]:
        """Dated changes to the SME's cash relative to the base forecast.

        ``invoice_receipts``: (expected date, USD) of the pledged invoice as the base forecast has them.
        Factoring: +advance at drawdown; each receipt is replaced by its share of the rebate, i.e.
        -share x (advance + fee + interest to that date). Loan: +net funds at drawdown, -(principal +
        interest) at the end of the term.
        """
        out: List[Tuple[date, Decimal]] = [(self.drawdown_date, self.net_received_usd)]
        if self.option_type == "loan":
            out.append((self.expected_settlement_date, -(self.principal_usd + self.interest_usd)))
            return out
        receipts = [(d, Decimal(a)) for d, a in invoice_receipts if Decimal(a) > 0] or [(self.expected_settlement_date, self.invoice_usd)]
        total = sum(a for _, a in receipts)
        base = self.principal_usd + self.settlement_fee_usd  # repaid out of the collection, split by receipt share
        allocated = Decimal(0)
        for i, (day, amount) in enumerate(receipts):
            share = amount / total
            base_part = cents(share * base) if i < len(receipts) - 1 else base - allocated  # last part takes the remainder
            allocated += base_part
            out.append((day, -(base_part + cents(share * self.interest_to(day)))))
        return out

    def expected_cost_usd(self, invoice_receipts: Sequence[Tuple[date, Decimal]] = ()) -> Decimal:
        """Minus the sum of all cash adjustments: the expected financing cost under the receipt timing."""
        return -sum(a for _, a in self.cash_adjustments(invoice_receipts))

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, (date,)):
                d[k] = v.isoformat()
            elif isinstance(v, Decimal):
                d[k] = float(v)
            elif isinstance(v, tuple):
                d[k] = list(v)
        d.update(days_financed=self.days_financed, interest_usd=float(self.interest_usd), total_cost_usd=float(self.total_cost_usd),
                 net_received_usd=float(self.net_received_usd), reserve_usd=float(self.reserve_usd) if self.reserve_usd is not None else None,
                 cost_convention="simple annualised, Actual/365 (internal estimate, not a legal APR)")
        return d
