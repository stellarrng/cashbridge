"""External validation of the buyer on-time model on public invoice data (v9).

    python eval/external_buyer_validation.py     # writes reports/external_buyer_validation.{json,md}

Question: does CashBridge's buyer payment model generalise beyond its own synthetic history, and do
the point-in-time behavioural features of Appel et al. (IBM Research; arXiv 1912.10828 and KDD MLF
workshop 2020, arXiv 2008.07363) improve it?

Label (same as the product): paid within 3 days of the due date. Prediction time: the invoice issue date.
Every feature is computed from what was known on that date: invoices of the same customer PAID before the
issue date (outcome visible), and invoices still unpaid then (counted as open, never as late or on time).

Models
  M0  portfolio base rate (point in time)
  M1  CashBridge v8: logistic on buyer identity, terms and size vs the buyer's usual invoice
  M2  v9 behavioural logistic: shrunk on-time rate of the customer's paid history (Beta prior), mean days late
      of the last 90 days, whether the last paid invoice was late, open invoices at issue, log size vs the
      customer's median, paperless billing at issue time
  M2+leak  M2 plus 'Disputed' and 'DaysToSettle' (known only after the fact) to show the leakage screen fires

Splits: (1) temporal: train on invoices whose outcome was known before 2013-01-01, test on invoices issued
from 2013-01-01; (2) unseen customers: 30% of customers (hash split) never appear in training. Metrics:
Brier, log loss, ROC-AUC, PR-AUC (late = positive class for PR), ECE, with 95% intervals from a
customer-clustered bootstrap. Public IBM sample data: indicative, not SME ground truth.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from eval.external_validation import cluster_bootstrap, leakage_screen, scores  # noqa: E402
from eval.forecast_backtest import load_ibm  # noqa: E402

REPORTS = Path(__file__).resolve().parent.parent / "reports"
GRACE = 3
CUTOFF = date(2013, 1, 1)
PRIOR = 4.0


def label(r) -> int:
    return 1 if (r["paid"] - r["due"]).days <= GRACE else 0


def point_in_time_features(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Features for every invoice using only information available on its issue date."""
    by_c: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_c[r["buyer"]].append(r)
    for lst in by_c.values():
        lst.sort(key=lambda r: r["paid"])
    paid_dates = {c: [r["paid"] for r in lst] for c, lst in by_c.items()}
    out = []
    for r in rows:
        c, t = r["buyer"], r["issue"]
        hist = by_c[c][: bisect_left(paid_dates[c], t)]  # paid strictly before the issue date
        known = [h for h in hist if h is not r]
        n = len(known)
        ontime = sum(label(h) for h in known)
        recent = [h for h in known if h["paid"] >= t - timedelta(days=90)]
        open_now = sum(1 for h in by_c[c] if h["issue"] < t and h["paid"] >= t)
        med = float(np.median([h["amount"] for h in known])) if known else r["amount"]
        out.append({**r, "y": label(r), "n_hist": n, "ontime_count": ontime,
                    "recent_days_late": float(np.mean([max(0, (h["paid"] - h["due"]).days) for h in recent])) if recent else 0.0,
                    "last_late": 1.0 if known and label(known[-1]) == 0 else 0.0,
                    "open_at_issue": float(open_now), "log_size": math.log(max(r["amount"], 0.01) / max(med, 0.01)),
                    "paperless": 1.0 if r.get("paperless_on") and r["paperless_on"] <= t else 0.0})
    return out


def shrunk_rate(d, prior_rate: float) -> float:
    return (d["ontime_count"] + PRIOR * prior_rate) / (d["n_hist"] + PRIOR)


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(C=1.0 / l2, max_iter=5000)
    m.fit(X, y)
    return m


def design_m2(ds, prior_rate, leak: bool = False):
    cols = {"shrunk_ontime_rate": [shrunk_rate(d, prior_rate) for d in ds], "recent_days_late": [d["recent_days_late"] for d in ds],
            "last_late": [d["last_late"] for d in ds], "open_at_issue": [d["open_at_issue"] for d in ds],
            "log_size": [d["log_size"] for d in ds], "paperless": [d["paperless"] for d in ds]}
    if leak:
        cols["disputed"] = [d["disputed"] for d in ds]
        cols["days_to_settle"] = [float((d["paid"] - d["issue"]).days) for d in ds]
    return cols


def v8_model_predict(train, test):
    from agents.buyer_risk_agent import BuyerRiskAgent
    hist = [{"buyer_id": d["buyer"], "amount": f"{d['amount']:.2f}", "currency": "USD", "issue_date": d["issue"].isoformat(),
             "due_date": d["due"].isoformat(), "days_late": (d["paid"] - d["due"]).days} for d in train]
    agent = BuyerRiskAgent(hist)
    return np.array([agent._probability(agent._vector(d["buyer"], (d["due"] - d["issue"]).days, d["amount"]))
                     if agent.has_history(d["buyer"]) else agent._portfolio_probability((d["due"] - d["issue"]).days, d["amount"]) for d in test])


def run_split(train, test, name) -> Dict[str, Any]:
    y_tr = np.array([d["y"] for d in train]); y_te = np.array([d["y"] for d in test])
    prior = float(y_tr.mean())
    preds: Dict[str, np.ndarray] = {"M0_base_rate": np.full(len(test), prior)}
    preds["M1_cashbridge_v8"] = v8_model_predict(train, test)
    tr_cols, te_cols = design_m2(train, prior), design_m2(test, prior)
    Xtr = np.column_stack(list(tr_cols.values())); Xte = np.column_stack(list(te_cols.values()))
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    m2 = fit_logistic((Xtr - mu) / sd, y_tr)
    preds["M2_behavioural_v9"] = m2.predict_proba((Xte - mu) / sd)[:, 1]
    # Leakage demonstration: same model with after-the-fact columns.
    tr_l, te_l = design_m2(train, prior, leak=True), design_m2(test, prior, leak=True)
    Ltr = np.column_stack(list(tr_l.values())); Lte = np.column_stack(list(te_l.values()))
    lmu, lsd = Ltr.mean(0), Ltr.std(0) + 1e-9
    leak_model = fit_logistic((Ltr - lmu) / lsd, y_tr)
    leak_scores = scores(y_te, leak_model.predict_proba((Lte - lmu) / lsd)[:, 1])
    groups = [d["buyer"] for d in test]
    late = 1 - y_te  # PR-AUC with LATE as the positive class (the event collectors act on)
    res = {"split": name, "n_train": len(train), "n_test": len(test), "test_customers": len(set(groups)),
           "shared_customers": len({d["buyer"] for d in test} & {d["buyer"] for d in train}),
           "metrics": {k: {**scores(y_te, v), "pr_auc_late": scores(late, 1 - v)["pr_auc"]} for k, v in preds.items()},
           "bootstrap_brier": cluster_bootstrap(y_te, preds, groups, metric="brier", n=500),
           "bootstrap_auc": cluster_bootstrap(y_te, preds, groups, metric="roc_auc", n=500),
           "leakage_screen_on_train": leakage_screen(y_tr, {**tr_l}),
           "leaky_model_test_metrics": leak_scores,
           "m2_coefficients": dict(zip(tr_cols, [round(float(c), 3) for c in m2.coef_[0]]))}
    return res


def load_with_extras() -> List[Dict[str, Any]]:
    import csv
    from datetime import datetime
    from scripts.fetch_external_data import fetch
    path = fetch("ar_ibm_sample.csv")
    base = load_ibm(path)
    p = lambda s: datetime.strptime(s, "%m/%d/%Y").date()  # noqa: E731
    for r, raw in zip(base, csv.DictReader(path.open(encoding="utf-8"))):
        r["disputed"] = 1.0 if raw["Disputed"] == "Yes" else 0.0
        r["paperless_on"] = p(raw["PaperlessDate"]) if raw["PaperlessBill"] == "Electronic" else None
    return base


def run() -> Dict[str, Any]:
    rows = point_in_time_features(load_with_extras())
    # temporal: train only on outcomes observable before the cutoff (due + grace passed and paid, or known late)
    temporal_train = [d for d in rows if d["issue"] < CUTOFF and (d["paid"] < CUTOFF or d["due"] + timedelta(days=GRACE) < CUTOFF)]
    temporal_test = [d for d in rows if d["issue"] >= CUTOFF]
    held = {c for c in {d["buyer"] for d in rows} if int(hashlib.sha256(c.encode()).hexdigest(), 16) % 10 < 3}
    group_train = [d for d in rows if d["buyer"] not in held and d["issue"] < CUTOFF and (d["paid"] < CUTOFF or d["due"] + timedelta(days=GRACE) < CUTOFF)]
    group_test = [d for d in rows if d["buyer"] in held and d["issue"] >= CUTOFF]
    return {"dataset": "IBM accounts-receivable sample (public; SHA-256 pinned)", "label": f"paid within {GRACE} days of due",
            "prediction_time": "invoice issue date", "splits": [run_split(temporal_train, temporal_test, "temporal (test: issued 2013)"),
                                                                 run_split(group_train, group_test, "temporal + unseen customers")]}


def write(res: Dict[str, Any]) -> Path:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "external_buyer_validation.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    names = {"M0_base_rate": "M0 base rate", "M1_cashbridge_v8": "M1 CashBridge v8 logistic", "M2_behavioural_v9": "**M2 v9 behavioural (point-in-time)**"}
    md = ["# External validation: buyer on-time model", "", f"`python eval/external_buyer_validation.py`. {res['dataset']}. "
          f"Label: {res['label']}; features computed at the {res['prediction_time']} from information available then.", ""]
    for s in res["splits"]:
        b, a = s["bootstrap_brier"], s["bootstrap_auc"]
        md += [f"## Split: {s['split']}", "", f"Train {s['n_train']} / test {s['n_test']} invoices; {s['test_customers']} test customers, "
               f"{s['shared_customers']} also in training.", "",
               "| Model | Brier (95% CI) | Log loss | ROC-AUC (95% CI) | PR-AUC (late) | ECE |", "|---|---|---|---|---|---|"]
        for k, m in s["metrics"].items():
            md.append(f"| {names[k]} | {m['brier']:.4f} ({b['ci95'][k][0]:.4f}-{b['ci95'][k][1]:.4f}) | {m['log_loss']:.4f} | "
                      f"{m['roc_auc'] if m['roc_auc'] is not None else '–'}"
                      f"{'' if a['ci95'][k] is None or m['roc_auc'] is None else f' ({a['ci95'][k][0]:.3f}-{a['ci95'][k][1]:.3f})'} | "
                      f"{m['pr_auc_late']} | {m['ece']:.4f} |")
        d = b["difference_vs_M0_base_rate"]
        md += ["", f"Brier difference vs base rate (customer-clustered bootstrap): v8 {d['M1_cashbridge_v8']}, v9 {d['M2_behavioural_v9']} "
               "(negative = better).", "",
               f"Leakage screen on training data flagged: {', '.join(f['feature'] + ' (AUC ' + str(f['single_feature_auc']) + ')' for f in s['leakage_screen_on_train']) or 'nothing'}. "
               f"A model given those after-the-fact columns would score ROC-AUC {s['leaky_model_test_metrics']['roc_auc']}: too good to be true, so they are excluded.", ""]
    md += ["## Limits", "", "- Public sample data (anonymised; 30-day terms only); not Vietnamese or Chinese SMEs.",
           "- One label definition (3-day grace). Point-in-time features need each customer's own payment history; a brand-new customer gets the base rate.",
           "- The leakage screen only flags a column that predicts the label on its own (single-feature ROC-AUC >= 0.9). It caught `days_to_settle` "
           "but would not catch a weaker after-the-fact column such as `Disputed` (recorded when a dispute is raised, often after the due date). "
           "`Disputed` is excluded by design from every model here, not because the screen found it: a screen is a check, not a guarantee."]
    path = REPORTS / "external_buyer_validation.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    r = run()
    print(write(r))
    for s in r["splits"]:
        print(s["split"], {k: (v["brier"], v["roc_auc"], v["ece"]) for k, v in s["metrics"].items()})
        print("  leak screen:", s["leakage_screen_on_train"], "leaky AUC", s["leaky_model_test_metrics"]["roc_auc"])
        print("  coef:", s["m2_coefficients"])
        print("  diff vs base:", s["bootstrap_brier"]["difference_vs_M0_base_rate"])
