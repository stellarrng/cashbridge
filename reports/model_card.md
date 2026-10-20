# Model card: buyer on-time payment model

`python eval/model_fairness.py`. SYNTHETIC history; walk-forward (each prediction uses only earlier invoices).

## What it is for, and what it is not

- **Intended use:** Expected timing of buyer payments inside the SME's 13-week cash forecast.
- **Out of scope:** Credit-scoring the SME or any person; Automatic lending decisions; Buyers in markets or sizes outside the training range.
- **Features:** buyer identity (one-hot); payment terms / 30 days; invoice size / buyer's median invoice. **Personal or protected attributes: none.**
- **Training domain:** terms 45-90 days, size 0.503-1.571x the buyer's usual invoice; outside it the explanation shows an `out_of_domain` warning.
- **Probability band:** scores are clipped to 2%-98%; the model never states certainty.

## Overall (167 walk-forward predictions)

Brier score 0.0906 with buyer identity, 0.1481 without it (lower is better).

## Calibration by market (= buyer country here)

| Group | n | Predicted on time | Observed (95% CI) | Gap | Within CI | Brier |
|---|---|---|---|---|---|---|
| CN | 27 | 88.1% | 92.6% (77%-98%) | -4.5% | yes | 0.0976 |
| JP | 18 | 96.9% | 100.0% (82%-100%) | -3.1% | yes | 0.0018 |
| US | 122 | 79.3% | 77.9% (70%-84%) | +1.5% | yes | 0.1022 |

**Confound:** Each market has exactly one buyer in this history (US 135 invoices, CN 30, JP 20), so a market effect cannot be separated from that buyer's own payment record.

Ablation without buyer identity (terms and size only). Calibration breaks for the smallest market, so the identity term carries each buyer's own payment record rather than adding noise; it is still a country proxy here and is disclosed as such:

| Group | n | Predicted on time | Observed (95% CI) | Gap | Within CI | Brier |
|---|---|---|---|---|---|---|
| CN | 27 | 82.8% | 92.6% (77%-98%) | -9.8% | yes | 0.0839 |
| JP | 18 | 64.6% | 100.0% (82%-100%) | -35.4% | **no** | 0.1516 |
| US | 122 | 83.5% | 77.9% (70%-84%) | +5.7% | yes | 0.1619 |

## Calibration by invoice size and by payment terms

| Group | n | Predicted on time | Observed (95% CI) | Gap | Within CI | Brier |
|---|---|---|---|---|---|---|
| larger than usual | 61 | 64.6% | 59.0% (46%-70%) | +5.6% | yes | 0.185 |
| smaller than usual | 73 | 96.1% | 100.0% (95%-100%) | -3.9% | yes | 0.0022 |
| usual | 33 | 86.2% | 87.9% (73%-95%) | -1.7% | yes | 0.1118 |

| Group | n | Predicted on time | Observed (95% CI) | Gap | Within CI | Brier |
|---|---|---|---|---|---|---|
| <=45 days | 33 | 84.7% | 78.8% (62%-89%) | +5.9% | yes | 0.1016 |
| >45 days | 134 | 82.1% | 83.6% (76%-89%) | -1.4% | yes | 0.0879 |

## New buyers are not penalised

A buyer with no history is scored at 96%, the portfolio average of known buyers (96%), and marked `has_history: false`.

## Every score can be explained

Example B-JP-01: intercept + contributions = 5.7772 log-odds (model: 5.7773). The lender sees this breakdown in the case view (`buyer_risk_explanation`).

## Limits

- 185 synthetic invoices from three buyers; group intervals are wide, and small groups (JP, n≈20) can look calibrated by chance.
- No external validation on real buyer payment data (harness: `eval/external_validation.py`).
- Payment timing of companies, not people: anti-discrimination rules for consumer credit do not map directly, but country effects should still be reviewed before using the score across markets.
