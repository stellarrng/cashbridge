# External validation: buyer on-time model

`python eval/external_buyer_validation.py`. IBM accounts-receivable sample (public; SHA-256 pinned). Label: paid within 3 days of due; features computed at the invoice issue date from information available then.

## Split: temporal (test: issued 2013)

Train 1189 / test 1189 invoices; 100 test customers, 100 also in training.

| Model | Brier (95% CI) | Log loss | ROC-AUC (95% CI) | PR-AUC (late) | ECE |
|---|---|---|---|---|---|
| M0 base rate | 0.1907 (0.1703-0.2124) | 0.5701 | 0.5 (0.500-0.500) | 0.2586 | 0.0572 |
| M1 CashBridge v8 logistic | 0.1319 (0.1089-0.1565) | 0.4160 | 0.8627 (0.825-0.896) | 0.6473 | 0.0712 |
| **M2 v9 behavioural (point-in-time)** | 0.1210 (0.0993-0.1439) | 0.3800 | 0.8719 (0.836-0.906) | 0.6901 | 0.0208 |

Brier difference vs base rate (customer-clustered bootstrap): v8 [-0.0775, -0.0405], v9 [-0.0883, -0.0541] (negative = better).

Leakage screen on training data flagged: days_to_settle (AUC 1.0). A model given those after-the-fact columns would score ROC-AUC 0.9998: too good to be true, so they are excluded.

## Split: temporal + unseen customers

Train 879 / test 310 invoices; 26 test customers, 0 also in training.

| Model | Brier (95% CI) | Log loss | ROC-AUC (95% CI) | PR-AUC (late) | ECE |
|---|---|---|---|---|---|
| M0 base rate | 0.2061 (0.1544-0.2624) | 0.6025 | 0.5 (0.500-0.500) | 0.3533 | 0.0048 |
| M1 CashBridge v8 logistic | 0.2060 (0.1550-0.2617) | 0.6025 | 0.5 (0.500-0.500) | 0.3533 | 0.0021 |
| **M2 v9 behavioural (point-in-time)** | 0.1160 (0.0753-0.1547) | 0.3686 | 0.8961 (0.811-0.948) | 0.7867 | 0.0400 |

Brier difference vs base rate (customer-clustered bootstrap): v8 [-0.0007, 0.0006], v9 [-0.1418, -0.0491] (negative = better).

Leakage screen on training data flagged: days_to_settle (AUC 1.0). A model given those after-the-fact columns would score ROC-AUC 0.9999: too good to be true, so they are excluded.

## Limits

- Public sample data (anonymised; 30-day terms only); not Vietnamese or Chinese SMEs.
- One label definition (3-day grace). Point-in-time features need each customer's own payment history; a brand-new customer gets the base rate.
- The leakage screen only flags a column that predicts the label on its own (single-feature ROC-AUC >= 0.9). It caught `days_to_settle` but would not catch a weaker after-the-fact column such as `Disputed` (recorded when a dispute is raised, often after the due date). `Disputed` is excluded by design from every model here, not because the screen found it: a screen is a check, not a guarantee.
