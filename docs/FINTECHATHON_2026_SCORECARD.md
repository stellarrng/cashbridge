# CashBridge v9 | 2026 Shenzhen FinTechathon International Track
## Topic E: SME Finance Copilot | Judge-facing rubric and evidence dossier

**Date of evidence review:** 20 October 2026  
**Status:** Functional sandbox prototype; all named companies, people, invoices, lenders and transactions in the demonstration are SYNTHETIC/MOCK.  
**Scope:** The organiser's published high-level headings are **Task Completion (40%)**, **Security & Compliance (30%)**, **Innovation & Interaction (30%)**. The organiser did **not** publish the detailed sub-weights in the supplied brief. The checkpoints and point allocations below are the **team's internal readiness checklist**, not an official scoring rubric or a claim of guaranteed marks. Topic F's 0–5 on-chain bonus **does not apply** to Topic E.

## A. Executive assessment

**Product claim (safe to present):** CashBridge is a policy-bounded SME financial copilot that detects a cash gap, compares eligible financing paths with cost and downside risk, prepares a traceable financing pack, requests Director authorisation, lets a mock lender verify and request additional evidence, and records an auditable simulated decision. It does not autonomously lend or move real money.

**High-level assessment:** A strong, working **prototype** against Topic E. It is not necessary to show a live bank, live loan disbursement, real customer data, a production penetration test or regulatory certification to demonstrate a sandbox workflow. It *is* necessary to explain that the lender is mocked and to demonstrate that the workflow and access boundaries really execute.

| Official dimension | Weight | Core question | Available proof | Evidence gap that still matters |
|---|---:|---|---|---|
| Task Completion | 40 | Can the agent finish useful SME finance tasks end-to-end, or safely decline/escalate? | 20/20 deterministic evaluation tasks; 5/5 agent scenarios; three-role Chromium flow; 11/11 reproducible demo steps; financial accuracy oracles; fault tests | Re-run on the **exact final submitted build**, include timestamp/video/link and any last-minute regression result |
| Security & Compliance | 30 | Are actions permissioned, checked, explainable, private and auditable? | 25/25 adversarial scorecard; fail-closed data gate; Director-only OTP; role/tenant isolation; server-side consent; AES-256-GCM evidence vault; 30/30 local production-mode checks | Final deployment smoke proof if a public deployment is submitted; clear distinction between demo security and production certification |
| Innovation & Interaction | 30 | Is the agent a meaningfully different financial participant, and can people use it? | Risk-aware optimisation, constrained memory/learning, first-screen role actions, interactive trace-to-source, three-language and mobile E2E, benchmark comparisons | **User tests reportedly conducted by team, but anonymised raw records and summary are missing from this archive**; attach the real results before claiming any participant count, success rate or SUS score |

### What is proven versus what is *not* proven

- **Proven by repository artifacts:** a report archived with `1609 passed` (`reports/full_pytest.txt`); `20/20` evaluation cases (`data/execution_evidence/eval_report.md`); 25/25 security cases and 5/5 agent outcomes (`data/execution_evidence/trust_scorecard.md`); 30/30 local production-mode checks (`reports/deploy_verification.md`). These are **team-generated artifacts**, not independent judge certification.
- **External-data evidence:** rolling-origin payment-receipts forecast on 2,466 public invoices improves WAPE from 38.1% (contractual-due-date baseline) and 69.9% (v8 rule) to 20.9% (v9 KM). The dataset is public/anonymised; the result is for **receipts timing**, not for real-world SME loan default or whole-company cash flow (`reports/forecast_backtest.md`).
- **Simulation evidence:** risk-aware plan lowers average CVaR95 shortfall by USD 1,571 (95% CI USD 702–2,491 improvement) against cheapest-policy baseline, with USD 0 average quoted cost change across 40 simulated quarters (`reports/risk_planner.md`). Operational triage missed 0/145 simulated Director-required events across 30 seeds versus 35/145 for the threshold baseline (`reports/ops_robustness.md`). Neither benchmark establishes field performance on real SMEs.
- **Not yet evidenced within this ZIP:** numeric user-testing results, a live deployment smoke on the final hosted URL, an independent penetration test, real bank/e-invoice integration or a licensed SME loan-default validation set. These are limitations, **not automatic failures** under the three high-level prototype criteria.

## B. Task Completion | 40 points maximum (internal checklist)

*The following allocations are proposed review prompts, not organiser sub-criteria.*

| Internal check | Possible points | Evidence to show in a live/demo recording | How to verify independently | Assessment |
|---|---:|---|---|---|
| Detect and explain liquidity gap with numbers and source | 8 | Week 7 negative cash; USD 42,831.63; cash-flow graph; click a number to inspect formula/source | `data/execution_evidence/eval_report.md` tasks `first_negative_week`, `shortfall_in_range`; `reports/e2e/17_provenance_click_to_source.png` | Demonstrated in code/evidence |
| Compare financing options with eligibility, total/annualised cost and downside | 8 | Factoring, bridge loan, early discount, policy rejections and CVaR; explicitly display `MOCK` quote | `tests/test_financial_accuracy.py`, `reports/risk_planner.md`, `data/execution_evidence/eval_report.md` | Demonstrated in code/evidence |
| Execute the multi-role flow from plan to simulated lender outcome | 12 | Accountant prepares → Director authorises with OTP → lender verifies, requests evidence, reviews → SME sees decision | `tests/e2e/test_browser_flow.py`; `reports/e2e/01_landing.png` through `09_accountant_sees_lender_decision.png`; `14_sme_evidence_submitted.png`; `15_bank_evidence_accepted.png` | Demonstrated in browser-test artifacts |
| Fail closed, escalate and recover from bad cases | 7 | Missing/unverified data blocked; wrong role or OTP blocked; incomplete lender evidence blocks a decision; no-eligible-invoice escalates | `tests/test_financing_gate.py`, `tests/test_failure_modes.py`, `data/execution_evidence/trust_scorecard.md` | Demonstrated in tests/evidence |
| Reproducibility and inspectable result | 5 | Run the demo and show case state, source hashes, generated PDF, timestamps and audit trail | `scripts/run_demo_story.py`; `data/execution_evidence/story_summary.md`; `reports/full_pytest.txt` | Archived evidence; final build re-run advised |
| **Maximum** | **40** | | | |

**Financial decision boundary:** CashBridge recommends/prepares/requests approval within a mocked financing environment. **A Director controls release; a named lender reviewer controls the credit decision.** The app must not claim autonomous approval, guaranteed funding, cash transfer, KYC completion or a validated creditworthiness score.

**Important distinction:** `67.0%` in the planner benchmark is a **simulated fraction of downside worlds with no negative week**, not the percentage of agent tasks completed. In 26/40 risk benchmark cases the target is not reachable under existing policy; transparent refusal/constraint reporting is correct task behaviour, not automatically a failed execution.

## C. Security & Compliance | 30 points maximum (internal checklist)

| Internal check | Possible points | Evidence | What to show |
|---|---:|---|---|
| Server-enforced identities, tenant and role segregation | 7 | `security/auth.py`, `tests/test_adversarial.py`, `reports/deploy_verification.md` | Accountant cannot authorise own pack; lender cannot access unreleased SME data |
| Authorisation of financial side effects | 7 | `security/otp_verifier.py`, `core/financing_gate.py`, `tests/test_financing_gate.py` | Wrong/replayed/action-mismatched OTP fails; unverified source blocks financing; no real payment permission |
| Source and decision traceability | 6 | `core/provenance.py`, `security/audit_log.py`, `reports/e2e/17_provenance_click_to_source.png` | Click a number to reach source/formula; verify audit chain; show a refusal in audit |
| Evidence protection, sharing consent and lifecycle | 6 | `workspace/evidence_vault.py`, `tests/test_evidence_vault.py`, `tests/test_privacy_lifecycle.py` | AES-256-GCM at rest; server-computed SHA-256; audited lender viewing; consent withdrawal revokes future app access |
| Threat tests and honest compliance limitations | 4 | `data/execution_evidence/trust_scorecard.md`, `reports/queue_faults.md`, `reports/deploy_verification.md`, `docs/SECURITY_SELF_ASSESSMENT_2026.md` | 25/25 attack tests; 11/11 queue faults; local HTTPS 30/30; explicitly distinguish not independently certified |
| **Maximum** | **30** | | |

**No false compliance claims:** These controls support *security and compliance by design*. They do not constitute regulatory licensing, an external security audit, anti-money-laundering clearance, actual lender compliance, or a production go-live approval.

## D. Innovation & Interaction | 30 points maximum (internal checklist)

| Internal check | Possible points | Evidence | What would strengthen it |
|---|---:|---|---|
| Novel workflow: risk-aware agent, not generic finance chat | 9 | `agents/intelligence_core.py`, `reports/risk_planner.md`, `reports/ops_robustness.md` | Side-by-side outcome versus cheapest option and simple rule-based threshold |
| Agent actions with policy boundaries and human oversight | 7 | `agents/autopilot.py`, `agents/coordinator.py`, `data/execution_evidence/trust_scorecard.md` | Live demonstration of plan → permitted tool invocation → stopped action requiring human approval |
| Explainable, multi-role interaction | 6 | `reports/e2e/04_director_decision_center.png`, `17_provenance_click_to_source.png`, `16_first_screen_*.png` | Show meaningful reasons, blocked actions and source trails without switching to developer console |
| Usability with actual participants | 5 | `docs/UAT_PROTOCOL.md`, `eval/uat_summary.py`, team-conducted testing | Attach de-identified `reports/uat_results.csv` and generated `reports/uat_summary.md`; state sample, role/task coverage, successes and failures exactly |
| Accessibility/localisation and stability in an authentic workflow | 3 | `reports/e2e/10_lang_*.png`, `11_mobile_*.png`, `tests/e2e/test_browser_flow.py` | Show EN/VI/ZH, 375 px phone, real participant feedback and resulting refinements |
| **Maximum** | **30** | | |

**Differentiation sentence:** *Unlike a generic accounting dashboard or LLM-only chatbot, CashBridge links auditable source data to a risk-aware financing decision and a permissioned, multi-party action workflow, including safe refusal and human escalation.* This is a product positioning claim, not proof that no competitors provide related features.

## E. UAT evidence: fact-preserving status

**Team statement:** User testing **has been carried out**.  
**Repository check (20 October 2026):** `docs/UAT_PROTOCOL.md`, `eval/uat_summary.py`, and `reports/uat_results_TEMPLATE.csv` exist. `reports/uat_results.csv` and `reports/uat_summary.md` **do not** exist in the received v9 ZIP. No attendee count, pass rate, time-on-task, SEQ, SUS, quotations or defects are provided in the archive.

Therefore, **do not** claim “80% unaided”, “SUS 85”, “zero severe issues” or “9 real testers” until they are backed by the actual logs. Use the neutral statement: *"We conducted user testing; the de-identified participant and task results will be attached to the final evidence set."* Once the files are attached, replace that sentence with a supported numeric summary. See `reports/UAT_EVIDENCE_STATUS.md`.

**Import/aggregate:** One row per participant and task using the existing CSV template. Put SUS answers on the first row for that participant. Then run `python eval/uat_summary.py reports/uat_results.csv`. This tool refuses an empty file; confirm the output against the underlying records before submission. If user tests followed a *different* protocol, preserve that fact and map the observed tasks only; do **not** retrofit unobserved tasks or claim they passed.

## F. Evidence bundle for judges: exact paths

| Deliverable / question | Best path to open | Status |
|---|---|---|
| What is the product and how to run it? | `README.md` (Quick Start), `Makefile` | Included |
| How does the end-to-end agent behave? | `docs/FINTECHATHON_DEMO_STORY.md`, `reports/e2e/01_*.png` to `17_*.png` | Script updated for v9, test screenshots included |
| Core financial logic and measured value | `reports/forecast_backtest.md`, `reports/risk_planner.md`, `data/execution_evidence/eval_report.md` | Included |
| Architecture/algorithms | `README.md`, `docs/RESEARCH_V9.md`, `docs/RESEARCH_AND_EVALUATION.md` | Included |
| Security self-assessment and known risks | `docs/SECURITY_SELF_ASSESSMENT_2026.md`, `docs/RUBRIC_EVIDENCE.md` | Included |
| Permission tiers / human in the loop | `security/auth.py`, `security/otp_verifier.py`, `core/financing_gate.py` | Included |
| Test and sandbox execution proof | `reports/full_pytest.txt`, `reports/BENCHMARKS.md`, `data/execution_evidence/sandbox_operation_logs.jsonl` | Archived team-run evidence |
| De-identified user test outcomes | `reports/uat_results.csv`, `reports/uat_summary.md` | **Not in received ZIP; team to attach actual observations** |
| Final deployed URL + timestamped smoke proof | `scripts/deploy_smoke.py`, `reports/deploy_verification.md` | Local HTTPS proven; hosted instance not evidenced |
| Pitch deck/video | External presentation/video files | Not included in this source archive |

## G. What a 100/100-ready evidence package would look like

This is a **target state, not a score prediction**. No team can guarantee 100/100 because judges decide how to interpret the broad dimensions.

1. **40/40-ready task proof:** One continuous 3–4 minute final-build demo shows detection, financing comparison, safe action, Director approval, lender evidence loop and a deliberate refusal. Publish test command, commit/build identifier, sandbox logs, and reproducible result.
2. **30/30-ready security proof:** A compact permission matrix and attack/refusal demo, with direct links to executed tests, documented threats, known risks and data flows. A hosted smoke report is needed **only when claiming a hosted deployment is secured**.
3. **30/30-ready innovation proof:** Compare the same SME decision against an explainable simple baseline, show an agent tool/action trace, demonstrate source-to-formula drill-down, and attach actual independent participant UAT outcomes with failures and fixes.
4. **Submission hygiene:** Every recorded numeric claim matches its report, every screenshot maps to the current v9 UI, the demo disclosure says SYNTHETIC/MOCK, and the README gives a reproducible start command. Remove/replace stale counts or historical claims from judge-facing materials.

**Priority:** Prove the final prototype reliably; do not add high-risk payment integrations, unnecessary agent modules or a fake production stack to chase a hypothetical maximum.

## H. Suggested 45-second judge response

> CashBridge is a working SME finance copilot, not a lending simulation dressed up as a chatbot. In our synthetic SME case it finds a USD 42,831.63 cash shortfall in week 7, evaluates policy-eligible financing with transparent costs and downside risks, prepares a source-linked case and stops for a Director's authorisation. A mock lender can independently verify the released evidence, ask for more documents and record a decision. We evaluate the finance calculations, end-to-end workflow, adversarial access controls and agent refusal paths. We keep real money movement outside agent authority, and clearly label mocked lender actions and the limitations of our benchmarking.

**Public competition references:** [Official 2026 competition page](https://fintechathon.g-ican.com/), [International Track description (IEEE)](https://www.ieee-cis-singapore.org/2026-fintechathon). Detailed sub-weight allocations in this document are internal, not official.
