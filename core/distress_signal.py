"""Financial-distress screening hint from the ledger ratios CashBridge can compute (v9, externally validated).

Model A of eval/external_distress_validation.py: a logistic model on DSO, DIO and gross margin, trained on the public
Polish Companies Bankruptcy data (Tomczak 2016, UCI, CC BY 4.0) for the 1-year horizon. Its coefficients live in
data/models/distress_signal.json, so the product needs neither the dataset nor scikit-learn.

What it is: a screening hint that says how a company with these working-capital ratios fared in that data.
What it is not: a credit score or a decision. Out-of-sample ROC-AUC is about 0.74 at 1 year (0.59-0.64 at 2-5 years),
well below models that use a balance sheet (reports/external_distress_validation.md). The training companies are
Polish (2000-2013, mostly manufacturing), so for a Vietnamese exporter the output is out of domain by construction.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Optional

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "distress_signal.json"


def ledger_features(ledger: Any) -> Dict[str, float]:
    """The three ratios, with the dataset's definitions: DSO and DIO in days, gross margin as a fraction."""
    revenue, cogs = float(ledger.revenue_usd), float(ledger.cogs_usd)
    scale = 365.0 / float(ledger.period_days)  # the dataset's ratios are annual
    return {"Attr44": float(ledger.avg_receivables_usd) * 365.0 / (revenue * scale),
            "Attr47": float(ledger.avg_inventory_usd) * 365.0 / (cogs * scale),
            "Attr56": (revenue - cogs) / revenue}


def score(ledger: Any, model_path: Path = MODEL_PATH) -> Optional[Dict[str, Any]]:
    if not model_path.exists():
        return None
    m = json.loads(model_path.read_text(encoding="utf-8"))
    x = ledger_features(ledger)
    z, contributions, outside = m["intercept"], {}, []
    for i, name in enumerate(m["order"]):
        v = x[name]
        if not m["p01"][i] <= v <= m["p99"][i]:
            outside.append(name)
        clipped = min(max(v, m["p01"][i]), m["p99"][i])
        t = (math.copysign(math.log1p(abs(clipped)), clipped) - m["mean"][i]) / m["sd"][i]
        contributions[name] = round(m["coef"][i] * t, 4)
        z += m["coef"][i] * t
    p = 1.0 / (1.0 + math.exp(-z))
    return {"p_distress_1y": round(p, 4), "features": {k: round(v, 4) for k, v in x.items()},
            "feature_labels": m["features"], "contributions_log_odds": contributions,
            "outside_training_range": outside, "trained_on": m["trained_on"], "source": m["source"],
            "validation": m["validation"], "out_of_domain": True, "credit_decision": False,
            "limitations": ["Trained on Polish companies (2000-2013, mostly manufacturing), not Vietnamese or Chinese SMEs.",
                            "Bankruptcy within a year, not loan default.",
                            "Uses only DSO, DIO and gross margin: out-of-sample ROC-AUC about 0.74 at 1 year; models that use a "
                            "balance sheet do much better. Ask for a balance sheet before reading anything into this number."]}
