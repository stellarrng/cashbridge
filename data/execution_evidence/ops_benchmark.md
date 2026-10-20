# Operations benchmark (SIMULATED)

Generated 2026-10-20T00:22:49+00:00. 100 synthetic raw events, grouped into 79 cases (21.0% fewer items). Labels come from the generator's own rule, not from the router.

| | Notify Director of every event | Director if amount ≥ USD 10k | CashBridge |
|---|---|---|---|
| Director notifications | 100 | 19 | 7 |
| Needed (label) | 4 | 4 | 4 |
| False alerts | 96 | 16 | 3 |
| Missed | 0 | 1 | 0 |
| Precision of Director alerts | 4.0% | 15.8% | 57.1% |

Ablation (switch one idea off, same events and labels):

| | Director notifications | False alerts | Missed |
|---|---|---|---|
| CashBridge | 7 | 3 | 0 |
| without the plan-in-force check (escalate on any plan change) | 11 | 7 | 0 |
| without grouping events into cases | 8 | 4 | 0 |

- Completed without a person (digest / exact matches): **23** of 79 cases
- Routed to: accountant 32, director 7, none 23, security 2, support 15
- Router agrees with the label on **96.2%** of cases
- Safety violations (side-effect flags or plans outside the policy): **0**
- Mean handling time per case (ms): support 0.0, invoice_audit 0.0, reconcile 0.0, refund 0.0, finance 551.2, overdue 0.0, cash_alert 0.0

Read with care: the events, the labels and the router are all ours. The point is that the Director sees a small number of cases that matter, with no side effects, and that every disagreement with the label is listed in the JSON for inspection.
