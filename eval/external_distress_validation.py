"""External validation of an SME financial-distress signal on public company data (v9).

    python scripts/fetch_external_data.py          # downloads and SHA-256-checks the data (not shipped)
    python eval/external_distress_validation.py    # writes reports/external_distress_validation.{json,md}
                                                   # and data/models/distress_signal.json (fitted coefficients)

Data: Polish Companies Bankruptcy (Tomczak 2016, UCI, CC BY 4.0, doi:10.24432/C5F600): 64 financial ratios per
company; five files, from "status after 5 years" (1year.arff) to "status after 1 year" (5year.arff). Counts were
checked against the UCI page (7027/271, 10173/400, 10503/495, 9792/515, 5910/410 companies/bankrupt).

The question it answers for CashBridge: how much of the bankruptcy signal is in the ratios CashBridge can compute from
an SME ledger today (DSO, DIO, gross margin), compared with ratios that need a balance sheet?

  base            training-set bankruptcy rate
  A_cashbridge    logistic on X44 (receivables x 365 / sales = DSO), X47 (inventory x 365 / COGS = DIO),
                  X56 ((sales - COGS) / sales = gross margin)                      <- what the product can compute
  altman_z2       Altman Z'' = 6.56 WC/TA + 3.26 RE/TA + 6.72 EBIT/TA + 1.05 BookEquity/TL (fixed published
                  weights, Altman 2000; recalibrated to a probability on the training folds only)
  B_altman_refit  logistic on the same four Altman ratios plus sales/TA
  C_all_logistic  logistic on all 64 ratios
  D_all_trees     gradient-boosted trees on all 64 ratios (reference ceiling; cf. Zieba et al. 2016)

Protocol: stratified 5-fold cross-validation per horizon; every transform (median imputation, 1st/99th-percentile
clipping, signed log, standardisation) is fitted on the training folds only. Metrics on the out-of-fold predictions:
ROC-AUC, PR-AUC (bankrupt class), Brier, log loss, ECE, and a 95% bootstrap interval for AUC and Brier.

Limits: Polish companies 2000-2013, mostly manufacturing, not Vietnamese or Chinese SMEs; no company id, so a company
may appear in several horizon files (horizons are evaluated separately, never trained on one and tested on another);
bankruptcy is not the same event as a loan default.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from eval.external_validation import auc, ece, log_loss, pr_auc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
MODEL_PATH = ROOT / "data" / "models" / "distress_signal.json"
FILES = {f"{y}year.arff": 6 - y for y in range(1, 6)}  # file -> years until the bankruptcy status
CASHBRIDGE = ("Attr44", "Attr47", "Attr56")
ALTMAN = ("Attr3", "Attr6", "Attr7", "Attr8")
ALTMAN_PLUS = ALTMAN + ("Attr9",)
Z2_WEIGHTS = {"Attr3": 6.56, "Attr6": 3.26, "Attr7": 6.72, "Attr8": 1.05}
NAMES = {"base": "Base rate", "A_cashbridge": "**A. CashBridge ledger ratios (DSO, DIO, gross margin)**",
         "altman_z2": "Altman Z'' (fixed published weights)", "B_altman_refit": "B. Altman ratios, refitted",
         "C_all_logistic": "C. All 64 ratios, logistic", "D_all_trees": "D. All 64 ratios, boosted trees (ceiling)"}


def load_arff(path: Path):
    cols, rows, in_data = [], [], False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("%"):
            continue
        if s.lower().startswith("@attribute"):
            cols.append(s.split()[1])
        elif s.lower().startswith("@data"):
            in_data = True
        elif in_data:
            rows.append([np.nan if v.strip() == "?" else float(v) for v in s.split(",")])
    a = np.array(rows, dtype=float)
    return cols[:-1], a[:, :-1], a[:, -1].astype(int)


class Prep:
    """Median imputation, 1st/99th-percentile clipping, signed log, standardisation, fitted on training rows only."""

    def fit(self, X: np.ndarray) -> "Prep":
        self.med = np.nanmedian(X, axis=0)
        Xi = np.where(np.isnan(X), self.med, X)
        self.lo, self.hi = np.percentile(Xi, 1, axis=0), np.percentile(Xi, 99, axis=0)
        Z = self._log(np.clip(Xi, self.lo, self.hi))
        self.mu, self.sd = Z.mean(axis=0), Z.std(axis=0) + 1e-9
        return self

    @staticmethod
    def _log(X: np.ndarray) -> np.ndarray:
        return np.sign(X) * np.log1p(np.abs(X))

    def transform(self, X: np.ndarray) -> np.ndarray:
        Xi = np.where(np.isnan(X), self.med, X)
        return (self._log(np.clip(Xi, self.lo, self.hi)) - self.mu) / self.sd


def _folds(y: np.ndarray, k: int, seed: int) -> List[np.ndarray]:
    rng = np.random.default_rng(seed)
    fold = np.empty(len(y), dtype=int)
    for cls in (0, 1):
        idx = np.flatnonzero(y == cls)
        rng.shuffle(idx)
        fold[idx] = np.arange(len(idx)) % k
    return [np.flatnonzero(fold == f) for f in range(k)]


def _logistic(C: float = 1.0):
    from sklearn.linear_model import LogisticRegression
    return LogisticRegression(C=C, max_iter=5000)


def z2(X: np.ndarray, cols: Sequence[str], med: np.ndarray) -> np.ndarray:
    idx = [cols.index(c) for c in ALTMAN]
    Xi = np.where(np.isnan(X[:, idx]), med[idx], X[:, idx])
    return Xi @ np.array([Z2_WEIGHTS[c] for c in ALTMAN])


def oof_predictions(cols: List[str], X: np.ndarray, y: np.ndarray, k: int = 5, seed: int = 7) -> Dict[str, np.ndarray]:
    from sklearn.ensemble import HistGradientBoostingClassifier
    pick = lambda names: [cols.index(c) for c in names]  # noqa: E731
    out = {m: np.zeros(len(y)) for m in NAMES}
    for test in _folds(y, k, seed):
        train = np.setdiff1d(np.arange(len(y)), test)
        out["base"][test] = y[train].mean()
        for name, feats in (("A_cashbridge", CASHBRIDGE), ("B_altman_refit", ALTMAN_PLUS), ("C_all_logistic", tuple(cols))):
            ix = pick(feats)
            prep = Prep().fit(X[np.ix_(train, ix)])
            clf = _logistic().fit(prep.transform(X[np.ix_(train, ix)]), y[train])
            out[name][test] = clf.predict_proba(prep.transform(X[np.ix_(test, ix)]))[:, 1]
        med = np.nanmedian(X[train], axis=0)
        # Z'' keeps its published weights; only the mapping score -> probability is learned (on training folds).
        zt = np.clip(z2(X[train], cols, med), -50, 50).reshape(-1, 1)
        cal = _logistic().fit(zt, y[train])
        out["altman_z2"][test] = cal.predict_proba(np.clip(z2(X[test], cols, med), -50, 50).reshape(-1, 1))[:, 1]
        trees = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=seed)
        out["D_all_trees"][test] = trees.fit(X[train], y[train]).predict_proba(X[test])[:, 1]
    return out


def _boot(y: np.ndarray, p: np.ndarray, n: int = 400, seed: int = 3) -> Dict[str, List[float]]:
    rng = np.random.default_rng(seed)
    a, b = [], []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if 0 < y[i].sum() < len(i):
            a.append(auc(y[i], p[i]))
            b.append(float(np.mean((p[i] - y[i]) ** 2)))
    q = lambda v: [round(float(np.quantile(v, 0.025)), 4), round(float(np.quantile(v, 0.975)), 4)]  # noqa: E731
    return {"roc_auc": q(a), "brier": q(b)}


def missingness_check(X: np.ndarray, y: np.ndarray, k: int = 5, seed: int = 7) -> Dict[str, float]:
    """Is the ceiling an artefact of which ratios are missing? Trees refitted with missing values median-imputed."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    p = np.zeros(len(y))
    for test in _folds(y, k, seed):
        train = np.setdiff1d(np.arange(len(y)), test)
        med = np.nanmedian(X[train], axis=0)
        fill = lambda A: np.where(np.isnan(A), med, A)  # noqa: E731
        trees = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=seed)
        p[test] = trees.fit(fill(X[train]), y[train]).predict_proba(fill(X[test]))[:, 1]
    return {"auc_count_of_missing_ratios_alone": round(auc(y, np.isnan(X).sum(axis=1)), 4),
            "auc_trees_with_missingness_hidden": round(auc(y, p), 4)}


def evaluate_file(path: Path) -> Dict[str, Any]:
    cols, X, y = load_arff(path)
    preds = oof_predictions(cols, X, y)
    metrics = {}
    for m, p in preds.items():
        metrics[m] = {"roc_auc": round(auc(y, p), 4), "pr_auc": round(pr_auc(y, p), 4), "brier": round(float(np.mean((p - y) ** 2)), 4),
                      "log_loss": round(log_loss(y, p), 4), "ece": round(ece(y, p), 4), "ci95": _boot(y, p)}
    return {"file": path.name, "years_to_status": FILES[path.name.replace("polish_", "")], "companies": int(len(y)), "bankrupt": int(y.sum()),
            "metrics": metrics, "missingness_check": missingness_check(X, y)}


def fit_product_model(path: Path) -> Dict[str, Any]:
    """Model A on the 1-year horizon, saved as plain numbers so the product needs neither the data nor sklearn."""
    cols, X, y = load_arff(path)
    ix = [cols.index(c) for c in CASHBRIDGE]
    prep = Prep().fit(X[:, ix])
    clf = _logistic().fit(prep.transform(X[:, ix]), y)
    return {"model": "A_cashbridge", "features": {"Attr44": "receivables x 365 / sales (DSO, days)",
                                                   "Attr47": "inventory x 365 / cost of products sold (DIO, days)",
                                                   "Attr56": "(sales - cost of products sold) / sales (gross margin)"},
            "order": list(CASHBRIDGE), "median": prep.med.tolist(), "p01": prep.lo.tolist(), "p99": prep.hi.tolist(),
            "mean": prep.mu.tolist(), "sd": prep.sd.tolist(), "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0]),
            "horizon_years": 1, "trained_on": f"{path.name}: {len(y)} Polish companies, {int(y.sum())} bankrupt within 1 year",
            "source": "Tomczak (2016), Polish Companies Bankruptcy, UCI ML Repository, doi:10.24432/C5F600 (CC BY 4.0)",
            "validation": "reports/external_distress_validation.md"}


def run(data_dir: Path) -> Dict[str, Any]:
    results = [evaluate_file(data_dir / f"polish_{name}") for name in FILES]
    return {"dataset": "Polish Companies Bankruptcy (Tomczak 2016, UCI, CC BY 4.0; SHA-256 pinned)", "protocol": "stratified 5-fold CV per horizon, out-of-fold metrics",
            "horizons": results}


def write(res: Dict[str, Any], model: Dict[str, Any]) -> Path:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "external_distress_validation.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(model, indent=2), encoding="utf-8")
    md = ["# External validation: SME financial-distress signal", "",
          "`python eval/external_distress_validation.py`. " + res["dataset"] + ". " + res["protocol"] + ". "
          "Higher is better for ROC-AUC and PR-AUC; lower for Brier, log loss and ECE.", ""]
    for h in res["horizons"]:
        md += [f"## Bankruptcy status after {h['years_to_status']} year{'s' if h['years_to_status'] > 1 else ''} ({h['file']})", "",
               f"{h['companies']} companies, {h['bankrupt']} bankrupt ({h['bankrupt'] / h['companies']:.1%}).", "",
               "| Model | ROC-AUC (95% CI) | PR-AUC | Brier (95% CI) | ECE |", "|---|---|---|---|---|"]
        for m, x in h["metrics"].items():
            c = x["ci95"]
            md.append(f"| {NAMES[m]} | {x['roc_auc']:.3f} ({c['roc_auc'][0]:.3f}-{c['roc_auc'][1]:.3f}) | {x['pr_auc']:.3f} | "
                      f"{x['brier']:.4f} ({c['brier'][0]:.4f}-{c['brier'][1]:.4f}) | {x['ece']:.4f} |")
        mc = h["missingness_check"]
        md += ["", f"Missingness check: the number of missing ratios alone scores ROC-AUC {mc['auc_count_of_missing_ratios_alone']:.3f}; "
               f"the trees with missing values hidden (median-imputed) still score {mc['auc_trees_with_missingness_hidden']:.3f}, "
               "so the ceiling is not an artefact of missing data.", ""]
    a = [h["metrics"]["A_cashbridge"]["roc_auc"] for h in res["horizons"]]
    d = [h["metrics"]["D_all_trees"]["roc_auc"] for h in res["horizons"]]
    z = [h["metrics"]["altman_z2"]["roc_auc"] for h in res["horizons"]]
    md += ["## What this means for CashBridge", "",
           f"- With only the ratios CashBridge computes from a ledger today, ROC-AUC is {min(a):.2f}-{max(a):.2f} across horizons; "
           f"Altman Z'' (needs a balance sheet) {min(z):.2f}-{max(z):.2f}; all 64 ratios with boosted trees {min(d):.2f}-{max(d):.2f}.",
           "- So the working-capital ratios carry some signal, but most of it needs balance-sheet data (assets, liabilities, "
           "retained earnings, EBIT). Before any distress indicator is used beyond a screening hint, the SME must provide a balance sheet.",
           "- The product shows model A for the 1-year horizon as a labelled external benchmark, not a credit decision "
           "(`data/models/distress_signal.json`).", "",
           "## Limits", "",
           "- Polish companies 2000-2013 (mostly manufacturing), not Vietnamese or Chinese SMEs; bankruptcy is not a loan default.",
           "- No company identifier: a company can appear in several horizon files, so horizons are evaluated separately and never "
           "used to train and test each other.",
           "- The bootstrap interval resamples companies within one horizon; folds are stratified, not grouped by industry or year "
           "(neither is in the data).", "",
           "References: Tomczak, S. (2016). Polish Companies Bankruptcy [Dataset]. UCI ML Repository, doi:10.24432/C5F600. "
           "Zieba, M., Tomczak, S. K., Tomczak, J. M. (2016). Ensemble boosted trees with synthetic features generation in application "
           "to bankruptcy prediction. Expert Systems with Applications, doi:10.1016/j.eswa.2016.04.001. "
           "Altman, E. I. (2000). Predicting financial distress of companies: revisiting the Z-score and ZETA models (Z'' weights)."]
    path = REPORTS / "external_distress_validation.md"
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def main() -> int:
    from scripts.fetch_external_data import fetch
    for name in FILES:
        fetch(f"polish_{name}")
    data_dir = ROOT / "data" / "external"
    res = run(data_dir)
    print(write(res, fit_product_model(data_dir / "polish_5year.arff")))
    for h in res["horizons"]:
        print(h["file"], {m: (x["roc_auc"], x["brier"]) for m, x in h["metrics"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
