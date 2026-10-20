# Rubric evidence map (v9, 2026 FinTechathon Topic E)

Every claim CashBridge makes to the judges, with the code that implements it, the test that would fail
if it stopped being true, the report or screenshot that shows it, and what it does **not** prove.
All companies, people, invoices and lenders are SYNTHETIC; the lender and payment rails are MOCK.

**Rubric weights (as supplied by the organiser):** Task Completion 40%, Security & Compliance 30%, Innovation & Interaction 30%. These are the only published breakdown numbers used here; see the expanded [judge-facing scorecard](FINTECHATHON_2026_SCORECARD.md). Prototype sandbox workflows are not penalised merely for lacking real lending/payment integrations.

**User-testing status:** The team says user testing has been conducted. The received v9 ZIP has not included the anonymised raw results or an aggregate report, so quantitative UAT outcomes cannot yet be asserted. See [`reports/UAT_EVIDENCE_STATUS.md`](../reports/UAT_EVIDENCE_STATUS.md).

Re-run everything from a clean checkout:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt -r requirements-e2e.txt
make test-report        # full regression -> reports/full_pytest.txt (1609 passed, exit 0 at the time of writing)
make e2e                # real Chromium: 10 browser tests, screenshots in reports/e2e/
make evidence           # every benchmark + fault injection -> reports/BENCHMARKS.md, reports/EVIDENCE_INDEX.json
make deploy-check       # PRODUCTION mode over local HTTPS, restart, log scan -> reports/deploy_verification.md
```

## 1. Task Completion (40%)

| Claim | Source | Test that guards it | Evidence | Limitation |
|---|---|---|---|---|
| The full three-role journey works in a real browser: accountant drafts with the Autopilot, Director approves with an action-bound OTP, lender verifies hashes and records a decision, SME sees the result | `frontend/src/features/*` (React), `api/main.py` | `tests/e2e/test_browser_flow.py::test_full_three_role_journey` | `reports/e2e/01…09_*.png` | Chromium only (no Safari/Firefox run) |
| Director can send a pack back with a reason; accountant reworks it | `frontend/src/` (React), `coordinator.reject_pack` | `test_director_sends_pack_back_and_accountant_reworks` | `reports/e2e/12_*.png`, `13_*.png` | — |
| The demo is reproducible: two fresh servers produce the same pack id, metrics, bundle hash, letter, PDF bytes and lender checks | `scripts/run_demo_story.py` (`StoryClock`) | `tests/test_demo_reproducible.py`, `tests/test_demo_story.py::test_story_output_is_byte_identical_on_every_run` | `data/execution_evidence/story_summary.md` | Simulated clock and seed |
| Every figure in the cover letter is a locked metric | `security/number_check.py` | `test_every_number_in_the_cover_letter_is_a_locked_metric` | pack PDF | Checks numbers, not wording |
| The planner chooses with tail risk, not only reports it: objective = expected cost + 0.02 × CVaR95, among plans meeting P(goal) | `agents/intelligence_core.py` (`OBJECTIVES`, `CVAR_WEIGHT`) | `tests/test_risk_planner.py` | `reports/risk_planner.md`: CVaR95 −1,571 USD (95% CI −2,491 to −702), cost +0, out of sample on 40 quarters | Simulated quarters and hidden world; weight fixed by policy, not tuned |
| When 90% is unreachable the planner says which limit binds and never relaxes policy | `IntelligenceCore.feasibility` | `test_small_out_of_sample_benchmark_never_worse_on_tail_and_never_breaks_policy` | `reports/risk_planner.md` (26/40 cases "goal not reachable", same for both objectives) | — |
| Lender ↔ SME evidence loop: request → document bound by SHA-256 → reject with reason → resubmit → accept; revoke; expiry; funding blocked until resolved | `workspace/store.py` (`EvidenceDesk`), `api/main.py` `/api/workspace/cases/{id}/evidence*` | `tests/test_evidence_loop.py`, `test_lender_evidence_loop_in_the_browser` | `reports/e2e/14_*.png`, `15_*.png` | In-app notifications only; no email |
| Green investment shown against the 13-week cash buffer: cash-funded vs green-loan-funded, extra funding needed | `core/green_finance.py` (`green_cash_impact`) | `tests/test_green_cash_impact.py` | Green page → "Effect on the 13-week cash buffer" | Estimate; no tariff path, degradation or tax; not a certification |
| Full regression completes and is diagnosable if it hangs | `pytest.ini` (`faulthandler_timeout`), `Makefile` `test-report` | the suite itself | `reports/full_pytest.txt` (1609 passed, 9 min incl. browser tests) | — |
| Every money formula matches an independent exact-arithmetic oracle (APR, discount APR, interest, FX, forecast identities, CVaR, CCC, Wilson, Brier, annuity); planner and engine quote the same cents | `tests/test_financial_accuracy.py` oracles | 726 cases | `docs/FINAL_AUDIT_AND_ACCEPTANCE.md` §1 | Conventions: simple annualised cost, Actual/365 |
| Dependency failures are handled: lender timeout sends nothing and says so; PDF failure after submission is not misreported; NaN/Infinity refused; missing data → 503; unexpected errors → incident id | `agents/coordinator.py`, `api/main.py` | `tests/test_failure_modes.py` (17) | `docs/FINAL_AUDIT_AND_ACCEPTANCE.md` §4 | — |

## 2. Security & Compliance (30%)

| Claim | Source | Test | Evidence | Limitation |
|---|---|---|---|---|
| Data Reliability Gate fails closed on **every** financing route (prepare, `/packs`, Autopilot execute, approve, `/packs/{id}/approve`, lender APPROVE_FUNDING); always on in production | `core/financing_gate.py`, `api/main.py` `enforce_verified_data_gate` | `tests/test_financing_gate.py` (21 cases: missing, stale, future-dated, mismatched, unverified, forged, edited, expired, wrong key, unreadable) | refusals in the audit chain | v7 left `/packs` and lender approval ungated; fixed in v8 |
| A manifest cannot vouch for itself: verification comes only from HMAC-signed attestations bound to source id, type, as-of date and document hash | `core/source_attestation.py`, `scripts/attest_source.py` | `test_self_declared_verification_is_not_accepted`, `test_forged_or_outdated_attestations_do_not_count` | — | HMAC integrity, not PKI; proves the key holder attested, not that the document is authentic |
| Tenant isolation and role boundaries hold against correctly signed sessions of the wrong tenant/role | `security/auth.py`, `api/main.py` `_portal` | `tests/test_adversarial.py` (35 cases) | — | Single SME tenant in the demo |
| OTP: action-bound, single use, brute-force cap (challenge voided after 5 wrong codes) | `security/otp_verifier.py`, `agents/coordinator.py` | `test_otp_brute_force_voids_the_challenge`, `test_otp_replay_after_release_is_refused`, `test_otp_is_bound_to_the_exact_pack` | — | TOTP demo secret is public in DEMO mode only |
| Sign-in throttle cannot be bypassed by rotating `X-Forwarded-For`; per-account limit behind a trusted proxy | `security/auth.py` (`client_key`, `trust_proxy_headers`) | `test_rotating_x_forwarded_for_does_not_bypass_the_sign_in_throttle` | — | v9: counters shared by all worker processes on a host (SQLite); per instance on serverless |
| Message kinds are bound to the sender's role (a bank cannot "respond" as the SME) | `api/main.py` `MESSAGE_KINDS_BY_PORTAL` | `test_message_kinds_are_bound_to_the_sender_role` | — | — |
| Request bodies over 6 MB refused before parsing; no stack traces leak | `api/main.py` middleware | `test_oversized_and_lying_bodies_are_refused_early`, `scripts/deploy_smoke.py` | `reports/deploy_verification.md` | Chunked bodies without Content-Length rely on the ASGI server limits |
| Queue: bounded retry with backoff, DLQ, stale-lease recovery, zombie workers cannot overwrite results, concurrent workers process each job exactly once | `automation/engine.py` (lease token) | `tests/test_queue_faults.py` | `reports/queue_faults.md` (11/11) | SQLite on one host |
| External effects use a transactional outbox + provider idempotency key; crash after provider accept does not double the effect; non-mock providers refused | `automation/outbox.py` | `outbox_crash_after_provider_accept_is_not_doubled`, `real_providers_are_refused` | `reports/queue_faults.md` | Only a MOCK provider exists |
| Production mode: HTTPS + HSTS, CSP, no demo accounts/OTP secret/API docs, CORS closed, 401 on every protected route, sessions survive restart, evidence archived with intact hash chain, logs free of secrets and personal names | `config/runtime_mode.py`, `api/main.py`, `agents/coordinator.py` (`_archive_evidence`) | `tests/test_deploy_checks.py`, `scripts/verify_deployment_local.py` | `reports/deploy_verification.md` (30/30 in v9, incl. 3 worker processes) | Local TLS with a throw-away CA; not a cloud provider review; Docker image not built in the verification sandbox (registry blocked) |
| v9: the document itself travels through CashBridge: type checked by its bytes, SHA-256 computed by the server, stored AES-256-GCM (bound to tenant/case/file), re-hashed on every read, opened only through an audited viewer; Accept refused until the lender has opened the current version; deleted on consent withdrawal | `workspace/evidence_vault.py`, `workspace/store.py` (`record_view`, `review`), `api/main.py` `/upload`, `/file` | `tests/test_evidence_vault.py`, `test_lender_evidence_loop_in_the_browser` | `reports/e2e/14_*.png`, `15_*.png` | Key in an environment variable, not an HSM/KMS; no malware scan of uploads |
| Consent can be withdrawn before the lender decides; the lender loses access at once | `coordinator.withdraw_release`, `POST /api/withdraw_release` | `tests/test_privacy_lifecycle.py` | — | Copies already downloaded by the lender must be deleted on their side (notice sent) |
| Data inventory, export per organisation, retention purge that keeps record-keeping data | `core/privacy_lifecycle.py`, `scripts/privacy_tool.py` | `tests/test_privacy_lifecycle.py` | — | Retention periods to confirm with counsel |
| Buyer-payment model: no personal attributes, explanations that add up, calibrated in 8/8 groups, out-of-domain flags, confound disclosed | `agents/buyer_risk_agent.py` (`explain`, `domain`), `eval/model_fairness.py` | `tests/test_model_audit.py` | `reports/model_card.md` | 185 synthetic invoices; one buyer per market |
| Shared static bank token refused in production | `security/role_access.py`, `config/runtime_mode.py` | `test_static_bank_token_is_refused_in_production` | — | — |
| Every refused call and every evidence transition is in the hash-chained audit log | `security/audit_log.py`, `api/main.py` (`record_denials`, `audit_evidence`) | `test_audit_chain_survives_the_attacks`, `test_full_loop_with_rejection_and_resubmission` | `/audit/verify` | Chain is per installation; anchor externally for non-repudiation |

## 3. Innovation & Interaction (30%)

| Claim | Source | Test | Evidence | Limitation |
|---|---|---|---|---|
| Executive Inbox is quiet and complete across seeds, not just seed 42: 0/145 Director-needed cases missed over 30 seeds (Wilson 95% upper bound 2.6%) vs 35/145 for the USD 10k threshold rule | `eval/ops_robustness.py` | `tests/test_ops_robustness.py` | `reports/ops_robustness.md` | Same generator family for events and labels |
| Burst (30 reports of one breach → one alert), critical-but-small (USD 10 below reserve → Director), harmless flood (no extra alerts) | `eval/ops_robustness.py` (`stress`) | `test_stress_cases_hold` | `reports/ops_robustness.md` | Simulated |
| Director sees tail risk for each plan ("Worst-5% gap, lower is better") | `frontend/src/features/decision-center/` | browser E2E (no JS errors, no raw keys) | `reports/e2e/04_*.png` | — |
| EN / VI / 中文 everywhere, no raw translation keys | `frontend/src/` translation layer | `test_languages_render_without_raw_keys` (5 pages × 3 languages) | `reports/e2e/10_lang_*.png` | Engine-generated text (letters, evidence) stays English by design |
| Works on a 375 px phone without horizontal page scroll; sidebar no longer hides "Sign out" | `frontend/src/` styles (v9 React) | `test_phone_viewport_has_no_horizontal_scroll`, sidebar check in the journey test | `reports/e2e/11_mobile_*.png` | — |
| Strict CSP holds in the browser (`script-src 'self'`, no eval) | `api/main.py` security headers | E2E runs under CSP (helper polls with `evaluate`, never `eval`) | — | `style-src 'unsafe-inline'` still allowed for inline styles |
| Each role's next action is on the first screen (laptop and 375 px phone) | `frontend/src/features/overview/` (Next step card, work queue) | `test_each_roles_next_action_is_on_the_first_screen` | `reports/e2e/16_*.png` | Pre-condition for guidance-free use, not a user study |
| Real user testing: team confirms completed; quantitative evidence not supplied in v9 ZIP. Empty results cannot be summarised into invented numbers. | `docs/UAT_PROTOCOL.md`, `eval/uat_summary.py` | `tests/test_uat_summary.py` | `reports/UAT_EVIDENCE_STATUS.md`; **attach real `reports/uat_results.csv` and `reports/uat_summary.md` when provided** | Participant count, role coverage, scores and findings are **not yet verifiable from this archive** |

## 4. v9 additions (models, provenance, integration)

| Claim | Source | Test | Evidence | Limitation |
|---|---|---|---|---|
| Receipts forecast backtested by rolling origin against baselines: WAPE 69.9% (v8 rule) → 20.9% (v9 Kaplan–Meier) on 2,466 public invoices; 46.4% → 42.6% on the synthetic history | `core/payment_timing.py`, `eval/forecast_backtest.py` | `tests/test_v9_models.py` | `reports/forecast_backtest.md` | Receipts only; public sample with 30-day terms |
| Forecast error bands are calibrated, not assumed: split conformal covered 80.6% / 80.1% at an 80% target | `core/conformal.py` | `test_split_conformal_quantile_and_aci_update`, `test_aci_reaches_target_coverage_under_drift` | `reports/forecast_backtest.md` | ACI under-covered on the short synthetic history, so it is not used |
| Buyer model generalises to unseen customers (ROC-AUC 0.896 vs v8 0.500) and is better calibrated in time (ECE 0.021 vs 0.071), with customer-clustered CIs and a leakage screen | `agents/buyer_behaviour.py`, `eval/external_buyer_validation.py` | `tests/test_v9_models.py` (skips without the data) | `reports/external_buyer_validation.md` | Public anonymised sample; second opinion, not a credit decision |
| Robust planner (finite ambiguity set) and a stress test of every chosen plan | `agents/intelligence_core.py` | `tests/test_risk_planner.py` | `reports/risk_planner.md`: P(goal) +0.6 pp (0 to +1.0), CVaR −922, cost +92 | Small gain; risk-aware stays the default |
| Financing timeline counted once: quote = drawdown = settlement, rebate replaces the invoice receipt, on-time / late / default, recourse vs non-recourse | `core/funding_schedule.py` | `tests/test_funding_schedule.py` (150 generated cases) | Funding page "Funding timeline" | Simple Actual/365 convention |
| Click any locked number → formula, inputs, source file/JSON path/SHA-256 or scan page/line/character span/excerpt/confidence; no invented bounding boxes; four-eyes corrections never change a locked pack | `core/provenance.py`, `workspace/corrections.py`, `frontend/src/entities/provenance/ProvenanceDialog.tsx` | `tests/test_provenance.py`, E2E `test_click_a_pack_number_to_see_its_source_and_correct_it_four_eyes` | `reports/e2e/17_provenance_click_to_source.png` | Text-layer scans only; no OCR coordinates |
| Lender adapter: neutral quotes, mock vs sandbox by config, timeout + idempotent retry, refused malformed quotes, signed/deduplicated webhooks, expiry, simulated vs provider-issued labels | `api/lender_adapters.py` | `tests/test_lender_adapters.py` (18) | Funding page "Lender quotes" | No real lender API called |
| SME distress screen validated on public company data: ROC-AUC 0.74 at 1 year with the ratios CashBridge computes, vs Altman Z'' 0.76 and a balance-sheet ceiling of 0.96; shown as an external benchmark, never a credit decision | `core/distress_signal.py`, `eval/external_distress_validation.py` | `tests/test_distress_signal.py` | `reports/external_distress_validation.md` | Polish companies 2000-2013; bankruptcy, not loan default; SBA loan-default harness ready but not run (file not downloadable here) |
| Sign-out, sign-out everywhere and the throttle hold across worker processes | `security/auth.py` (`SqliteSessionState`) | `tests/test_shared_sessions.py` | `reports/deploy_verification.md` (3 workers) | Not shared across serverless instances; no OIDC/MFA |

Research basis with references: [RESEARCH_V9.md](RESEARCH_V9.md). Status against the reviews: [V9_IMPLEMENTATION_AND_LIMITS.md](V9_IMPLEMENTATION_AND_LIMITS.md).

## What v9 does **not** claim

- **SME credit-risk validation**: v9 validates payment *timing* and on-time behaviour on a public accounts-receivable sample (section 4). No licensed SME **default** dataset was available, so nothing here is a validated credit-risk model. Not production lending.
- **Usability testing with real users (T17)**: team states it has been carried out, but raw observations and summary are **not included in the ZIP**. No participant counts, completion rate or SUS scores can be verified until genuine records are attached (`reports/UAT_EVIDENCE_STATUS.md`). Browser E2E proves flows work, not that they are easy.
- **Real cloud deployment, penetration test, OIDC/MFA, real bank/e-invoice APIs**: not done. The smoke script (`scripts/deploy_smoke.py --base-url https://…`) is ready to run against a real deployment.
- Benchmarks are explicitly classified: some are SYNTHETIC/SIMULATED and others use public external data (see `reports/BENCHMARKS.md`). Do not describe the external-invoice backtest as an evaluation on real live SMEs or as proof of SME loan-default prediction.
- Local HTTPS checks do not equal a deployed-cloud security audit.
- **Self-assessment and known-risk list:** [`SECURITY_SELF_ASSESSMENT_2026.md`](SECURITY_SELF_ASSESSMENT_2026.md).
