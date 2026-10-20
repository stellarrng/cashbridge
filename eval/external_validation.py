"""Offline out-of-time credit model validation on user-supplied licensed CSV.

No network calls, no built-in claims of SME generalisation, no loan decisions.
Example: python -m eval.external_validation --csv data.csv --label defaulted \\
         --date observation_date --features revenue,debt_ratio,payment_delay_days \\
         --output /tmp/credit_validation.json

Expected: one dated observation per entity, no post-default/outcome features. Dataset
license, consent, sampling and geographic suitability must be documented by operator.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from datetime import date
from math import exp, log
import numpy as np


def auc(y, p):
    """ROC-AUC as Wilcoxon rank statistic including ties."""
    order=np.argsort(p)
    ranks=np.empty(len(y),dtype=float)
    idx=0
    while idx<len(y):
        end=idx+1
        while end<len(y) and p[order[end]]==p[order[idx]]: end+=1
        ranks[order[idx:end]]=(idx+1+end)/2
        idx=end
    n1=int(y.sum()); n0=len(y)-n1
    return float((ranks[y==1].sum()-n1*(n1+1)/2)/(n1*n0)) if n1 and n0 else None


def pr_auc(y, p):
    """Average precision (area under the precision-recall curve, step-wise), positive class = 1."""
    y = np.asarray(y); p = np.asarray(p, dtype=float)
    if y.sum() == 0:
        return None
    order = np.argsort(-p, kind="mergesort")
    hits = np.cumsum(y[order]); prec = hits / np.arange(1, len(y) + 1)
    return float((prec * y[order]).sum() / y.sum())


def ece(y, p, bins: int = 10):
    """Expected calibration error with equal-width bins."""
    y = np.asarray(y, dtype=float); p = np.asarray(p, dtype=float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(total)


def log_loss(y, p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6); y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def scores(y, p) -> dict:
    y = np.asarray(y, dtype=int); p = np.asarray(p, dtype=float)
    a = auc(y, p)
    return {"brier": round(float(np.mean((p - y) ** 2)), 4), "log_loss": round(log_loss(y, p), 4),
            "roc_auc": None if a is None else round(a, 4), "pr_auc": None if (z := pr_auc(y, p)) is None else round(z, 4),
            "ece": round(ece(y, p), 4), "prediction_mean": round(float(p.mean()), 4), "observed_rate": round(float(y.mean()), 4)}


def cluster_bootstrap(y, preds: dict, groups, metric: str = "brier", n: int = 1000, seed: int = 11) -> dict:
    """95% intervals for each model's metric and for its difference from the first model, resampling whole groups
    (customers) because invoices of one customer are not independent."""
    y = np.asarray(y); groups = np.asarray(groups)
    uniq = np.unique(groups); rng = np.random.default_rng(seed)
    members = {g: np.where(groups == g)[0] for g in uniq}
    names = list(preds); base = names[0]
    draws = {k: [] for k in names}; diffs = {k: [] for k in names[1:]}
    for _ in range(n):
        idx = np.concatenate([members[g] for g in rng.choice(uniq, size=len(uniq), replace=True)])
        vals = {k: scores(y[idx], np.asarray(v)[idx])[metric] for k, v in preds.items()}
        for k in names:
            draws[k].append(vals[k])
        for k in names[1:]:
            if vals[k] is not None and vals[base] is not None:
                diffs[k].append(vals[k] - vals[base])
    ci = lambda a: [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)] if a else None  # noqa: E731
    return {"metric": metric, "resampled": "customers", "n": n, "ci95": {k: ci([v for v in draws[k] if v is not None]) for k in names},
            f"difference_vs_{base}": {k: ci(diffs[k]) for k in names[1:]}}


def leakage_screen(y, columns: dict, threshold: float = 0.9) -> list:
    """Flag features that alone separate the outcome almost perfectly: usually information from after the prediction time."""
    flagged = []
    for name, x in columns.items():
        a = auc(np.asarray(y, dtype=int), np.asarray(x, dtype=float))
        if a is not None and max(a, 1 - a) >= threshold:
            flagged.append({"feature": name, "single_feature_auc": round(max(a, 1 - a), 4)})
    return flagged


def evaluate_csv(path: str|Path, label: str, date_field: str, features: list[str],
                 min_rows: int=100, group_field: str | None = None) -> dict:
    if not features or len(features)>15 or len(set(features))!=len(features):
        raise ValueError('Specify 1–15 distinct numeric input features')
    forbidden={'target','label','defaulted','outcome','chargeoff','recovery_amount','funded_after_decision'}
    if any(f.casefold() in forbidden or 'post_default' in f.casefold() for f in features):
        raise ValueError('Outcome/leakage candidate detected; remove target-related features')
    raw=[]
    with open(path,newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        if not {label,date_field,*features,*( [group_field] if group_field else [])}.issubset(set(reader.fieldnames or [])):
            raise ValueError('Missing requested CSV columns')
        for row in reader:
            if len(raw)>=100000: raise ValueError('Dataset capped at 100,000 rows')
            try:
                d=date.fromisoformat(row[date_field])
                v=float(row[label])
                x=[float(row[f]) for f in features]
                if v not in (0,1) or not all(np.isfinite(x)): raise ValueError()
            except (ValueError,TypeError):
                raise ValueError(f'Malformed value or ISO date near input row {len(raw)+2}') from None
            raw.append((d,int(v),x,row[group_field] if group_field else str(len(raw))))
    if len(raw)<min_rows: raise ValueError(f'At least {min_rows} records required')
    raw.sort(key=lambda r:r[0]); y=np.array([r[1] for r in raw],dtype=int)
    x=np.array([r[2] for r in raw],dtype=float)
    k=int(len(raw)*.7)
    while k>0 and k<len(raw) and raw[k-1][0]==raw[k][0]: k-=1
    if k<max(50,int(.4*len(raw))) or len(raw)-k<25:
        raise ValueError('Insufficient separated chronological train/test periods')
    if len(set(y[:k]))<2 or len(set(y[k:]))<2:
        raise ValueError('Both time periods need positive and negative labels')
    # Train-only standardisation: test horizon is never used to fit transformations.
    mean=x[:k].mean(axis=0); std=x[:k].std(axis=0); std[std<1e-9]=1.0
    tr=np.clip((x[:k]-mean)/std,-10,10)
    te=np.clip((x[k:]-mean)/std,-10,10)
    w=np.zeros(len(features)+1); X=np.column_stack([np.ones(k),tr]); T=np.column_stack([np.ones(len(raw)-k),te])
    for _ in range(1200):
        logits=np.clip(X@w,-25,25)
        prob=1/(1+np.exp(-logits))
        grad=X.T@(prob-y[:k])/k
        grad[1:]+=.01*w[1:]
        w-=.1*grad
    preds=1/(1+np.exp(-np.clip(T@w,-25,25)))
    test=y[k:]
    prior=float(y[:k].mean())
    def stats(p):
        out = scores(test, np.asarray(p))
        out['brier'] = round(float(np.mean((np.asarray(p)-test)**2)),6)
        return out
    groups_test = [r[3] for r in raw[k:]]
    train_groups = {r[3] for r in raw[:k]}
    shared = len({g for g in groups_test if g in train_groups}) if group_field else None
    # No raw feature rows or individual predictions are written to output.
    return {'status':'offline_out_of_time_validation','scope':'input_dataset_only',
            'n_train':int(k),'n_test':int(len(raw)-k),
            'train_through':raw[k-1][0].isoformat(), 'test_from':raw[k][0].isoformat(),
            'features':features,'baseline_constant_prevalence':stats(np.full(len(test),prior)),
            'regularized_logistic_regression':stats(preds),
            'bootstrap':cluster_bootstrap(test, {'baseline': np.full(len(test),prior), 'logistic': preds}, groups_test, n=300)
            if group_field else None,
            'entities_in_both_periods': shared,
            'leakage_screen': leakage_screen(y[:k], {f: x[:k, i] for i, f in enumerate(features)}),
            'generalizable_to_local_smes':False,
            'caveats':['This is not a calibrated SME credit decision model',
                       'Automated: chronological split, single-feature leakage screen, customer-clustered bootstrap (with group_field). '
                       'Not automated: label latency, dataset suitability and licensing',
                       'Review licenses, representative sampling, sensitive/proxy variables and model monitoring before use']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',required=True); parser.add_argument('--label',required=True)
    parser.add_argument('--date',required=True); parser.add_argument('--features',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=evaluate_csv(args.csv,args.label,args.date,[f.strip() for f in args.features.split(',') if f.strip()])
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
