# External validation: SME financial-distress signal

`python eval/external_distress_validation.py`. Polish Companies Bankruptcy (Tomczak 2016, UCI, CC BY 4.0; SHA-256 pinned). stratified 5-fold CV per horizon, out-of-fold metrics. Higher is better for ROC-AUC and PR-AUC; lower for Brier, log loss and ECE.

## Bankruptcy status after 5 years (polish_1year.arff)

7027 companies, 271 bankrupt (3.9%).

| Model | ROC-AUC (95% CI) | PR-AUC | Brier (95% CI) | ECE |
|---|---|---|---|---|
| Base rate | 0.499 (0.472-0.525) | 0.023 | 0.0371 (0.0330-0.0409) | 0.0000 |
| **A. CashBridge ledger ratios (DSO, DIO, gross margin)** | 0.607 (0.575-0.642) | 0.063 | 0.0368 (0.0328-0.0406) | 0.0003 |
| Altman Z'' (fixed published weights) | 0.688 (0.655-0.725) | 0.093 | 0.0368 (0.0327-0.0406) | 0.0016 |
| B. Altman ratios, refitted | 0.699 (0.666-0.730) | 0.095 | 0.0362 (0.0323-0.0399) | 0.0017 |
| C. All 64 ratios, logistic | 0.778 (0.749-0.809) | 0.253 | 0.0329 (0.0292-0.0367) | 0.0028 |
| D. All 64 ratios, boosted trees (ceiling) | 0.962 (0.950-0.973) | 0.792 | 0.0159 (0.0132-0.0188) | 0.0158 |

Missingness check: the number of missing ratios alone scores ROC-AUC 0.725; the trees with missing values hidden (median-imputed) still score 0.959, so the ceiling is not an artefact of missing data.

## Bankruptcy status after 4 years (polish_2year.arff)

10173 companies, 400 bankrupt (3.9%).

| Model | ROC-AUC (95% CI) | PR-AUC | Brier (95% CI) | ECE |
|---|---|---|---|---|
| Base rate | 0.500 (0.476-0.521) | 0.025 | 0.0378 (0.0340-0.0412) | 0.0000 |
| **A. CashBridge ledger ratios (DSO, DIO, gross margin)** | 0.590 (0.562-0.619) | 0.057 | 0.0377 (0.0339-0.0412) | 0.0004 |
| Altman Z'' (fixed published weights) | 0.645 (0.614-0.674) | 0.066 | 0.0376 (0.0339-0.0410) | 0.0006 |
| B. Altman ratios, refitted | 0.648 (0.620-0.676) | 0.064 | 0.0375 (0.0339-0.0409) | 0.0022 |
| C. All 64 ratios, logistic | 0.747 (0.719-0.773) | 0.247 | 0.0337 (0.0306-0.0367) | 0.0056 |
| D. All 64 ratios, boosted trees (ceiling) | 0.935 (0.921-0.948) | 0.711 | 0.0201 (0.0175-0.0228) | 0.0189 |

Missingness check: the number of missing ratios alone scores ROC-AUC 0.629; the trees with missing values hidden (median-imputed) still score 0.929, so the ceiling is not an artefact of missing data.

## Bankruptcy status after 3 years (polish_3year.arff)

10503 companies, 495 bankrupt (4.7%).

| Model | ROC-AUC (95% CI) | PR-AUC | Brier (95% CI) | ECE |
|---|---|---|---|---|
| Base rate | 0.500 (0.475-0.522) | 0.030 | 0.0449 (0.0410-0.0483) | 0.0000 |
| **A. CashBridge ledger ratios (DSO, DIO, gross margin)** | 0.622 (0.599-0.648) | 0.080 | 0.0445 (0.0407-0.0479) | 0.0007 |
| Altman Z'' (fixed published weights) | 0.690 (0.665-0.714) | 0.092 | 0.0447 (0.0408-0.0480) | 0.0022 |
| B. Altman ratios, refitted | 0.700 (0.677-0.723) | 0.093 | 0.0442 (0.0404-0.0476) | 0.0037 |
| C. All 64 ratios, logistic | 0.770 (0.747-0.794) | 0.231 | 0.0407 (0.0375-0.0439) | 0.0030 |
| D. All 64 ratios, boosted trees (ceiling) | 0.933 (0.920-0.945) | 0.668 | 0.0268 (0.0238-0.0298) | 0.0227 |

Missingness check: the number of missing ratios alone scores ROC-AUC 0.655; the trees with missing values hidden (median-imputed) still score 0.931, so the ceiling is not an artefact of missing data.

## Bankruptcy status after 2 years (polish_4year.arff)

9792 companies, 515 bankrupt (5.3%).

| Model | ROC-AUC (95% CI) | PR-AUC | Brier (95% CI) | ECE |
|---|---|---|---|---|
| Base rate | 0.500 (0.481-0.519) | 0.033 | 0.0498 (0.0459-0.0534) | 0.0000 |
| **A. CashBridge ledger ratios (DSO, DIO, gross margin)** | 0.644 (0.621-0.669) | 0.105 | 0.0491 (0.0453-0.0526) | 0.0019 |
| Altman Z'' (fixed published weights) | 0.697 (0.671-0.723) | 0.118 | 0.0493 (0.0456-0.0529) | 0.0022 |
| B. Altman ratios, refitted | 0.709 (0.683-0.734) | 0.131 | 0.0483 (0.0447-0.0517) | 0.0032 |
| C. All 64 ratios, logistic | 0.785 (0.762-0.809) | 0.291 | 0.0433 (0.0398-0.0466) | 0.0031 |
| D. All 64 ratios, boosted trees (ceiling) | 0.948 (0.938-0.958) | 0.747 | 0.0254 (0.0226-0.0285) | 0.0221 |

Missingness check: the number of missing ratios alone scores ROC-AUC 0.661; the trees with missing values hidden (median-imputed) still score 0.940, so the ceiling is not an artefact of missing data.

## Bankruptcy status after 1 year (polish_5year.arff)

5910 companies, 410 bankrupt (6.9%).

| Model | ROC-AUC (95% CI) | PR-AUC | Brier (95% CI) | ECE |
|---|---|---|---|---|
| Base rate | 0.500 (0.500-0.500) | 0.036 | 0.0646 (0.0596-0.0698) | 0.0000 |
| **A. CashBridge ledger ratios (DSO, DIO, gross margin)** | 0.736 (0.705-0.764) | 0.243 | 0.0594 (0.0544-0.0642) | 0.0169 |
| Altman Z'' (fixed published weights) | 0.763 (0.738-0.793) | 0.265 | 0.0602 (0.0550-0.0648) | 0.0198 |
| B. Altman ratios, refitted | 0.781 (0.753-0.809) | 0.300 | 0.0563 (0.0517-0.0605) | 0.0112 |
| C. All 64 ratios, logistic | 0.864 (0.844-0.885) | 0.492 | 0.0469 (0.0424-0.0511) | 0.0087 |
| D. All 64 ratios, boosted trees (ceiling) | 0.960 (0.949-0.970) | 0.806 | 0.0298 (0.0262-0.0341) | 0.0268 |

Missingness check: the number of missing ratios alone scores ROC-AUC 0.681; the trees with missing values hidden (median-imputed) still score 0.956, so the ceiling is not an artefact of missing data.

## What this means for CashBridge

- With only the ratios CashBridge computes from a ledger today, ROC-AUC is 0.59-0.74 across horizons; Altman Z'' (needs a balance sheet) 0.65-0.76; all 64 ratios with boosted trees 0.93-0.96.
- So the working-capital ratios carry some signal, but most of it needs balance-sheet data (assets, liabilities, retained earnings, EBIT). Before any distress indicator is used beyond a screening hint, the SME must provide a balance sheet.
- The product shows model A for the 1-year horizon as a labelled external benchmark, not a credit decision (`data/models/distress_signal.json`).

## Limits

- Polish companies 2000-2013 (mostly manufacturing), not Vietnamese or Chinese SMEs; bankruptcy is not a loan default.
- No company identifier: a company can appear in several horizon files, so horizons are evaluated separately and never used to train and test each other.
- The bootstrap interval resamples companies within one horizon; folds are stratified, not grouped by industry or year (neither is in the data).

References: Tomczak, S. (2016). Polish Companies Bankruptcy [Dataset]. UCI ML Repository, doi:10.24432/C5F600. Zieba, M., Tomczak, S. K., Tomczak, J. M. (2016). Ensemble boosted trees with synthetic features generation in application to bankruptcy prediction. Expert Systems with Applications, doi:10.1016/j.eswa.2016.04.001. Altman, E. I. (2000). Predicting financial distress of companies: revisiting the Z-score and ZETA models (Z'' weights).
