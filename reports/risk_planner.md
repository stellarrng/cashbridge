# Risk-aware financing planner (T11)

`python eval/risk_planner_benchmark.py --cases 40`. 40 SYNTHETIC quarters, plans chosen on 800 planner paths, scored out of sample on 1500 hidden-world paths. Lower is better for every column except P(goal).

| Planner | P(goal) | P(any negative week) | CVaR95 shortfall | Expected cost | Cost + 0.02 x CVaR | Packs | Policy violations |
|---|---|---|---|---|---|---|---|
| A. Fixed rule (manual workflow) | 8.4% | 91.6% | $180,021 | $961 | $4,562 | 0.95 | 6 |
| B. Cheapest plan meeting the goal | 65.0% | 35.0% | $99,031 | $4,068 | $6,048 | 3.00 | 0 |
| C. Risk-aware (cost + 0.02 x CVaR95) | 65.9% | 34.1% | $97,461 | $4,068 | $6,017 | 3.00 | 0 |
| D. Robust (worst case over an ambiguity set) | 66.4% | 33.6% | $96,538 | $4,160 | $6,091 | 3.00 | 0 |

## Paired: risk-aware minus cheapest (bootstrap 95% interval)

- Different plan chosen in **9 of 40** cases.
- CVaR95 shortfall: **-1,571 USD** (-2,491 to -702).
- Expected financing cost: **+0 USD** (+0 to +0).
- P(goal): **+0.8%** (+0.0% to +1.0%).

Goal (90%) not reachable within policy: cheapest 26 cases, risk-aware 26 cases. In those cases the planner reports the binding limit (feasibility verdict) and does not relax the policy.

## Robust planner vs risk-aware (paired, bootstrap 95% interval)

- Different plan in **7 of 40** cases.
- P(goal) in the hidden world: **+0.6%** (+0.0% to +1.0%).
- CVaR95: **-922 USD**; expected cost: **+92 USD**.
- The ambiguity set is fixed policy (any buyer's on-time odds halve; all buyers a third worse; orders ship at 85%), not fitted to the hidden world.

## Reading this honestly

- The CVaR weight is a fixed policy value (5% tail x 40% emergency-funding cost), not tuned on these cases.
- All quarters, buyer behaviour and the hidden world are simulated; this shows the trade-off mechanism, not real-world savings.
