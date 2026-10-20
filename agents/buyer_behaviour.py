"""Point-in-time behavioural buyer score (v9), externally validated as a cross-check of the v8 model.

Features follow the invoice-payment work of Appel et al. (IBM Research; arXiv 1912.10828, KDD MLF 2020
arXiv 2008.07363): the customer's own recent payment behaviour, computed only from what was known on
the scoring date. On the public IBM accounts-receivable sample (eval/external_buyer_validation.py) it
generalises to customers never seen in training (ROC-AUC about 0.90) where the v8 buyer-identity model
falls back to the base rate, and it is better calibrated in time (ECE about 0.02 vs 0.07).

It is shown to the lender next to the v8 score, labelled as a second opinion. It is not a credit decision.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Sequence

import numpy as np

from agents.buyer_risk_agent import GRACE_DAYS, NumpyLogisticRegression, _terms_days, _usd

FEATURES = ("shrunk_ontime_rate", "recent_days_late", "last_late", "open_at_issue", "log_size")
PRIOR = 4.0


def _label(r: Dict[str, Any]) -> int:
    return 1 if r["days_late"] <= GRACE_DAYS else 0


def _paid_on(r: Dict[str, Any]) -> date:
    return date.fromisoformat(r["paid_date"]) if r.get("paid_date") else date.fromisoformat(r["due_date"]) + timedelta(days=r["days_late"])


def features_at(history: Sequence[Dict[str, Any]], buyer: str, when: date, amount_usd: float, prior_rate: float) -> List[float]:
    known = sorted((r for r in history if r["buyer_id"] == buyer and _paid_on(r) < when), key=_paid_on)
    n, ontime = len(known), sum(_label(r) for r in known)
    recent = [r for r in known if _paid_on(r) >= when - timedelta(days=90)]
    open_now = sum(1 for r in history if r["buyer_id"] == buyer and date.fromisoformat(r["issue_date"]) < when <= _paid_on(r))
    med = float(np.median([_usd(r) for r in known])) if known else amount_usd
    return [(ontime + PRIOR * prior_rate) / (n + PRIOR),
            float(np.mean([max(0, r["days_late"]) for r in recent])) if recent else 0.0,
            1.0 if known and _label(known[-1]) == 0 else 0.0, float(open_now),
            math.log(max(amount_usd, 0.01) / max(med, 0.01))]


class BehaviouralBuyerModel:
    def __init__(self, history: Sequence[Dict[str, Any]]) -> None:
        self.history = list(history)
        labels = [_label(r) for r in self.history]
        self.prior_rate = sum(labels) / len(labels) if labels else 0.5
        rows = [features_at(self.history, r["buyer_id"], date.fromisoformat(r["issue_date"]), _usd(r), self.prior_rate) for r in self.history]
        X = np.array(rows) if rows else np.zeros((0, len(FEATURES)))
        self.mu, self.sd = (X.mean(0), X.std(0) + 1e-9) if len(X) else (np.zeros(len(FEATURES)), np.ones(len(FEATURES)))
        self.fitted = len(set(labels)) == 2
        if self.fitted:
            self.clf = NumpyLogisticRegression(C=1.0).fit((X - self.mu) / self.sd, np.array(labels))

    def score(self, buyer: str, when: date, amount_usd: float) -> Dict[str, Any]:
        x = np.array(features_at(self.history, buyer, when, amount_usd, self.prior_rate))
        if not self.fitted:
            return {"p_on_time": round(self.prior_rate, 2), "method": "base rate (history has one outcome)"}
        z = (x - self.mu) / self.sd
        p = float(self.clf.predict_proba(z[None, :])[0, 1])
        contrib = {f: round(float(c * v), 4) for f, c, v in zip(FEATURES, self.clf.coef_[0], z)}
        return {"p_on_time": round(min(0.98, max(0.02, p)), 2), "features": dict(zip(FEATURES, [round(float(v), 4) for v in x])),
                "contributions_log_odds": contrib, "intercept": round(float(self.clf.intercept_[0]), 4),
                "method": "point-in-time behavioural logistic (v9 cross-check)",
                "external_validation": "reports/external_buyer_validation.md", "not_a_credit_decision": True}
