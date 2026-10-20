# Reproducible evidence index (T08)

Generated 2026-10-20T11:52:50+00:00 by `python eval/reproduce_all.py` (Python 3.13.16, commit 90ca594). All data SYNTHETIC; lender MOCK.

| Step | Result | Sample / seed | Time | Limitation |
|---|---|---|---|---|
| `python scripts/run_demo_story.py` | 11/11 story steps hold; 73 hash-chained audit lines; byte-identical on every run | 11 steps / simulated clock 07:00 UTC, seeded SYNTHETIC inputs | 3.2 s | SYNTHETIC case; MOCK lender. |
| `python eval/run_eval.py` | 20/20 evaluation tasks pass | 20 / deterministic | 6.7 s | Task suite written by the team. |
| `python eval/planner_benchmark.py` | P(goal) realised in hidden world: fixed 8.7%, planner+memory 66.2%, planner+learning 67.0% | 40 cases x 1000 paths / cases 99, train 7, eval 50000+k | 175.9 s | Simulated quarters and a simulated hidden world. |
| `python eval/ops_benchmark.py` | 100 events -> 7 Director alerts, 0 missed of 4 needed | 100 / 42 | 11.8 s | Generator-written labels; one seed (see robustness). |
| `python eval/trust_scorecard.py` | security 28/28, agent 5/5, Brier 0.0907 vs baseline 0.1458 (n=167) | 167 / walk-forward on synthetic invoices | 32.6 s | Adversarial cases chosen by the team; synthetic invoices for the model. |
| `python eval/risk_planner_benchmark.py --cases 40` | risk-aware vs cheapest: CVaR95 -1,571 USD (95% CI -2,491 to -702), cost change +0 USD; robust vs risk-aware: P(goal) +0.6%, CVaR95 -922, cost +92 USD | 40 cases x 1500 out-of-sample paths / cases 99, eval 90000+k | 100.8 s | CVaR weight fixed by policy, not tuned; simulated. |
| `python eval/ops_robustness.py --seeds 30` | missed 0/145 (Wilson 95% upper 2.6%); threshold baseline missed 35/145; stress 3/3 | 30 seeds x 100 events / 1..30 | 267.2 s | Same generator family; real events need a shadow period. |
| `python eval/queue_faults.py` | 11/11 fault scenarios hold their invariant | 11 / deterministic | 1.5 s | SQLite on one host; MOCK provider. |
| `python eval/model_fairness.py` | calibrated within 95% CI in 8/8 groups; Brier 0.0906 (without buyer identity 0.1481); no personal attributes | 167 / walk-forward | 6.2 s | 185 synthetic invoices, one buyer per market (buyer and country effects confounded). |
| `python scripts/fetch_external_data.py` | public IBM AR sample downloaded and SHA-256 verified (not redistributed) | 1 file / pinned hash | 0.2 s | Public anonymised sample; licence unclear, so it is downloaded, hash-checked and never packaged. |
| `python eval/forecast_backtest.py` | External: WAPE v8 rule 69.9% -> v9 KM 20.9% (contractual 38.1%); 80% interval coverage split 80.6%, ACI 81.0%; CashBridge synthetic payment history: WAPE v8 rule 46.4% -> v9 KM 42.6% (contractual 44.9%); 80% interval coverage split 80.1%, ACI 74.0% | 66 origins / 2466 invoices, 32 origins / 185 invoices / rolling origin, weekly | 19.0 s | Receipts only (no costs or new sales); external sample has 30-day terms only. |
| `python eval/external_buyer_validation.py` | temporal (test: issued 2013): AUC v8 0.8627 vs v9 0.8719, Brier 0.1319 vs 0.121, ECE 0.0712 vs 0.0208; temporal + unseen customers: AUC v8 0.5 vs v9 0.8961, Brier 0.206 vs 0.116, ECE 0.0021 vs 0.04 | 2,466 public invoices, 100 customers / customer-clustered bootstrap 500 | 16.0 s | Public sample, not Vietnamese or Chinese SMEs; one label definition. |
| `python eval/external_distress_validation.py` | bankruptcy ROC-AUC over 5 horizons: CashBridge ledger ratios 0.59-0.74, Altman Z'' 0.65-0.76, all 64 ratios (trees) 0.93-0.96 | 43405 company-years (Polish, UCI) / stratified 5-fold CV, seed 7 | 316.1 s | Polish companies 2000-2013; bankruptcy, not loan default; screening hint, not a credit model. |
| sba_default | skipped (data file SBAnational.csv not present: NOT evaluated) | | | |
| `python scripts/verify_deployment_local.py` | 30/30 production-mode checks over local HTTPS | 30 / fresh secrets each run | 47.7 s | Local HTTPS, not a cloud provider; no pentest. |

Detailed reports: `reports/forecast_backtest.md`, `reports/external_buyer_validation.md`, `reports/risk_planner.md`, `reports/ops_robustness.md`, `reports/queue_faults.md`, `reports/deploy_verification.md`, `data/execution_evidence/*.md`.
