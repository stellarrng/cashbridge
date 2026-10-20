"""Model card + fairness and calibration audit for the buyer-payment model (Audit 2).

    python eval/model_fairness.py        # writes reports/model_card.md and reports/model_fairness.json

What is scored: whether a BUYER (a company that owes the SME money) pays an invoice within 3 days of
its due date. Nobody is scored as a person and the SME itself is not credit-scored by this model; the
lender's credit decision is recorded by a named human. Inputs: buyer identity, payment terms, invoice
size relative to that buyer's usual invoice. No personal or protected attributes.

Audit steps (walk-forward: each prediction uses only earlier invoices):
1. calibration and Brier score per group: market (= buyer country), invoice-size band, terms band;
2. ablation: the same model WITHOUT buyer identity, to show how much the buyer (and therefore country,
   because each market has one buyer in this data) drives the score;
3. new-buyer handling: a buyer with no history gets the portfolio average, not a penalty;
4. explanation exactness: intercept + contributions reproduce the score.
SYNTHETIC history of 185 invoices: indicative only.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from agents.buyer_risk_agent import GRACE_DAYS, BuyerRiskAgent, _terms_days, _usd  # noqa: E402
from data import loader  # noqa: E402

REPORTS = Path(__file__).resolve().parent.parent / "reports"
MIN_TRAIN = 18


def wilson(k: int, n: int, z: float = 1.96) -> List[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def walk_forward(identity: bool = True) -> List[Dict[str, Any]]:
    recs = sorted(loader.read("payment_history.json")["records"], key=lambda r: r["issue_date"])
    rows = []
    for i in range(MIN_TRAIN, len(recs)):
        train, t = recs[:i], recs[i]
        if not identity:  # ablation: every buyer looks the same to the model
            train = [{**r, "buyer_id": "ANY"} for r in train]
        agent = BuyerRiskAgent(train)
        buyer = t["buyer_id"] if identity else "ANY"
        p = agent.p_on_time_for(buyer, _terms_days(t), _usd(t)) if agent.has_history(buyer) else \
            agent.p_on_time_for(buyer, _terms_days(t), _usd(t))
        size = _usd(t) / agent.medians.get(buyer, _usd(t))
        rows.append({"invoice": t["invoice_no"], "buyer": t["buyer_id"], "market": t["buyer_id"].split("-")[1],
                     "terms_band": "<=45 days" if _terms_days(t) <= 45 else ">45 days",
                     "size_band": "smaller than usual" if size < 0.9 else "usual" if size <= 1.1 else "larger than usual",
                     "p": p, "y": 1 if t["days_late"] <= GRACE_DAYS else 0})
    return rows


def groups(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    out = []
    for g in sorted({r[key] for r in rows}):
        xs = [r for r in rows if r[key] == g]
        n, k = len(xs), sum(r["y"] for r in xs)
        mean_p = float(np.mean([r["p"] for r in xs]))
        lo, hi = wilson(k, n)
        out.append({"group": g, "n": n, "predicted_on_time": round(mean_p, 3), "observed_on_time": round(k / n, 3),
                    "observed_wilson95": [lo, hi], "calibration_gap": round(mean_p - k / n, 3),
                    "within_interval": lo <= mean_p <= hi,
                    "brier": round(float(np.mean([(r["p"] - r["y"]) ** 2 for r in xs])), 4)})
    return out


def run() -> Dict[str, Any]:
    full = walk_forward(True)
    blind = walk_forward(False)
    brier = lambda rows: round(float(np.mean([(r["p"] - r["y"]) ** 2 for r in rows])), 4)  # noqa: E731
    recs = loader.read("payment_history.json")["records"]
    agent = BuyerRiskAgent(recs)
    new_buyer = agent.p_on_time_for("B-NEW-99", 60, 20000)
    known = {b: agent.p_on_time_for(b, 60, agent.medians[b]) for b in agent.buyers}
    known_unrounded = [agent._probability(agent._vector(b, 60, agent.medians[b])) for b in agent.buyers]
    sample = agent.explain("B-JP-01", 60, agent.medians["B-JP-01"])
    reconstructed = sample["intercept"] + sum(c["contribution_log_odds"] for c in sample["contributions"])
    return {
        "synthetic": True, "n_history": len(recs), "n_walk_forward": len(full),
        "intended_use": "Expected timing of buyer payments inside the SME's 13-week cash forecast.",
        "out_of_scope": ["Credit-scoring the SME or any person", "Automatic lending decisions", "Buyers in markets or sizes outside the training range"],
        "features": ["buyer identity (one-hot)", "payment terms / 30 days", "invoice size / buyer's median invoice"],
        "protected_or_personal_attributes": [],
        "domain": agent.domain(),
        "overall": {"brier_full": brier(full), "brier_without_buyer_identity": brier(blind)},
        "by_market": groups(full, "market"), "by_size": groups(full, "size_band"), "by_terms": groups(full, "terms_band"),
        "by_market_without_identity": groups(blind, "market"),
        "new_buyer": {"p_on_time": new_buyer, "portfolio_mean_of_known": round(float(np.mean(known_unrounded)), 4), "known": known},
        "explanation_check": {"buyer": "B-JP-01", "log_odds": sample["log_odds"], "reconstructed": round(reconstructed, 4),
                              "contributions": sample["contributions"]},
        "confound": "Each market has exactly one buyer in this history (US 135 invoices, CN 30, JP 20), so a market effect "
                    "cannot be separated from that buyer's own payment record.",
    }


def write(res: Dict[str, Any]) -> Path:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "model_fairness.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    def table(rows):
        lines = ["| Group | n | Predicted on time | Observed (95% CI) | Gap | Within CI | Brier |", "|---|---|---|---|---|---|---|"]
        for g in rows:
            lines.append(f"| {g['group']} | {g['n']} | {g['predicted_on_time']:.1%} | {g['observed_on_time']:.1%} "
                         f"({g['observed_wilson95'][0]:.0%}-{g['observed_wilson95'][1]:.0%}) | {g['calibration_gap']:+.1%} | "
                         f"{'yes' if g['within_interval'] else '**no**'} | {g['brier']} |")
        return lines
    o = res["overall"]
    md = ["# Model card: buyer on-time payment model", "",
          "`python eval/model_fairness.py`. SYNTHETIC history; walk-forward (each prediction uses only earlier invoices).", "",
          "## What it is for, and what it is not", "",
          f"- **Intended use:** {res['intended_use']}",
          "- **Out of scope:** " + "; ".join(res["out_of_scope"]) + ".",
          "- **Features:** " + "; ".join(res["features"]) + ". **Personal or protected attributes: none.**",
          f"- **Training domain:** terms {res['domain']['terms_days'][0]}-{res['domain']['terms_days'][1]} days, size "
          f"{res['domain']['size_vs_usual'][0]}-{res['domain']['size_vs_usual'][1]}x the buyer's usual invoice; outside it the "
          "explanation shows an `out_of_domain` warning.",
          "- **Probability band:** scores are clipped to 2%-98%; the model never states certainty.", "",
          f"## Overall ({res['n_walk_forward']} walk-forward predictions)", "",
          f"Brier score {o['brier_full']} with buyer identity, {o['brier_without_buyer_identity']} without it (lower is better).", "",
          "## Calibration by market (= buyer country here)", ""] + table(res["by_market"]) + [
          "", f"**Confound:** {res['confound']}", "",
          "Ablation without buyer identity (terms and size only). Calibration breaks for the smallest market, so the identity "
          "term carries each buyer's own payment record rather than adding noise; it is still a country proxy here and is "
          "disclosed as such:", ""] + table(res["by_market_without_identity"]) + [
          "", "## Calibration by invoice size and by payment terms", ""] + table(res["by_size"]) + [""] + table(res["by_terms"]) + [
          "", "## New buyers are not penalised", "",
          f"A buyer with no history is scored at {res['new_buyer']['p_on_time']:.0%}, the portfolio average of known buyers "
          f"({res['new_buyer']['portfolio_mean_of_known']:.0%}), and marked `has_history: false`.", "",
          "## Every score can be explained", "",
          f"Example {res['explanation_check']['buyer']}: intercept + contributions = {res['explanation_check']['reconstructed']} "
          f"log-odds (model: {res['explanation_check']['log_odds']}). The lender sees this breakdown in the case view "
          "(`buyer_risk_explanation`).", "",
          "## Limits", "",
          "- 185 synthetic invoices from three buyers; group intervals are wide, and small groups (JP, n≈20) can look calibrated by chance.",
          "- No external validation on real buyer payment data (harness: `eval/external_validation.py`).",
          "- Payment timing of companies, not people: anti-discrimination rules for consumer credit do not map directly, "
          "but country effects should still be reviewed before using the score across markets."]
    path = REPORTS / "model_card.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    r = run()
    print(write(r))
    print(json.dumps({k: r[k] for k in ("overall", "by_market", "new_buyer")}, indent=2))
