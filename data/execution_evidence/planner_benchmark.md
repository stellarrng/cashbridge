# Planner benchmark (SIMULATED)

Generated 2026-10-20T00:19:46+00:00. 40 held-out test quarters, 8 training quarters, plans evaluated on 1000 paths of the hidden test world: *hidden test world (simulated): Oakline pays later, orders slip more than stated*.

This measures planners against a world model we wrote ourselves. It shows whether learning corrects a mis-specified model in simulation; it is not evidence about real SMEs.

| Metric | A. Fixed workflow | B. Planner + memory | C. Planner + learning |
|---|---|---|---|
| Paths with no negative week (mean) | 8.7% | 64.9% | 66.8% |
| Cases reaching 90% | 0 / 40 | 0 / 40 | 0 / 40 |
| Cases reaching 80% | 0 / 40 | 2 / 40 | 2 / 40 |
| Expected financing cost (mean) | USD 960 | USD 4,086 | USD 4,012 |
| Shortfall in worst 5% of paths, CVaR 95% (mean) | USD 180,929 | USD 100,057 | USD 98,897 |
| Packs to approve (mean) | 0.9 | 3.0 | 3.0 |
| Policy violations | 6 | 0 | 0 |
| Overconfidence (predicted - realised) | +20.6 pp | +19.3 pp | +9.3 pp |
| Same plan after 3% input noise (re-plan) | 80% | 55% | 78% |
| Outcome within 5 points after 3% noise | 92% | 70% | 78% |
| Planner said goal not reachable | 0 | 27 | 40 |
| Same plan after 3% noise, re-plan WITHOUT the plan in force (ablation) | n/a | 38% | 58% |
| Overconfidence in the planner's own world (calibration check) | n/a | -1.3 pp | -1.9 pp |

## Why no planner reaches 90%: feasibility

Upper bound for ANY plan inside the over-borrowing cap, in the hidden world: free cash equal to the cap from week 1, never repaid. Mean 98.6%; cases where even this bound reaches 90%: **40 / 40**, 80%: 40 / 40.

- B. Planner + memory: certificate verdicts {'LIMITED_BY_POLICY_OR_SOURCES': 27, 'REACHABLE': 13}; binding limits {'combined_limits': 10, 'packs_per_plan': 4, 'repayment_inside_horizon': 13, 'timing': 16} (computed in the planner's own world model, one limit relaxed at a time; diagnostics, not plans).
- C. Planner + learning: certificate verdicts {'LIMITED_BY_POLICY_OR_SOURCES': 40}; binding limits {'combined_limits': 21, 'repayment_inside_horizon': 18, 'timing': 5} (computed in the planner's own world model, one limit relaxed at a time; diagnostics, not plans).

Calibration (predicted success band vs realised in the hidden world):

| Planner | Band | Cases | Predicted | Realised |
|---|---|---|---|---|
| B. Planner + memory | 60%-80% | 11 | 74.8% | 48.3% |
| B. Planner + memory | 80%-90% | 16 | 85.4% | 65.9% |
| B. Planner + memory | 90%-100% | 13 | 90.6% | 77.7% |
| C. Planner + learning | 0%-60% | 3 | 56.6% | 41.8% |
| C. Planner + learning | 60%-80% | 20 | 72.9% | 61.9% |
| C. Planner + learning | 80%-90% | 17 | 83.4% | 76.9% |

## Learning gate

Leave-one-episode-out on 8 quarters (321 observations): mean log-likelihood -0.3925 (prior) vs -0.3676 (candidate), gain 0.0249 per observation, better on 7 of 8 held-out quarters. Accepted: **True**.

Learned corrections: buyer logit shifts {'B-CN-01': 0.36, 'B-JP-01': 0.53, 'B-US-01': -0.514, 'B-US-02': 0.059}, order shipment scale 0.814 (hidden truth: B-US-01 -1.2, B-US-02 -0.4, scale 0.8; shrinkage pulls estimates toward zero).

## How to read it

* A plan sized for the expected path (A) is cheap and fails often when buyers are slower than the model thinks.
* B plans for bad paths, so it succeeds more often and costs more; it still trusts the prior model and is overconfident.
* C keeps the same rules and plan space; only the world model changed, after an offline gate. Lower overconfidence is the main point: the planner's stated probability is closer to what happens.
* All planners' plans pass the same independent policy validator; the learner cannot change limits.
