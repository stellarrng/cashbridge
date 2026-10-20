# 13-week receipts forecast: rolling-origin backtest

`python eval/forecast_backtest.py`. Each weekly origin uses only data known that day; the forecast covers receipts from invoices open at the origin. Lower is better for WAPE, MAE and |bias|.

## External: IBM accounts-receivable sample

2466 invoices, 100 buyers, 2012-01-03 to 2014-01-09; 66 forecast origins x 13 weeks.

| Method | WAPE | MAE (per week) | Bias | WAPE week 1 / 4 / 13 |
|---|---|---|---|---|
| Contractual (pay on due date) | 38.1% | 167.59 | -0.0% | 17.8% / 77.6% / – |
| CashBridge v8 rule | 69.9% | 307.31 | +0.0% | 57.2% / 30.7% / – |
| **v9: Kaplan-Meier, pooled (used)** | 20.9% | 91.84 | -0.1% | 14.6% / 20.9% / – |
| Variant: Kaplan-Meier per buyer, shrunk (not used) | 22.2% | 97.69 | -0.1% | 17.9% / 22.1% / – |

80% intervals for the v9 forecast: own Monte Carlo P10-P90 covered **87.1%**; split conformal **80.6%** (mean width 328); adaptive conformal (ACI) **81.0%** (mean width 323).

## CashBridge synthetic payment history

185 invoices, 3 buyers, 2025-10-21 to 2026-12-21; 32 forecast origins x 13 weeks.

| Method | WAPE | MAE (per week) | Bias | WAPE week 1 / 4 / 13 |
|---|---|---|---|---|
| Contractual (pay on due date) | 44.9% | 30,318.66 | +0.6% | 28.8% / 43.0% / 79.3% |
| CashBridge v8 rule | 46.4% | 31,327.84 | -3.0% | 35.7% / 42.9% / 122.9% |
| **v9: Kaplan-Meier, pooled (used)** | 42.6% | 28,778.32 | +0.2% | 24.1% / 42.6% / 85.2% |
| Variant: Kaplan-Meier per buyer, shrunk (not used) | 43.1% | 29,099.27 | +0.2% | 23.9% / 42.9% / 81.8% |

80% intervals for the v9 forecast: own Monte Carlo P10-P90 covered **80.8%**; split conformal **80.1%** (mean width 92,953); adaptive conformal (ACI) **74.0%** (mean width 86,797).

## Limits

- The external data are a public IBM sample (anonymised, origin unknown) with 30-day terms only; CashBridge's own history is synthetic.
- Receipts only, from invoices already issued. Bank balances, costs and new sales are not in these data, so a full cash-balance backtest still needs a real SME's ledger.
- Weekly errors are correlated across origins; the figures are descriptive, not significance tests.
- Interval choice: the product uses split conformal (close to 80% on both datasets). ACI reached 81% on the external data but only 74% on the short synthetic history (about 200 evaluated points), so it is reported, not used. The model's own Monte Carlo band over-covers (too wide) on the external data.
- WAPE at a horizon with no receipts at all is undefined and shown as '–'.
