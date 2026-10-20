# Research basis and evaluation

What each CashBridge engine is built on, what it is compared against, and what we have measured. Every number below is from a
script in this repository and is **SIMULATED** unless stated otherwise: the company, buyers, lenders and outcomes are synthetic.
Re-run everything with `make story eval bench ops trust`.

Citations were checked against the publisher or an institutional repository on 20 Oct 2026. One suggested source could not be
opened and is listed under *Not cited* instead of being quoted.

## 1. Claims, in three tiers

| Tier | What it means | CashBridge items |
|---|---|---|
| **Implemented and verified** | Code in this repository, exercised by tests or an evaluation script that anyone can re-run | Deterministic 13-week forecast; scenario simulator; Intelligence Core (plan enumeration, chance-constrained choice, independent validator, feasibility certificate, CVaR reporting); buyer on-time model with walk-forward Brier score; case memory, gated learner and two-person model activation; event twin and Director inbox; operations benchmark; 3-way match and double-financing registry; signed sessions, roles, tenant scope, segregation of duties, action-bound OTP, hash-chained audit log; 28 adversarial security cases (incl. on-chain duplicate financing, anchored audit log, PDF active content) |
| **Prototype / sandbox** | Works end to end in the demo, but against mock partners or synthetic data | Factoring partner and bridge-loan catalogue (MOCK); bank portal (a mock lender, real hash re-verification); e-mail, refund and support automations (no message leaves the sandbox); Vercel / Render deployment |
| **Roadmap** | Designed or discussed, not built | Credit-risk model trained on public data (e.g. SBA 7(a)) with monotonic gradient boosting and SHAP; learned cash-flow forecaster (quantile GBM, later TFT) once real ledger history exists; layout-aware invoice extraction (DocILE-style field localisation); process-mining conformance checks on the audit log; cloud worker with retries, dead-letter queue and idempotency keys |

Nothing in the roadmap row is presented in the product as working.

## 2. Map: research → module → baseline → metric → result

| Area | Research it draws on | Module | Baseline | Metric | Result (SIMULATED unless noted) |
|---|---|---|---|---|---|
| Cash risk under uncertainty | Monte Carlo with common random numbers [Glasserman 2003]; chance-constrained programming [Charnes & Cooper 1959]; multi-stage stochastic cash management with a CVaR objective [Ferstl & Weissensteiner 2010]; stochastic programming for cash management [Castro 2009] | `core/scenario_simulator.py`, `agents/intelligence_core.py` | A. fixed workflow (one advance sized for the expected path) | Share of scenarios with no negative week; expected financing cost; CVaR 95% of the shortfall; overconfidence | 8.7% → 64.9% (B) → 66.8% (C); cost USD 960 → 4,086 → 4,012; CVaR 95% USD 180,929 → 100,057 → 98,897; overconfidence +20.6 → +19.3 → +9.3 pp (40 held-out quarters, hidden test world) |
| Is the goal reachable at all? | Upper bound by relaxation (standard in optimisation) | `IntelligenceCore.feasibility` | — | Free cash equal to the over-borrowing cap from week 1 (an upper bound for any plan inside the cap) | Bound reaches 90% in **40/40** quarters (mean 98.6%): the 0/40 result is caused by the plan space (≤ 3 packs, repayment inside 13 weeks, timing), not by too little money. Binding limits for C: combined limits 21, repayment inside the horizon 18, timing 5 |
| Probability honesty (calibration) | Proper scoring rules [Brier 1950] | `eval/planner_benchmark.py` | The planner's own world vs the hidden world | Overconfidence in the planner's own world (fresh scenarios) | −1.3 pp (B), −1.9 pp (C): the Monte Carlo is honest when its model is right, so the remaining gap in the hidden world is model error, which learning halves |
| Buyer payment behaviour | Explainable credit scoring on small-business banking data [Wang et al. 2020]; profit-sensitive evaluation [Ariza-Garzón et al. 2024] | `agents/buyer_risk_agent.py` (logistic regression, readable coefficients) | Historical on-time rate per buyer | Walk-forward Brier score | 0.0907 vs 0.1458 (37.8% better, n = 167 synthetic invoices). Gradient boosting + SHAP is roadmap: with 185 synthetic invoices a more flexible model cannot be validated |
| Learning from outcomes | Held-out model selection | `WorldModelLearner`, `ModelRegistry` | Prior world model | Leave-one-quarter-out log-likelihood; activation by a different person | Gain 0.0249 per observation, better on 7 of 8 held-out quarters; proposer ≠ approver enforced |
| Director attention | Event abstraction: grouping fine events into meaningful cases [Van Houdt et al. 2024] | `eval/ops_benchmark.py`, `assess_event` | Notify on every event; notify when amount ≥ USD 10k | Director notifications, false alerts, missed decisions | 100 / 19 / **7** notifications; missed 0 / 1 / 0; precision 4% / 15.8% / 57.1% (100 synthetic events, 79 cases) |
| Internal control evidence | Process mining of event logs for internal-control testing [Chiu & Jans 2019] | Hash-chained audit log, refused calls logged with the actor, segregation of duties in the permission matrix and the coordinator | — | Adversarial security cases | 28/28 (`make trust`). Conformance mining over the log is roadmap |
| Document evidence | Document information localisation and extraction [Šimsa et al. 2023] | 3-way match (invoice, purchase order, bill of lading), financing registry | — | Eval tasks | 20/20 deterministic tasks; layout-aware extraction is roadmap |
| Agent and AI risk | NIST AI RMF 1.0 (2023); OWASP Top 10 for LLM Applications (2025) | Gatekeeper tiers L0–L4, allow-listed actions, number lock, prompt-injection treated as data | — | Security cases mapped below | See section 5 |

## 3. The planning problem, written out

For one case, let *x* be a plan from the finite set *X* of plans the policy allows (factor 1–3 eligible invoices, the bridge loan,
loan + 1–2 invoices, with or without asking the supplier to cut a deposit, drawn in the first risky week or the first base-case
negative week). Let *B_t(x, ω)* be the closing balance in week *t* of scenario ω, and *C(x, ω)* the financing cost.

```
choose x in X to minimise  E[C(x)]
subject to                 P( min_t B_t(x) >= floor ) >= 1 - alpha     (alpha = 0.10 by default)
                           validate_plan(x) is empty                   (independent policy check)
```

* **Sample average approximation.** Probabilities and expectations are estimated on 2,000 scenarios that are the same for every
  plan (common random numbers), so differences between plans are not sampling noise. Two plans within two standard errors of
  the best are treated as equal, and the cheaper one wins.
* **Exact over a small set.** *X* has about 220 members in the demo case, so the planner enumerates instead of relaxing; there is no solver
  tolerance to explain.
* **When no plan meets the constraint**, the planner says so (`GOAL_NOT_REACHABLE`), proposes the cheapest plan within noise
  of the best, and attaches a **feasibility certificate**: the least free cash in week 1 that would reach the goal (closed form:
  the (1 − α) quantile of *floor − min_t B_t(no action)*), the over-borrowing cap, the eligible sources, and four probes that each
  relax one limit on the same scenarios (more packs inside the cap; free cash up to the cap; every eligible source; the same plan
  drawn in week 1). The probes are diagnostics. They are never offered as plans and the limits do not move.
* **CVaR 95%** (mean shortfall over the worst 5% of scenarios [Rockafellar & Uryasev 2000]) is computed for every plan and shown
  in the Decision Trace and the benchmark. It is reported, not optimised: a weighted objective *E[C] + λ·CVaR* needs a λ that a
  credit policy sets, and we do not want to pick one and call the result optimal.

**A change we tested and did not adopt.** Adding a candidate draw one or two weeks before the first risky week raised success by
0.5–1.5 points on 12 test quarters and cost about 60% more planning time. The certificate shows why it helps so little: timing
binds in only 5 of 40 quarters for the learning planner. The switch is in the code (`DRAW_LEAD`, off).

## 4. Ablation

| Idea switched off | Where measured | With | Without |
|---|---|---|---|
| Risk-aware planning (plan on many bad paths) | Planner benchmark, A vs B | 64.9% of scenarios with no negative week | 8.7% |
| Learning from outcomes | Planner benchmark, B vs C | Overconfidence +9.3 pp | +19.3 pp |
| Knowing the plan in force when re-planning | Planner benchmark, C, 3% input noise | Same plan 77.5% | 57.5% |
| Plan-in-force check before alerting the Director | Ops benchmark | 7 notifications, 3 false | 11 notifications, 7 false |
| Grouping events into cases | Ops benchmark | 7 notifications | 8 (one duplicate) |

Every idea pays for itself on the metric it targets. Grouping matters least on this event mix: few Director-level cases had
duplicate reports.

## 5. Security frameworks, mapped to controls and tests

| Risk (OWASP LLM 2025 / NIST AI RMF function) | Control in CashBridge | Test |
|---|---|---|
| LLM01 Prompt injection | Documents and e-mails are data; no free text selects a goal, tool or action | `injection_is_data` (eval), `AGENT-01/02` |
| LLM06 Excessive agency | Allow-listed transitions, gatekeeper L0–L4, no tool that pays, submits or changes a limit; planner proposals that move money are refused and logged | `AGENT-01`, `CORE-01..04` |
| LLM02 Sensitive information disclosure | Tenant scope on every request; the lender sees only released packs | `AUTH-03`, `DATA-01/02` |
| LLM09 Misinformation | Number lock: generated text may only contain numbers the engines produced | `FIN-02`, `invented_number_rejected` |
| NIST *Govern* | Segregation of duties, two-person model activation, read-only organisation policy in Settings | `SOD-01..03`, `test_registry_requires_a_different_human_and_an_accepted_gate` |
| NIST *Measure* | Trust scorecard, planner and operations benchmarks, calibration check | `make trust bench ops` |
| NIST *Manage* | Refused calls written to the hash-chained log; the Director decides plan changes (L2, named) | `EVID-01..03` |

## 6. Limits

* All outcomes come from a world model we wrote, including the hidden test world. The benchmarks show that the method corrects a
  mis-specified model in simulation; they say nothing yet about real SMEs.
* The buyer model is fitted on 185 synthetic invoices. A public dataset (SBA 7(a), LendingClub) would test the method, not the
  population: such a model would not describe Vietnamese or Chinese exporters and must not be presented as if it did.
* The operations benchmark's events, labels and router are all ours. Disagreements are listed case by case in
  `data/execution_evidence/ops_benchmark.json`.

## References

* Ariza-Garzón, M. J., Arroyo, J., Segovia-Vargas, M. J., & Caparrini, A. (2024). Profit-sensitive machine learning classification
  with explanations in credit risk: The case of small businesses in peer-to-peer lending. *Electronic Commerce Research and
  Applications*, 101428. https://doi.org/10.1016/j.elerap.2024.101428
* Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review*, 78(1), 1–3.
* Castro, J. (2009). A stochastic programming approach to cash management in banking. *European Journal of Operational
  Research*, 192(3), 963–974.
* Charnes, A., & Cooper, W. W. (1959). Chance-constrained programming. *Management Science*, 6(1), 73–79.
* Chiu, T., & Jans, M. (2019). Process mining of event logs: A case study evaluating internal control effectiveness. *Accounting
  Horizons*, 33(3), 141–156. https://doi.org/10.2308/acch-52458
* Ferstl, R., & Weissensteiner, A. (2010). Cash management using multi-stage stochastic programming. *Quantitative Finance*,
  10(2), 209–219. https://doi.org/10.1080/14697680802637908
* Glasserman, P. (2003). *Monte Carlo Methods in Financial Engineering*. Springer.
* Lim, B., Arık, S. Ö., Loeff, N., & Pfister, T. (2021). Temporal Fusion Transformers for interpretable multi-horizon time series
  forecasting. *International Journal of Forecasting*, 37(4), 1748–1764. https://doi.org/10.1016/j.ijforecast.2021.03.012
  (roadmap only)
* National Institute of Standards and Technology (2023). *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*,
  NIST AI 100-1.
* OWASP Foundation (2025). *OWASP Top 10 for Large Language Model Applications*, version 2025.
* Rockafellar, R. T., & Uryasev, S. (2000). Optimization of conditional value-at-risk. *Journal of Risk*, 2(3), 21–41.
* Šimsa, Š., et al. (2023). DocILE benchmark for document information localization and extraction. *ICDAR 2023*.
  arXiv:2302.05658 (roadmap only)
* Van Houdt, G., de Leoni, M., Martin, N., & Depaire, B. (2024). An empirical evaluation of unsupervised event log abstraction
  techniques in process mining. *Information Systems*, 121, 102320. https://doi.org/10.1016/j.is.2023.102320
* Wang, W., Lesner, C., Ran, A., Rukonic, M., Xue, J., & Shiu, E. (2020). Using small business banking data for explainable
  credit risk scoring. *Proceedings of the AAAI Conference on Artificial Intelligence*, 34(08), 13396–13401.
  https://doi.org/10.1609/aaai.v34i08.7055

**Not cited.** "A Multistage Stochastic Optimization Model for the Cash Management Problem" (Schmid, Springer *Applied
Optimization*) was suggested in review, but its page could not be opened to confirm the details. Ferstl & Weissensteiner (2010)
and Castro (2009) cover the same idea and were verified.
