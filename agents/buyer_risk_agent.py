"""Buyer risk agent: concentration, average lateness and a fitted on-time probability per invoice.

The on-time probability comes from a logistic regression (scikit-learn) fitted on the company's own
payment history. An invoice is "on time" if it was paid within ``GRACE_DAYS`` of its due date. The inputs
are the buyer, the payment terms and the invoice size relative to that buyer's usual invoice; the coefficients are reported so the model can be
read and questioned. A buyer with no history gets the portfolio-level estimate and is marked as such.

Everything is deterministic: the same history always gives the same coefficients. The agent only reads
history and produces numbers; the forecast engine turns them into cash.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

try:  # scikit-learn is used when installed (local, Docker); serverless builds use the NumPy solver below.
    from sklearn.linear_model import LogisticRegression
except ImportError:  # pragma: no cover - exercised in the lean Vercel build
    LogisticRegression = None  # type: ignore[assignment]

from config.settings import CONCENTRATION_ALERT_PCT
from schemas.document_schemas import CommercialInvoice, Currency, Money
from schemas.forecast_schemas import OpenReceivable

GRACE_DAYS = 3
# A model fitted on one SME's history never states certainty: probabilities are kept inside this band.
P_FLOOR, P_CEILING = 0.02, 0.98
MODEL_FEATURES = ("terms_30_days", "size_vs_usual")


class NumpyLogisticRegression:
    """Same objective as scikit-learn's ``LogisticRegression(C, penalty="l2")``: the mean-free sum of
    log-losses times C plus half the squared weights (intercept not penalised), solved by Newton's method.
    Used only when scikit-learn is unavailable; ``tests/test_buyer_risk.py`` checks both agree."""

    def __init__(self, C: float = 10.0, max_iter: int = 100, tol: float = 1e-10) -> None:
        self.C, self.max_iter, self.tol = C, max_iter, tol

    def fit(self, X: np.ndarray, y: np.ndarray) -> "NumpyLogisticRegression":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        Xb = np.hstack([X, np.ones((X.shape[0], 1))])
        w = np.zeros(Xb.shape[1])
        reg = np.ones(Xb.shape[1]) / self.C
        reg[-1] = 0.0
        for _ in range(self.max_iter):
            p = 1.0 / (1.0 + np.exp(-(Xb @ w)))
            grad = Xb.T @ (p - y) + reg * w
            hess = (Xb * (p * (1 - p))[:, None]).T @ Xb + np.diag(reg) + 1e-12 * np.eye(Xb.shape[1])
            step = np.linalg.solve(hess, grad)
            w -= step
            if np.max(np.abs(step)) < self.tol:
                break
        self.coef_ = np.array([w[:-1]])
        self.intercept_ = np.array([w[-1]])
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        z = np.asarray(X, dtype=float) @ self.coef_[0] + self.intercept_[0]
        p = 1.0 / (1.0 + np.exp(-z))
        return np.column_stack([1 - p, p])


@dataclass
class RiskModel:
    """A fitted model and what is needed to read it."""

    buyers: List[str]
    coefficients: Dict[str, float]
    intercept: float
    training_rows: int
    on_time_rate: float
    classifier: Optional[Any]
    constant: float = 0.5  # used only when the history has a single outcome and no regression can be fitted

    def describe(self) -> Dict[str, Any]:
        return {
            "method": "Logistic regression (L2, C=10) on past invoices" if self.classifier is not None
            else "Overall on-time rate, smoothed (the history has only one outcome, so no regression can be fitted)",
            "on_time_definition": f"Paid within {GRACE_DAYS} days of the due date",
            "training_rows": self.training_rows,
            "on_time_rate_pct": round(self.on_time_rate * 100, 1),
            "intercept": round(self.intercept, 3),
            "coefficients": [{"name": name, "coefficient": round(value, 3)} for name, value in self.coefficients.items()],
        }


def _usd(record: Dict[str, Any]) -> float:
    return float(Money.from_amount(Decimal(record["amount"]), Currency(record["currency"])).to_usd())


def _terms_days(record: Dict[str, Any]) -> int:
    return (date.fromisoformat(record["due_date"]) - date.fromisoformat(record["issue_date"])).days


class BuyerRiskAgent:
    """Fits the model once from payment history, then scores invoices and buyers."""

    def __init__(self, history: Sequence[Dict[str, Any]]) -> None:
        self.history = list(history)
        self.buyers = sorted({r["buyer_id"] for r in self.history})
        self.medians = {b: float(np.median([_usd(r) for r in self.history if r["buyer_id"] == b])) for b in self.buyers}
        self.model = self._fit()

    # ---------------------------------------------------------------- model
    def _relative_size(self, buyer_id: str, amount_usd: float) -> float:
        """Invoice size divided by the buyer's median invoice in the history (1.0 for a buyer with no history)."""
        return amount_usd / self.medians[buyer_id] if buyer_id in self.medians else 1.0

    def _vector(self, buyer_id: str, terms_days: float, amount_usd: float) -> List[float]:
        return [1.0 if buyer_id == b else 0.0 for b in self.buyers] + [terms_days / 30.0, self._relative_size(buyer_id, amount_usd)]

    def _fit(self) -> RiskModel:
        rows = [self._vector(r["buyer_id"], _terms_days(r), _usd(r)) for r in self.history]
        labels = [1 if r["days_late"] <= GRACE_DAYS else 0 for r in self.history]
        smoothed = (sum(labels) + 1) / (len(labels) + 2)  # Laplace smoothing: never exactly 0 or 1
        if len(set(labels)) < 2:
            return RiskModel(self.buyers, {}, 0.0, len(rows), sum(labels) / len(labels) if labels else 0.0, None, smoothed)
        classifier = (LogisticRegression(C=10.0, solver="lbfgs", max_iter=5000, tol=1e-10) if LogisticRegression is not None
                      else NumpyLogisticRegression(C=10.0))
        classifier.fit(np.array(rows), np.array(labels))
        names = [f"buyer {b}" for b in self.buyers] + list(MODEL_FEATURES)
        return RiskModel(
            buyers=self.buyers,
            coefficients=dict(zip(names, (float(c) for c in classifier.coef_[0]))),
            intercept=float(classifier.intercept_[0]),
            training_rows=len(rows),
            on_time_rate=sum(labels) / len(labels),
            classifier=classifier,
            constant=smoothed,
        )

    def _probability(self, vector: List[float]) -> float:
        if self.model.classifier is None:
            return self.model.constant
        return float(self.model.classifier.predict_proba(np.array([vector]))[0][1])

    def has_history(self, buyer_id: str) -> bool:
        return buyer_id in self.buyers

    def p_on_time(self, invoice: CommercialInvoice) -> float:
        """Probability the invoice is paid on time. A buyer with no history is scored as the portfolio average."""
        terms = (invoice.due_date - invoice.issue_date).days
        return self.p_on_time_for(invoice.buyer_id, terms, float(invoice.amount.to_usd()))

    def p_on_time_for(self, buyer_id: str, terms_days: int, amount_usd: float) -> float:
        """Same score for something that is not an invoice yet (a confirmed order), from its planned terms."""
        if not self.has_history(buyer_id):
            probability = self._portfolio_probability(terms_days, amount_usd)
        else:
            probability = self._probability(self._vector(buyer_id, terms_days, amount_usd))
        return round(min(P_CEILING, max(P_FLOOR, probability)), 2)

    def _portfolio_probability(self, terms_days: int, amount_usd: float) -> float:
        """Average of the known buyers' probabilities for a usual-sized invoice on these terms."""
        if not self.buyers:
            return self.model.constant
        scores = [self._probability(self._vector(b, terms_days, self.medians[b])) for b in self.buyers]
        return sum(scores) / len(scores)

    # ------------------------------------------------------------- per buyer
    def average_days_late(self, buyer_id: str) -> Optional[float]:
        """Mean days late over the buyer's history, counting early and on-time payments as zero."""
        late = [max(0, r["days_late"]) for r in self.history if r["buyer_id"] == buyer_id]
        return round(sum(late) / len(late), 1) if late else None

    def table(self, receivables: Sequence[OpenReceivable], shares: Dict[str, Decimal]) -> List[Dict[str, Any]]:
        """Contract rows: one per buyer with open invoices, largest share first."""
        names: Dict[str, str] = {}
        open_p: Dict[str, List[float]] = {}
        open_usd: Dict[str, float] = {}
        for item in receivables:
            names[item.buyer_id] = item.buyer_name
            usd = float(item.amount.to_usd())
            open_usd[item.buyer_id] = open_usd.get(item.buyer_id, 0.0) + usd
            open_p.setdefault(item.buyer_id, []).append(item.p_on_time * usd)
        rows = []
        for buyer, name in names.items():
            weighted = sum(open_p[buyer]) / open_usd[buyer] if open_usd[buyer] else 0.0
            share = float(shares.get(buyer, Decimal(0)))
            rows.append(
                {
                    "buyer": name,
                    "buyer_id": buyer,
                    "share_of_receivables_pct": share,
                    "avg_days_late": self.average_days_late(buyer) or 0.0,
                    "p_on_time": round(weighted, 2),
                    "concentration_alert": share > float(CONCENTRATION_ALERT_PCT),
                    "has_history": self.has_history(buyer),
                }
            )
        return sorted(rows, key=lambda r: (-r["share_of_receivables_pct"], r["buyer"]))
