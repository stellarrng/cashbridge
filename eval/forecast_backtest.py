"""Rolling-origin backtest of the 13-week receipts forecast (v9): v8 rule vs survival timing model.

    python scripts/fetch_external_data.py      # once: public data, SHA-256 pinned
    python eval/forecast_backtest.py           # writes reports/forecast_backtest.{json,md}

Protocol (Tashman 2000, "Out-of-sample tests of forecasting accuracy", rolling origin):
for every weekly origin, use only what was known that Monday (invoices issued by then, payments made
before then), forecast the receipts from the invoices still open for each of the next 13 weeks, and
compare with what was actually received from those invoices. Nothing after the origin is used to fit.

Methods
  contractual   every open invoice paid on its due date (overdue ones in week 1)
  v8_rule       CashBridge v8: on-time probability from the v8 buyer model at the due date, the rest 4 weeks later
  km_pooled     v9 (used by the product): censoring-aware Kaplan-Meier delay distribution, early payment included,
                one for all buyers (core/payment_timing.py)
  km_buyer      variant: the same per buyer, shrunk to the portfolio (prior strength 8). Reported, not used: it was
                not better than pooled on either dataset, and larger shrinkage was always better (time-respecting tuning)

Metrics: WAPE (sum |error| / sum actual), MAE, bias (sum error / sum actual) by horizon; for km_pooled
also the 80% interval coverage of (a) its own Monte Carlo P10-P90 and (b) conformal intervals: split
conformal and adaptive conformal inference (core/conformal.py), calibrated only on errors already
realised at each origin.

Datasets: the public IBM accounts-receivable sample (external) and CashBridge's own synthetic history.
Scope: receipts from invoices open at the origin (what an invoice-level model can forecast). New sales,
costs and bank balances are not in these data, so this is not a full cash-balance validation.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from core import conformal as cf  # noqa: E402
from core.payment_timing import PaymentTimingModel, observations_at, v8_rule_receipts  # noqa: E402

REPORTS = Path(__file__).resolve().parent.parent / "reports"
WEEKS = 13
ALPHA = 0.2  # 80% intervals


# ----------------------------------------------------------------------------- data
def load_ibm(path: Path) -> List[Dict[str, Any]]:
    p = lambda s: datetime.strptime(s, "%m/%d/%Y").date()  # noqa: E731
    out = []
    for r in csv.DictReader(path.open(encoding="utf-8")):
        out.append({"buyer": r["customerID"], "issue": p(r["InvoiceDate"]), "due": p(r["DueDate"]), "paid": p(r["SettledDate"]),
                    "amount": float(r["InvoiceAmount"]), "market": r["countryCode"]})
    return out


def load_cashbridge() -> List[Dict[str, Any]]:
    from agents.buyer_risk_agent import _usd
    from data import loader
    out = []
    for r in loader.read("payment_history.json")["records"]:
        out.append({"buyer": r["buyer_id"], "issue": date.fromisoformat(r["issue_date"]), "due": date.fromisoformat(r["due_date"]),
                    "paid": date.fromisoformat(r["paid_date"]), "amount": _usd(r), "market": r["buyer_id"].split("-")[1]})
    return out


# ----------------------------------------------------------------------------- v8 probability, point in time
def v8_probabilities(rows: List[Dict[str, Any]], origin: date, open_rows: List[Dict[str, Any]]) -> List[float]:
    """What v8 would have used: its logistic buyer model refitted on invoices PAID before the origin (v8 never sees censored ones)."""
    from agents.buyer_risk_agent import BuyerRiskAgent
    hist = [{"buyer_id": r["buyer"], "amount": f"{r['amount']:.2f}", "currency": "USD", "issue_date": r["issue"].isoformat(),
             "due_date": r["due"].isoformat(), "days_late": (r["paid"] - r["due"]).days} for r in rows if r["paid"] < origin]
    if len(hist) < 10:
        return [0.5] * len(open_rows)
    agent = BuyerRiskAgent(hist)
    return [agent.p_on_time_for(r["buyer"], (r["due"] - r["issue"]).days, r["amount"]) for r in open_rows]


# ----------------------------------------------------------------------------- backtest
def backtest(rows: List[Dict[str, Any]], name: str, warmup_weeks: int = 26, step_weeks: int = 1, mc: int = 400, seed: int = 7) -> Dict[str, Any]:
    first = min(r["issue"] for r in rows)
    last = max(r["paid"] for r in rows)
    origin = first + timedelta(days=(7 - first.weekday()) % 7) + timedelta(weeks=warmup_weeks)
    rng = np.random.default_rng(seed)
    methods = ("contractual", "v8_rule", "km_pooled", "km_buyer")
    err: Dict[str, List[List[float]]] = {m: [] for m in methods}
    actuals: List[List[float]] = []
    mc_cover: List[List[bool]] = []
    points: List[Tuple[date, np.ndarray, np.ndarray]] = []  # (origin, v9 = km_pooled forecast, actual) for conformal replay
    origins = 0
    while origin + timedelta(weeks=WEEKS) <= last:
        open_rows = [r for r in rows if r["issue"] < origin and r["paid"] >= origin]
        if open_rows:
            actual = np.zeros(WEEKS)
            for r in open_rows:
                w = (r["paid"] - origin).days // 7
                if w < WEEKS:
                    actual[w] += r["amount"]
            obs = observations_at(origin - timedelta(days=1), ((r["buyer"], r["due"], r["paid"]) for r in rows))
            inv = [(r["buyer"], r["due"], r["amount"]) for r in open_rows]
            fc: Dict[str, np.ndarray] = {}
            fc["contractual"] = v8_rule_receipts([(b, d, a, 1.0) for b, d, a in inv], origin, WEEKS)
            p8 = v8_probabilities(rows, origin, open_rows)
            fc["v8_rule"] = v8_rule_receipts([(b, d, a, p) for (b, d, a), p in zip(inv, p8)], origin, WEEKS)
            pooled = PaymentTimingModel([type(o)("ALL", o.due, o.paid) for o in obs], origin - timedelta(days=1))
            fc["km_pooled"] = pooled.weekly_receipts([("ALL", d, a) for _, d, a in inv], origin, WEEKS)[0]
            model = PaymentTimingModel(obs, origin - timedelta(days=1))
            fc["km_buyer"] = model.weekly_receipts(inv, origin, WEEKS)[0]
            sims = pooled.sample_weeks([("ALL", d, a) for _, d, a in inv], origin, WEEKS, mc, rng)
            lo, hi = np.percentile(sims, 10, axis=0), np.percentile(sims, 90, axis=0)
            mc_cover.append(list((actual >= lo) & (actual <= hi)))
            for m in methods:
                err[m].append(list(fc[m] - actual))
            actuals.append(list(actual))
            points.append((origin, fc["km_pooled"], actual))
            origins += 1
        origin += timedelta(weeks=step_weeks)

    A = np.array(actuals)
    res: Dict[str, Any] = {"dataset": name, "origins": origins, "invoices": len(rows), "buyers": len({r["buyer"] for r in rows}),
                           "period": [min(r["issue"] for r in rows).isoformat(), last.isoformat()], "weeks": WEEKS, "methods": {}}
    for m in methods:
        E = np.array(err[m])
        res["methods"][m] = {"wape": round(float(np.abs(E).sum() / A.sum()), 4), "mae": round(float(np.abs(E).mean()), 2),
                             "bias": round(float(E.sum() / A.sum()), 4),
                             "wape_by_horizon": [round(float(np.abs(E[:, h]).sum() / A[:, h].sum()), 4) if A[:, h].sum() > 0 else None for h in range(WEEKS)]}
    res["_abs_errors_by_h"] = [list(np.abs(np.array(err["km_pooled"])[:, h])) for h in range(WEEKS)] if err["km_pooled"] else []
    res["_actual_by_h"] = [float(A[:, h].sum()) for h in range(WEEKS)]
    res["intervals"] = conformal_replay(points)
    res["intervals"]["v9_monte_carlo_p10_p90"] = round(float(np.mean(mc_cover)), 4)
    return res


def conformal_replay(points: List[Tuple[date, np.ndarray, np.ndarray]]) -> Dict[str, Any]:
    """Split conformal and ACI per horizon, using only errors realised before each origin (target week ended)."""
    split_cov, aci_cov, split_w, aci_w = [], [], [], []
    aci = [cf.ACI(alpha=ALPHA, gamma=0.02) for _ in range(WEEKS)]
    pending: List[Tuple[date, int, float, bool]] = []  # (realised_on, horizon, |error|, covered by ACI)
    history: Dict[int, List[float]] = defaultdict(list)
    for origin, f, y in points:
        # release errors whose target week has fully passed by this origin
        ready = [p for p in pending if p[0] <= origin]
        pending = [p for p in pending if p[0] > origin]
        for _, h, score, covered in ready:
            history[h].append(score)
            aci[h].update(covered, score)
        for h in range(WEEKS):
            q = cf.conformal_quantile(history[h][-200:], ALPHA)
            if np.isfinite(q):
                split_cov.append(abs(y[h] - f[h]) <= q)
                split_w.append(2 * q)
            w = aci[h].half_width()
            covered = abs(y[h] - f[h]) <= w
            if np.isfinite(w) and len(aci[h].scores) >= 10:
                aci_cov.append(covered)
                aci_w.append(2 * w)
            pending.append((origin + timedelta(weeks=h + 1), h, abs(y[h] - f[h]), covered))
    return {"nominal": 1 - ALPHA, "split_conformal": round(float(np.mean(split_cov)), 4) if split_cov else None,
            "aci": round(float(np.mean(aci_cov)), 4) if aci_cov else None,
            "split_mean_width": round(float(np.mean(split_w)), 2) if split_w else None,
            "aci_mean_width": round(float(np.mean(aci_w)), 2) if aci_w else None,
            "evaluated": {"split": len(split_cov), "aci": len(aci_cov)}}


def write(results: List[Dict[str, Any]]) -> Path:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "forecast_backtest.json").write_text(json.dumps([{k: v for k, v in r.items() if not k.startswith("_")} for r in results], indent=2),
                                                    encoding="utf-8")
    names = {"contractual": "Contractual (pay on due date)", "v8_rule": "CashBridge v8 rule",
             "km_pooled": "**v9: Kaplan-Meier, pooled (used)**", "km_buyer": "Variant: Kaplan-Meier per buyer, shrunk (not used)"}
    pctx = lambda v, a: "–" if a == 0 else f"{v:.1%}"  # noqa: E731  no receipts at that horizon: WAPE undefined
    md = ["# 13-week receipts forecast: rolling-origin backtest", "",
          "`python eval/forecast_backtest.py`. Each weekly origin uses only data known that day; the forecast covers receipts from "
          "invoices open at the origin. Lower is better for WAPE, MAE and |bias|.", ""]
    for r in results:
        md += [f"## {r['dataset']}", "", f"{r['invoices']} invoices, {r['buyers']} buyers, {r['period'][0]} to {r['period'][1]}; "
               f"{r['origins']} forecast origins x {r['weeks']} weeks.", "",
               "| Method | WAPE | MAE (per week) | Bias | WAPE week 1 / 4 / 13 |", "|---|---|---|---|---|"]
        for m, x in r["methods"].items():
            h = x["wape_by_horizon"]
            a = r["_actual_by_h"]
            md.append(f"| {names[m]} | {x['wape']:.1%} | {x['mae']:,.2f} | {x['bias']:+.1%} | {pctx(h[0], a[0])} / {pctx(h[3], a[3])} / {pctx(h[12], a[12])} |")
        iv = r["intervals"]
        md += ["", f"80% intervals for the v9 forecast: own Monte Carlo P10-P90 covered **{iv['v9_monte_carlo_p10_p90']:.1%}**; "
               f"split conformal **{iv['split_conformal']:.1%}** (mean width {iv['split_mean_width']:,.0f}); "
               f"adaptive conformal (ACI) **{iv['aci']:.1%}** (mean width {iv['aci_mean_width']:,.0f}).", ""]
    md += ["## Limits", "",
           "- The external data are a public IBM sample (anonymised, origin unknown) with 30-day terms only; CashBridge's own history is synthetic.",
           "- Receipts only, from invoices already issued. Bank balances, costs and new sales are not in these data, so a full cash-balance backtest still needs a real SME's ledger.",
           "- Weekly errors are correlated across origins; the figures are descriptive, not significance tests.",
           "- Interval choice: the product uses split conformal (close to 80% on both datasets). ACI reached 81% on the external data "
           "but only 74% on the short synthetic history (about 200 evaluated points), so it is reported, not used. The model's own "
           "Monte Carlo band over-covers (too wide) on the external data.",
           "- WAPE at a horizon with no receipts at all is undefined and shown as '–'."]
    path = REPORTS / "forecast_backtest.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def main() -> int:
    from scripts.fetch_external_data import fetch
    results = []
    try:
        results.append(backtest(load_ibm(fetch("ar_ibm_sample.csv")), "External: IBM accounts-receivable sample"))
    except Exception as error:  # offline: say so, never silently skip
        print(f"external dataset unavailable: {error}")
    results.append(backtest(load_cashbridge(), "CashBridge synthetic payment history", warmup_weeks=16))
    print(write(results))
    for r in results:
        print(r["dataset"], {m: (x["wape"], x["bias"]) for m, x in r["methods"].items()}, r["intervals"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
