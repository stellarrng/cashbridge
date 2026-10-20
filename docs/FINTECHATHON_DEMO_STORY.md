# CashBridge v9 | 3-minute live demo: SME cash gap → safe financing workflow

**For:** 2026 Shenzhen FinTechathon International Track, Topic E.  
**Rubric emphasis:** Task Completion 40%, Security & Compliance 30%, Innovation & Interaction 30%.  
**Disclosure to speak clearly:** All businesses, invoices and users are SYNTHETIC. Lender, loan offers and funding outcome are MOCK. No real money moves.  
**Preparation:** Start the v9 app with `make run` (frontend is `frontend/` React build). Confirm demo accounts, test document, and browser have been reset before recording. E2E screenshot evidence lives in `reports/e2e/`.

| Time | Persona | Action in current v9 demo | One-sentence narration | Proof to show |
|---|---|---|---|---|
| 0:00–0:22 | SME / Accountant | Show the 13-week forecast and click shortfall details | "CashBridge detects the first cash-negative week, week 7, and quantifies an approximately USD 42.8k gap, with the source of the figures traceable." | `reports/e2e/01_landing.png`; `data/execution_evidence/eval_report.md`; `17_provenance_click_to_source.png` |
| 0:22–0:50 | Accountant | Run Autopilot, inspect eligible funding alternatives and create the financing pack | "Our agent evaluates funding costs and downside risk, then prepares a source-linked case. It cannot authorise its own recommendation." | `03_accountant_autopilot_pack_drafted.png`; `reports/risk_planner.md` |
| 0:50–1:14 | Director | Open Decision Center, review cost and worst-5%-gap, approve with action-bound OTP | "The Director sees the trade-off and controls release; the server refuses approval by an accountant or with the wrong code." | `04_director_decision_center.png`; `05_director_wrong_otp.png`; `06_director_released.png` |
| 1:14–1:39 | Mock lender | Open released case, Verify source hashes, ask for signed bill of lading | "The lender sees only the approved package, verifies the documents, and can request missing evidence; the decision remains blocked while a request is open." | `07_bank_inbox.png`; `tests/test_evidence_loop.py` |
| 1:39–2:09 | Accountant | Upload the actual supplemental document to the evidence request | "The file travels through the encrypted evidence vault. The server checks type, calculates SHA-256 and stores it protected; this is more than simply exchanging a hash." | `14_sme_evidence_submitted.png`; `tests/test_evidence_vault.py` |
| 2:09–2:34 | Mock lender | Open the stored file, accept evidence, record MOCK credit decision | "The lender must open the current version before accepting it. Every review action is recorded; the funding decision here is simulated." | `15_bank_evidence_accepted.png`; `08_bank_case_decided.png` |
| 2:34–2:55 | Accountant / Director | Show decision status, click source provenance and blocked-action/audit evidence | "This is an acting, bounded financial agent: the outcome is visible, the money movement is not autonomous, and a wrong action fails closed." | `09_accountant_sees_lender_decision.png`; `17_provenance_click_to_source.png`; `trust_scorecard.md` |
| 2:55–3:00 | Narrator | Point to evidence links and close | "Our archived v9 verification has 1,609 passing tests, 20/20 task cases, and 25/25 adversarial security cases." | `reports/full_pytest.txt`; `data/execution_evidence/eval_report.md`; `data/execution_evidence/trust_scorecard.md` |

## Show one refusal (swap into the flow if judges prioritise security)

- **Wrong OTP or wrong role:** accountant tries to approve, or Director enters a wrong OTP, and the action is rejected without releasing a pack. Show the audit record.
- **Unverified source:** data gate blocks financing if source evidence is missing, stale or altered. Explain that the refusal is correct task completion, not failure to act.
- **Unopened lender evidence:** lender attempts acceptance before opening the current stored version and is refused.

## Explain innovation in 15 seconds

"A basic finance dashboard shows the cash gap. A generic chatbot may describe options. CashBridge connects verified financial inputs to a risk-aware financing plan, prepares a permitted case, requests approval, receives lender feedback and provides source-level explanations while maintaining strict role boundaries."

## Benchmark notes for Q&A (not a live demo claim)

- On 40 **simulated** risk benchmark cases, the risk-aware objective lowers average CVaR95 by USD 1,571 vs the cheapest baseline while preserving the quoted cost on average (`reports/risk_planner.md`).
- The Executive Inbox misses 0/145 simulated Director-needed events across 30 seeds vs 35/145 for a simple amount threshold (`reports/ops_robustness.md`); synthetic labels, so not measured real-world performance.
- Forecasting on a **public anonymised invoice dataset** (2,466 invoices) achieves 20.9% receipt-timing WAPE vs 38.1% contractual due-date and 69.9% v8 rule (`reports/forecast_backtest.md`). This is not total-company cash-flow accuracy or SME default prediction.
- Team reports user testing has been conducted, but `reports/uat_results.csv` and `reports/uat_summary.md` were not in the received archive; present measured usability statistics **only after** attaching authentic records (`reports/UAT_EVIDENCE_STATUS.md`).

## Statements to avoid

- Do **not** say a real lender approved credit or real money was disbursed.
- Do **not** call local HTTPS checks a cloud security certification or a penetration test.
- Do **not** call synthetic benchmarks independent validations on live SMEs.
- Do **not** say the document stays in the user's browser and only a hash reaches the lender: v9 stores the encrypted uploaded file and requires the lender to view it.
- Do **not** say 617 tests or 7 browser journeys: that was a historical v8 number. The archived v9 full-suite result is **1,609 passed**. Recheck for the final exact build.

**More details:** `docs/FINTECHATHON_2026_SCORECARD.md` and `docs/SECURITY_SELF_ASSESSMENT_2026.md`.
