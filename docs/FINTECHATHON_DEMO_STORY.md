# Three-minute demo (v8): from a cash gap to a lender decision, with proof at every step

Everything shown is SYNTHETIC (Binh Duong Timberworks, its buyers and invoices) and the lender is MOCK. No money moves.
The same journey runs automatically in a real browser: `make e2e` (screenshots in `reports/e2e/`).

| Time | Who | Do | Say | Proof on screen |
|---|---|---|---|---|
| 0:00 | — | Open `/`. | "13-week forecast: the company goes negative in week 7, about $42.8k short." | Landing chart; `reports/e2e/01_landing.png` |
| 0:15 | Chief accountant (`sme.lan`) | Sign in → **Autopilot** → **Run**. | "The Autopilot gathers evidence, compares funding, drafts the pack, then stops: it cannot approve." | Case tag turns *awaiting approval*; evidence table with VERIFIED / MODEL_ESTIMATE labels |
| 0:40 | Chief accountant | Open **Funding**. | "No approve button for the preparer: segregation of duties is enforced on the server, not hidden in the browser." | `03_*.png`; `tests/test_adversarial.py` |
| 0:55 | Director (`sme.minh`) | Sign in → **Decision center**. | "Each plan shows P(goal), expected cost and the worst-5% gap. The planner picks lowest cost + 0.02 × that tail among plans that meet the goal." | CVaR column; `reports/risk_planner.md` |
| 1:15 | Director | **Funding → Approve**, type a wrong code, then the right one. | "The one-time code is bound to this exact pack; five wrong codes void the challenge." | `05_*.png`, `06_*.png` |
| 1:35 | Credit reviewer (`bank.lihua`) | **Inbox** → case → **Verify**. | "The lender sees only what the Director released, and recomputes every hash itself." | 6 ✓ + 1 "cannot be proven here" (other lenders' registers) |
| 1:55 | Credit reviewer | **Evidence & collaboration** → request "Signed bill of lading". | "While this request is open, the funding decision is blocked." | "Blocking the funding decision" |
| 2:10 | Chief accountant | Same page → choose the file → **Submit evidence**. | "The browser hashes the file; the hash, not the file, goes to the case." | `14_*.png` shows the SHA-256 prefix |
| 2:25 | Credit reviewer | **Accept** with a reason → **Record decision**. | "Accepted, logged in the hash-chained audit trail; now funding can be recorded (MOCK)." | `15_*.png`, `08_*.png` |
| 2:40 | Anyone | **Audit & trust**; optionally switch to VI / 中文 or a phone. | "Every refusal and every step is in the audit chain. 617 tests, 7 browser journeys, fault injection and a production-mode check back these claims." | `docs/RUBRIC_EVIDENCE.md` |

## Optional detours (if a judge asks)

- **Data gate**: start with `CASHBRIDGE_REQUIRE_DATA_GATE=1` and no manifest → preparing a pack returns 409 and the refusal is audited. In production the gate is always on.
- **Green investment**: Green finance → *Effect on the 13-week cash buffer*: paying for the solar roof in cash drives the forecast to about −$222k; an 80% green loan limits the extra funding need to about $37k. An estimate, not a certification.
- **Executive Inbox**: `reports/ops_robustness.md`: 0 of 145 Director-needed cases missed across 30 seeds (upper 95% bound 2.6%); the USD 10k rule missed 35.

## Say these limits out loud

- All data synthetic, lender mock, no real loan or payment.
- The buyer-payment model is validated on synthetic invoices only; no external SME dataset was available.
- Production identity (OIDC/MFA), a penetration test and a cloud deployment review are not done; the smoke script for them is ready.
- The web app is the React + TypeScript project in `frontend/` (built into `frontend/dist`); there is no other UI source.
