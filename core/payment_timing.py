"""When will an open invoice be paid? A censoring-aware, buyer-specific delay distribution (v9).

v8 placed the expected on-time part of an invoice on its due date and the remainder exactly
LATE_PAYMENT_DELAY_WEEKS (4) later. Real delays are neither binary nor fixed. This module estimates the
whole distribution of days late per buyer:

* Discrete-time survival on L = paid - due days (negative = paid early, down to -EARLY_DAYS), estimated with the Kaplan-Meier product-limit
  estimator (Kaplan & Meier 1958) so invoices still unpaid at the forecast origin count as right-censored
  observations instead of being dropped or treated as late (the leakage trap noted in survival work on
  invoices, e.g. random survival forests for late invoice payment, University of Tartu thesis).
* Per-buyer hazards are shrunk towards the portfolio hazard with a Beta prior of strength ``k``
  (empirical-Bayes / beta-binomial smoothing, in the spirit of Efron & Morris 1975): a buyer with few
  invoices borrows strength from the portfolio, a buyer with many keeps its own pattern.
* For an invoice already overdue by ``a`` days at the origin, the distribution is conditioned on L > a.

Only outcomes observable at the origin are used (paid on or before the origin, or censored at it).
Pure NumPy; deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

MAX_DAYS = 120          # latest day modelled after the due date; mass beyond goes to the tail
EARLY_DAYS = 60         # earliest day modelled before the due date (early payers are common)
DEFAULT_PRIOR_STRENGTH = 8.0


@dataclass(frozen=True)
class Observation:
    buyer: str
    due: date
    paid: Optional[date]  # None = not paid by the origin (censored)


def observations_at(origin: date, invoices: Iterable[Tuple[str, date, date]]) -> List[Observation]:
    """Point-in-time training set: (buyer, due, paid) rows as they were known on ``origin``.

    Every invoice due within EARLY_DAYS of the origin (or earlier) carries information: if paid by the
    origin it is an event, otherwise it is censored at the origin (known unpaid through that day, even if
    not yet due). Payments after the origin are never visible.
    """
    out = []
    for buyer, due, paid in invoices:
        if (origin - due).days < -EARLY_DAYS:
            continue
        out.append(Observation(buyer, due, paid if paid is not None and paid <= origin else None))
    return out


def _cell(days_rel_due: int) -> int:
    """Index of a day relative to the due date: 0 = EARLY_DAYS early (or earlier), last = later than MAX_DAYS."""
    return min(EARLY_DAYS + MAX_DAYS + 1, max(0, days_rel_due + EARLY_DAYS))


SIZE = EARLY_DAYS + MAX_DAYS + 2


def _counts(obs: Sequence[Observation], origin: date) -> Tuple[np.ndarray, np.ndarray]:
    """events[c] = paid on cell c; at_risk[c] = still unpaid at the start of cell c (Kaplan-Meier risk set)."""
    events = np.zeros(SIZE)
    censor = np.zeros(SIZE)
    for o in obs:
        if o.paid is not None:
            events[_cell((o.paid - o.due).days)] += 1
        else:  # unpaid at the origin: known only that payment comes after origin - due
            c = (origin - o.due).days
            if c >= -EARLY_DAYS:
                censor[_cell(c)] += 1
    at_risk = np.cumsum(events[::-1])[::-1] + np.cumsum(censor[::-1])[::-1]
    return events, at_risk


class PaymentTimingModel:
    """Shrunk Kaplan-Meier delay distribution per buyer, fitted on what was known at ``origin``."""

    def __init__(self, obs: Sequence[Observation], origin: date, prior_strength: float = DEFAULT_PRIOR_STRENGTH) -> None:
        self.origin = origin
        self.k = float(prior_strength)
        ev, rk = _counts(obs, origin)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.pool_hazard = np.where(rk > 0, ev / rk, 0.0)
        self.pool_hazard[-1] = 1.0  # everything left at the end of the support is paid "later"
        self.buyer_hazard: Dict[str, np.ndarray] = {}
        self.buyer_n: Dict[str, int] = {}
        for b in sorted({o.buyer for o in obs}):
            mine = [o for o in obs if o.buyer == b]
            e, r = _counts(mine, origin)
            with np.errstate(invalid="ignore", divide="ignore"):
                # Beta(k*h_pool, k*(1-h_pool)) prior on each daily hazard; no data and no prior -> the pooled hazard
                h = np.where(r + self.k > 0, (e + self.k * self.pool_hazard) / (r + self.k), self.pool_hazard)
            h[-1] = 1.0
            self.buyer_hazard[b] = h
            self.buyer_n[b] = len(mine)

    def hazard(self, buyer: str) -> np.ndarray:
        return self.buyer_hazard.get(buyer, self.pool_hazard)

    def pmf(self, buyer: str, unpaid_through: Optional[int] = None) -> np.ndarray:
        """P(paid on cell c), cells = days relative to due from -EARLY_DAYS to MAX_DAYS, plus a 'later' cell.

        ``unpaid_through``: days relative to due through which the invoice is known unpaid (conditioning).
        """
        h = self.hazard(buyer)
        surv = np.concatenate([[1.0], np.cumprod(1 - h)[:-1]])
        f = surv * h
        if unpaid_through is not None and unpaid_through >= -EARLY_DAYS:
            f = f.copy()
            f[: _cell(unpaid_through) + 1] = 0.0
            total = f.sum()
            f = f / total if total > 0 else np.eye(len(f))[-1]
        return f

    @staticmethod
    def day_of_cell(c: int) -> Optional[int]:
        return None if c >= SIZE - 1 else c - EARLY_DAYS

    def p_on_time(self, buyer: str, grace_days: int = 3) -> float:
        return float(self.pmf(buyer)[: _cell(grace_days) + 1].sum())

    def weekly_receipts(self, invoices: Sequence[Tuple[str, date, float]], start: date, weeks: int = 13):
        """Expected receipts per forecast week for invoices open at the start of ``start`` (buyer, due, amount).

        Returns (per-week array, amount expected after the horizon).
        """
        out = np.zeros(weeks + 1)
        for buyer, due, amount in invoices:
            f = self.pmf(buyer, (start - due).days - 1)  # open at start: unpaid through the day before
            for c, p in enumerate(f):
                if p <= 0:
                    continue
                rel = self.day_of_cell(c)
                w = weeks if rel is None else max(0, (due + timedelta(days=rel) - start).days) // 7
                out[min(w, weeks)] += amount * p
        return out[:weeks], out[weeks]

    def sample_weeks(self, invoices: Sequence[Tuple[str, date, float]], start: date, weeks: int, n: int, rng: np.random.Generator) -> np.ndarray:
        """Monte Carlo receipts per week (n x weeks) assuming invoices settle independently."""
        sims = np.zeros((n, weeks))
        for buyer, due, amount in invoices:
            f = self.pmf(buyer, (start - due).days - 1)
            cs = rng.choice(len(f), size=n, p=f / f.sum())
            rel = cs - EARLY_DAYS
            days = np.where(cs < SIZE - 1, (due - start).days + rel, 10_000)
            w = np.maximum(0, days) // 7
            ok = w < weeks
            np.add.at(sims, (np.arange(n)[ok], w[ok]), amount)
        return sims


def v8_rule_receipts(invoices: Sequence[Tuple[str, date, float, float]], start: date, weeks: int = 13, delay_weeks: int = 4) -> np.ndarray:
    """The v8 forecast rule: on-time share p on the due date (or week 1 if overdue), the rest ``delay_weeks`` later."""
    out = np.zeros(weeks)
    for _buyer, due, amount, p in invoices:
        w = max(0, (due - start).days) // 7
        if w < weeks:
            out[w] += amount * p
        if w + delay_weeks < weeks:
            out[w + delay_weeks] += amount * (1 - p)
    return out
