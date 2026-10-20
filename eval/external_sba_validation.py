"""SME loan-default validation on the U.S. SBA 7(a) loan records, when the file is available (v9).

    python eval/external_sba_validation.py [path/to/SBAnational.csv]
    -> reports/external_sba_validation.{json,md}

Data: "Should This Loan be Approved or Denied?" (Li, Mickel & Taylor, Journal of Statistics Education, 2018), the
SBA national loan records 1987-2014, label MIS_Status = CHGOFF (charged off) vs PIF (paid in full). The file is about
170 MB, cannot be downloaded from the build environment and is never shipped: attach it and pass its path (or put it at
data/external/SBAnational.csv). Without it the script says so and writes nothing; no number is invented.

Features are only what is known when the loan is approved: amount (log), SBA-guaranteed share, term, real-estate term
(>= 240 months), employees (log), new business, urban/rural, revolving line, LowDoc, franchise, industry (NAICS 2-digit).
Split by approval year (train 1995-2002, test 2003-2006), which also crosses into the 2008 recession, a realistic shift.
The leakage screen runs on post-outcome columns (ChgOffPrinGr, BalanceGross, ChgOffDate present) to show what must be
excluded: a column that alone separates the classes is information from after the decision.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from eval.external_validation import auc, ece, leakage_screen, log_loss, pr_auc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
DEFAULT_PATH = ROOT / "data" / "external" / "SBAnational.csv"
TRAIN_FY, TEST_FY = (1995, 2002), (2003, 2006)
SECTORS = ("11", "21", "22", "23", "31", "32", "33", "42", "44", "45", "48", "49", "51", "52", "53", "54", "56", "61", "62",
           "71", "72", "81")


def money(v: str) -> float:
    v = (v or "").replace("$", "").replace(",", "").strip()
    return float(v) if v else 0.0


def fy(v: str) -> Optional[int]:
    digits = "".join(ch for ch in (v or "") if ch.isdigit())
    return int(digits[:4]) if len(digits) >= 4 else None


def features(r: Dict[str, str]) -> List[float]:
    gross = money(r.get("GrAppv", ""))
    sba = money(r.get("SBA_Appv", ""))
    term = float(r.get("Term") or 0)
    naics = (r.get("NAICS") or "0")[:2]
    urban = (r.get("UrbanRural") or "0").strip()
    franchise = (r.get("FranchiseCode") or "0").strip() not in ("0", "1", "00000", "00001", "")
    return [math.log1p(gross), sba / gross if gross > 0 else 0.0, term / 12.0, 1.0 if term >= 240 else 0.0,
            math.log1p(float(r.get("NoEmp") or 0)), 1.0 if (r.get("NewExist") or "").strip().startswith("2") else 0.0,
            1.0 if urban == "1" else 0.0, 1.0 if urban == "2" else 0.0,
            1.0 if (r.get("RevLineCr") or "").strip().upper() == "Y" else 0.0, 1.0 if (r.get("LowDoc") or "").strip().upper() == "Y" else 0.0,
            1.0 if franchise else 0.0] + [1.0 if naics == s else 0.0 for s in SECTORS]


FEATURE_NAMES = ["log_amount", "sba_share", "term_years", "real_estate_term", "log_employees", "new_business", "urban", "rural",
                 "revolving_line", "low_doc", "franchise"] + [f"naics_{s}" for s in SECTORS]


def load(path: Path):
    X, y, year, post = [], [], [], {"ChgOffPrinGr": [], "BalanceGross": [], "ChgOffDate_present": []}
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            status = (r.get("MIS_Status") or "").strip().upper()
            year_ = fy(r.get("ApprovalFY", ""))
            if status not in ("CHGOFF", "P I F") or year_ is None:
                continue
            X.append(features(r))
            y.append(1 if status == "CHGOFF" else 0)
            year.append(year_)
            post["ChgOffPrinGr"].append(money(r.get("ChgOffPrinGr", "")))
            post["BalanceGross"].append(money(r.get("BalanceGross", "")))
            post["ChgOffDate_present"].append(1.0 if (r.get("ChgOffDate") or "").strip() else 0.0)
    return np.array(X, dtype=float), np.array(y), np.array(year), {k: np.array(v) for k, v in post.items()}


def metrics(y: np.ndarray, p: np.ndarray) -> Dict[str, float]:
    return {"roc_auc": round(auc(y, p), 4), "pr_auc": round(pr_auc(y, p), 4), "brier": round(float(np.mean((p - y) ** 2)), 4),
            "log_loss": round(log_loss(y, p), 4), "ece": round(ece(y, p), 4)}


def run(path: Path) -> Dict[str, Any]:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    X, y, year, post = load(path)
    tr = (year >= TRAIN_FY[0]) & (year <= TRAIN_FY[1])
    te = (year >= TEST_FY[0]) & (year <= TEST_FY[1])
    if tr.sum() == 0 or te.sum() == 0 or len(set(y[tr])) < 2:
        raise ValueError("the file has no usable loans in the train or test approval years")
    mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0) + 1e-9
    logit = LogisticRegression(C=1.0, max_iter=5000).fit((X[tr] - mu) / sd, y[tr])
    trees = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=7).fit(X[tr], y[tr])
    preds = {"base": np.full(int(te.sum()), y[tr].mean()), "logistic": logit.predict_proba((X[te] - mu) / sd)[:, 1],
             "boosted_trees": trees.predict_proba(X[te])[:, 1]}
    return {"dataset": "SBA 7(a) national loan records (Li, Mickel & Taylor 2018)", "file": path.name,
            "train": {"approval_fy": list(TRAIN_FY), "loans": int(tr.sum()), "default_rate": round(float(y[tr].mean()), 4)},
            "test": {"approval_fy": list(TEST_FY), "loans": int(te.sum()), "default_rate": round(float(y[te].mean()), 4)},
            "features": FEATURE_NAMES, "metrics": {m: metrics(y[te], p) for m, p in preds.items()},
            "leakage_screen_on_train": leakage_screen(y[tr], {k: v[tr] for k, v in post.items()}),
            "excluded_post_outcome_columns": list(post)}


def write(res: Dict[str, Any]) -> Path:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "external_sba_validation.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    md = ["# External validation: SME loan default (SBA 7(a))", "", f"`python eval/external_sba_validation.py`. {res['dataset']}.",
          f"Train: approval years {res['train']['approval_fy'][0]}-{res['train']['approval_fy'][1]}, {res['train']['loans']} loans, "
          f"default rate {res['train']['default_rate']:.1%}. Test: {res['test']['approval_fy'][0]}-{res['test']['approval_fy'][1]}, "
          f"{res['test']['loans']} loans, default rate {res['test']['default_rate']:.1%}.", "",
          "| Model | ROC-AUC | PR-AUC | Brier | Log loss | ECE |", "|---|---|---|---|---|---|"]
    for m, x in res["metrics"].items():
        md.append(f"| {m} | {x['roc_auc']} | {x['pr_auc']} | {x['brier']} | {x['log_loss']} | {x['ece']} |")
    flagged = ", ".join(f"{f['feature']} (AUC {f['single_feature_auc']})" for f in res["leakage_screen_on_train"]) or "nothing"
    md += ["", f"Leakage screen on post-outcome columns (never used as features) flagged: {flagged}.", "",
           "Limits: U.S. loans guaranteed by the SBA, not Vietnamese or Chinese SMEs; loans approved later have had less time to "
           "default; features describe the loan, not the company's invoices or ledger."]
    path = REPORTS / "external_sba_validation.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT_PATH
    if not path.exists():
        print(f"SBA file not found at {path}: NOT evaluated. Attach SBAnational.csv (Li, Mickel & Taylor 2018) and rerun.")
        return 0
    res = run(path)
    print(write(res))
    print(json.dumps(res["metrics"], indent=2), res["leakage_screen_on_train"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
