> **Historical document notice (updated 20 October 2026):** Statements below saying no real-user test describe the status *when this historical audit/research note was written*. The team now reports user testing has occurred, but the v9 ZIP does not contain de-identified session records or a UAT summary. See `reports/UAT_EVIDENCE_STATUS.md` and the current `docs/FINTECHATHON_2026_SCORECARD.md`; do not infer or invent results.

# Final audit and acceptance (v8, feature freeze)

**Freeze rule:** after v8 no new modules or agents. This round only checked five areas a judge could challenge,
fixed what was actually wrong, and re-ran every acceptance check. Every number below was produced by a command
in this repository; nothing was estimated. Data is SYNTHETIC and the lender is MOCK.

## Result

| Check | Command | Result |
|---|---|---|
| Full regression (unit, API, adversarial, oracle, failure, browser) | `make test-report` | **1380 passed, 0 failed, exit 0** (7 min) — `reports/full_pytest.txt` |
| Real-browser journeys (Chromium) | `make e2e` | **9 passed** — `reports/e2e/*.png` |
| All benchmarks and reports regenerated | `make evidence` + `--with-deploy` | **10/10 steps pass** — `reports/BENCHMARKS.md` |
| Production mode over HTTPS, restart, log scan | `make deploy-check` | **27/27** — `reports/deploy_verification.md` |
| Clean checkout, fresh install, full suite | see §7 | exit 0 |

## 1. Financial accuracy audit — Task Completion

**How:** `tests/test_financial_accuracy.py` (726 test cases). Each formula is re-computed by an *independent oracle*
written from the textbook definition in exact rational arithmetic (`fractions.Fraction`) with its own half-up
rounding; it shares no code with the engines. The demo figures are also checked against hand calculations.

| Formula | Convention | Checked by |
|---|---|---|
| Annualised cost | total cost / net funds × 365 / days; simple, Actual/365, no compounding | hand values (17.12%, 18.24%, 37.24%) + 300 random term sets |
| Early-payment discount | d/(1−d) × 365/(net − discount days) | oracle |
| Simple interest, fees | principal × rate × days/365, half-up to the cent | oracle, exact half-cent boundary, the 2.675 float trap |
| FX | amount × VND per unit / 26,000, half-up; JPY/VND have 0 minor digits | 200 random amounts in 4 currencies |
| 13-week forecast | closing = opening + inflows − outflows, exact; shortfall = −closing in first negative week | 5 what-if combinations |
| Shortfall drivers | add up to the shortfall to the cent | same |
| Receivable split | final = on-time + late; final = raw + FX effect + tariff effect | every invoice |
| CCC | DIO + DSO − DPO from ledger averages, 0.1-day rounding | oracle |
| CVaR95 | mean of the worst ⌈5% × n⌉ shortfalls; never below VaR95 | n = 1 … 1001 incl. ties |
| Wilson interval, Brier score | standard definitions; baseline Brier recomputed from raw history | published values |
| Green loan instalment | standard annuity; 0% handled | 4 rate/tenor pairs |
| Capital plan gap | deployable = cash − reserve; gap = max(0, spend − deployable) | worked example |

**Found and fixed:** the planner (`agents/intelligence_core.py`) rounded quotes with Python `round()` on floats
(banker's rounding plus binary error), so it could quote a cent differently from the funding engine for the same
option (e.g. a USD 1.825 fee → 1.82 instead of 1.83). It now uses Decimal half-up like the engine; 200 random
cross-checks confirm planner and engine agree to the cent.

**Documented, not changed:** the factoring cost is quoted for drawdown today (interest to the due date) while
the coverage chart shows the funds arriving in the first shortfall week. The quoted cost is therefore an upper
bound; this is now stated in the coverage assumptions.

## 2. Model fairness and explainability — Security & Compliance

**How:** `eval/model_fairness.py` → `reports/model_card.md`; `tests/test_model_audit.py`.

- The model scores **companies' payment timing** (buyers), not people and not the SME's creditworthiness; no
  personal or protected attributes are used (test-enforced). Credit decisions stay with a named lender reviewer.
- Walk-forward calibration (167 predictions): predicted vs observed on-time rate inside the 95% interval in
  **8 of 8 groups** (market, invoice size, payment terms). Brier 0.0906 vs 0.1481 without buyer identity.
- **Disclosed confound:** each market has exactly one buyer in the data, so a country effect cannot be
  separated from that buyer's own record; removing identity breaks calibration for JP (−35 pp).
- **Every score is explainable:** `explain()` returns intercept + per-feature contributions that add up to the
  log-odds exactly; the lender sees it in the case view (`buyer_risk_explanation`).
- **Out-of-domain inputs are flagged** (terms or invoice size outside the training range); new buyers get the
  portfolio average and are marked `has_history: false`, not penalised.
- **Green finance:** even with 100% of evidence provided, the status stays `NEEDS_HUMAN_REVIEW`, evidence is
  `provided_unverified`, and `green_taxonomy_verified`, `impact_is_verified`, `bank_credit_approved`,
  `green_certified` are always false; a test scans outputs and EN/VI/ZH copy for eligibility or certification claims.

## 3. Data privacy lifecycle — Security & Compliance

**How:** `core/privacy_lifecycle.py`, `scripts/privacy_tool.py`, `tests/test_privacy_lifecycle.py`.

| Lifecycle step | Status |
|---|---|
| Consent | The Director's OTP release is the consent to share one exact pack (bound by hash) with one lender |
| **Withdrawal (fixed)** | New: Director can withdraw before the lender decides (`POST /api/withdraw_release`). The lender immediately loses the inbox item, case, PDF, messages and evidence requests (404), gets an in-app notice to delete copies, and the withdrawal is in the audit chain. Refused after a lender decision |
| Minimisation | Lender sees only released packs; audit log stores SHA-256 of payloads, never the payloads |
| Access / portability (fixed) | `privacy_tool.py export --tenant …` writes everything held for an organisation as JSON |
| Retention and deletion (fixed) | `privacy_tool.py purge`: notifications deleted and support/refund job payloads redacted (hash kept) after 90 days; audit archives capped. Audit log, case records and sealed accounting evidence are kept (record-keeping duties; confirm periods with counsel) |
| **Shared static credential (fixed)** | `CASHBRIDGE_BANK_REVIEW_TOKEN` is refused in production at runtime and production refuses to start if it is set |

## 4. Failure and edge-case testing — Task + Security

**How:** `tests/test_failure_modes.py` (17), plus the earlier adversarial (35), data-gate (21) and queue fault (11) suites.

| Injected failure | Before | After |
|---|---|---|
| Lender API times out during release | HTTP 500, no message | Clear `lender_unavailable`; nothing submitted or registered; audit entry; retry with the next code succeeds |
| PDF compilation fails after the lender accepted | HTTP 500 although the pack **was** submitted | Reported as submitted; PDF rebuilt on first download (byte-identical); audit entry |
| PDF deleted on disk | 404 for the lender | Rebuilt from the locked record, same bytes |
| `NaN` / `Infinity` / `1e400` in JSON | HTTP 500 on two endpoints | 422 everywhere (Python accepts NaN in JSON by default; now refused before parsing) |
| Missing or corrupt input file | HTTP 500 | 503 "nothing was changed" |
| Any unexpected bug | Starlette's plain 500 | JSON 500 with an incident id, no internals, incident in the audit chain |
| Lender "accepts" a document without seeing it | Possible (only a hash was exchanged) | Accepting now requires the SHA-256 of the file the lender holds to match the submitted one (checked in the lender's browser); a different file is refused. Browser-tested |
| Tampered audit log | Detected | Still detected by the lender's verification |

## 5. Independent user acceptance — Innovation & Interaction

**Not done with real users** (no participants were available to us). Prepared instead:

- `docs/UAT_PROTOCOL.md`: participants per role, guidance-free rules, 8 task cards with success criteria and
  critical errors, metrics (unaided completion, time, errors, SEQ, SUS) and acceptance thresholds.
- `eval/uat_summary.py` + `reports/uat_results_TEMPLATE.csv`: refuses to summarise an empty file, so no
  invented results can reach a report.
- Automated pre-condition (`test_each_roles_next_action_is_on_the_first_screen`): on sign-in, each role's
  next action is visible without scrolling on a laptop and a 375 px phone. **Found and fixed:** on phones the
  demo persona switcher pushed the accountant's main task below the fold; it is now hidden on narrow screens
  (Switch account stays in the menu) and the "prepare funding" tile comes first.

## 6. What is still not proven

External SME data validation (T12), forecast back-testing on real cash (T13), field-level provenance (T14),
real-user UAT, a cloud deployment run, Docker image build/scan, penetration test, OIDC/MFA, shared session
revocation across processes, and real bank / e-invoice integrations. These are listed so no claim exceeds the evidence.

## 7. Reproduce from a clean machine

```bash
git clone <repo> && cd cashbridge
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt -r requirements-e2e.txt
make test-report && make evidence && make deploy-check
```
