# Executive Inbox robustness (T16)

`python eval/ops_robustness.py --seeds 30`. SIMULATED events and generator-written labels; not a measurement on a real company.

## Seed sweep: 30 seeds x 100 events = 3000 events

| Router | Alerts / 100 events | False alerts / 100 events | Missed / needed | Miss rate (Wilson 95%) |
|---|---|---|---|---|
| CashBridge router | 7.1 | 2.3 | 0 / 145 | 0.0% (0.0% to 2.6%) |
| Notify on every event | 100.0 | 92.1 | 0 / 145 | 0.0% (0.0% to 2.6%) |
| Notify if amount >= USD 10,000 | 21.2 | 17.5 | 35 / 145 | 24.1% (17.9% to 31.7%) |

Seeds where CashBridge missed at least one Director-needed case: **0** of 30. Side-effect safety violations across all runs: **0**.

## Stress cases

| Scenario | Holds | Observed |
|---|---|---|
| Burst: one reserve breach reported 30 times | yes | `{"raw_events": 30, "routed": "director", "director_alerts_total": 8, "missed": 0}` |
| Critical but small: reserve missed by USD 10 next period, no amount attached | yes | `{"cashbridge": "director", "label": "director", "threshold_baseline": "other"}` |
| Flood: 40 harmless duplicates (exact reconciliations, routine tickets) | yes | `{"director_alerts_before": 7, "director_alerts_after": 7, "reconcile_routed": "none", "ticket_routed": "support"}` |

## Limits

- Labels and events come from the same generator family; zero misses here is an upper bound on real-world performance, not a guarantee.
- The upper end of the Wilson interval is the honest headline: with this many Director-needed cases, a miss rate up to that value cannot be ruled out.
- Real deployment needs a shadow period on live events with human-labelled outcomes.
