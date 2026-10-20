"""Calibrated forecast intervals: split conformal and adaptive conformal inference (v9).

A model's own P10-P90 band is only as honest as the model. Conformal prediction wraps any point
forecast with an interval whose coverage is checked against realised errors:

* Split conformal (Vovk et al.; for multi-horizon series, Stankeviciute, Alaa & van der Schaar,
  NeurIPS 2021): the interval half-width for horizon h is the ceil((n+1)(1-alpha))/n empirical quantile
  of past absolute errors at that horizon.
* Adaptive conformal inference, ACI (Gibbs & Candes, NeurIPS 2021): the working miscoverage level is
  updated online, alpha_{t+1} = alpha_t + gamma (alpha - err_t), where err_t = 1 if the realised value fell
  outside the interval. Over a long run the miss rate approaches alpha even when the data drift.

Only errors whose targets had been realised by the forecast origin are used (no look-ahead).
"""

from __future__ import annotations

import math
from typing import List, Sequence

import numpy as np


def conformal_quantile(scores: Sequence[float], alpha: float) -> float:
    """Finite-sample split-conformal quantile; +inf when there are too few scores for the level."""
    s = np.sort(np.asarray(scores, dtype=float))
    n = len(s)
    if n == 0:
        return math.inf
    k = math.ceil((n + 1) * (1 - alpha))
    return float(s[k - 1]) if k <= n else math.inf


class ACI:
    """Adaptive conformal inference for one horizon: keeps its own alpha_t and score history."""

    def __init__(self, alpha: float = 0.2, gamma: float = 0.02, window: int = 200) -> None:
        if not 0 < alpha < 1 or gamma <= 0:
            raise ValueError("alpha in (0,1) and gamma > 0 required")
        self.alpha, self.gamma, self.window = alpha, gamma, window
        self.alpha_t = alpha
        self.scores: List[float] = []
        self.misses: List[int] = []

    def half_width(self) -> float:
        if self.alpha_t >= 1:
            return 0.0
        if self.alpha_t <= 0:
            return math.inf
        return conformal_quantile(self.scores[-self.window:], self.alpha_t)

    def update(self, covered: bool, score: float) -> None:
        err = 0 if covered else 1
        self.misses.append(err)
        self.alpha_t = self.alpha_t + self.gamma * (self.alpha - err)
        self.scores.append(float(score))


def coverage(lo: Sequence[float], hi: Sequence[float], y: Sequence[float]) -> float:
    lo, hi, y = map(np.asarray, (lo, hi, y))
    return float(np.mean((y >= lo) & (y <= hi))) if len(y) else float("nan")
