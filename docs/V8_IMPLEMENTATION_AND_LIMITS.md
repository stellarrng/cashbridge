# CashBridge v8: what changed against the "To 100" action plan, and how it was verified

Status per task of `CashBridge_v7_To_100_Action_Plan.md`. "Done" means the Definition of Done was met with a
test or report that fails if the claim stops being true. Numbers are from the run recorded in `reports/`.

| ID | Task | Status | What was done | Proof |
|---|---|---|---|---|
| T01 | Full regression | **Done** | Suite runs to completion: **1380 passed, exit 0** after the final audit (617 at v8 first pass) (518 in v7; the v7 "41% then timeout" was the reviewer's time limit, not a hang). `faulthandler_timeout=300` dumps stacks if a test ever hangs. `make test-report`. | `reports/full_pytest.txt` |
| T02 | Browser E2E | **Done** | Playwright + Chromium against a live server: 3-role journey, refresh, wrong-role route (UI + API 403), sign-out, wrong then right OTP, Escape, reject/rework, evidence loop with in-browser file hashing, EN/VI/ZH without raw keys, 375 px phone. Found and fixed 2 UI bugs (Trust page overflow on phones; sidebar card covering "Sign out"). | `tests/e2e/`, `reports/e2e/*.png` |
| T03 | Deterministic demo | **Done** | Two fresh servers → identical pack id, metrics, bundle hash, letter, PDF bytes, lender checks; every letter figure is a locked metric. Demo script rewritten for the current RBAC flow. | `tests/test_demo_reproducible.py`, `docs/FINTECHATHON_DEMO_STORY.md` |
| T04 | Data gate fail-closed | **Done** | One gate (`core/financing_gate.py`) on all six financing routes; v7 missed `/packs`, `/packs/{id}/approve` and lender APPROVE_FUNDING. Always on in production. Verification only via HMAC-signed attestations bound to id/type/date/hash (`scripts/attest_source.py`). Refusals audited. | `tests/test_financing_gate.py` (21) |
| T05 | Threat tests | **Done** | 35 adversarial tests. Fixes: OTP brute-force cap (challenge voided after 5 wrong codes), sign-in throttle no longer bypassable via `X-Forwarded-For`, per-account throttle, message kinds bound to role, 6 MB body limit, HSTS, API docs hidden in production. | `tests/test_adversarial.py` |
| T06 | Queue faults | **Done** | Lease token (zombie worker cannot overwrite), `dead_at` on recovered DLQ jobs, decision whitelist for audit review, reviewer token must differ from operator token, transactional outbox + provider idempotency key, non-mock providers refused. 11 fault scenarios, each mutation-checked. | `reports/queue_faults.md`, `tests/test_queue_faults.py` |
| T07 | Deployment | **Done locally / pending cloud** | PRODUCTION mode over real HTTPS (throw-away CA), restart, session + workspace survive, audit evidence archived with intact chain (no longer deleted on restart), logs scanned: 27/27. Automation/workspace DBs moved into the writable runtime dir (the Docker user could not write the old path). Reusable `scripts/deploy_smoke.py` for the real host. Docker image not built here: the sandbox could not pull the base image. | `reports/deploy_verification.md`, `tests/test_deploy_checks.py` |
| T08 | Reproducible benchmarks | **Done** | `make evidence` runs 9 generators with fixed seeds, records n, seeds, time, commit, and fails on any error. | `reports/BENCHMARKS.md`, `reports/EVIDENCE_INDEX.json` |
| T09 | UX/copy | **Partly** | Fixed: phone overflow, sidebar overlap, mid-word breaks in check details, `window.prompt` reject replaced by a translated dialog, "lower is better" on cost and tail-risk charts, role-correct message types. Not done: a full copy review of every screen. | E2E screenshots |
| T10 | Submission evidence | **Done** | Claim → source → test → evidence → limitation map. | `docs/RUBRIC_EVIDENCE.md` |
| T11 | Risk-aware planner | **Done** | Objective `cost + 0.02 × CVaR95` (fixed policy weight) is now the default after an out-of-sample benchmark: CVaR95 −1,571 USD (95% CI −2,491 to −702), cost +0, P(goal) +0.8 pp; same policy limits; API `objective` parameter; CVaR column in the Decision center. | `reports/risk_planner.md`, `tests/test_risk_planner.py` |
| T12 | External SME validation | **Not done** | No licensed SME default dataset available in this environment. Harness unchanged and ready. | — |
| T13 | Forecast accuracy | **Not done** | Needs an independent time series of actual cash. | — |
| T14 | Field-level provenance | **Not done** | Document hashes per pack exist (v7); click-through to source field and controlled correction not built. | — |
| T15 | Appeal / case collaboration | **Done** | Lender evidence requests: open → SHA-256-bound submission → accept/reject with reason → resubmit (max 5) → revoke / expiry; stale-review protection; per-role in-app notifications; every transition in the audit chain; APPROVE_FUNDING blocked while unresolved. | `tests/test_evidence_loop.py`, E2E `test_lender_evidence_loop_in_the_browser` |
| T16 | Executive Inbox robustness | **Done** | 30 seeds × 100 events: 0/145 missed (Wilson upper 2.6%) vs 35/145 for the USD 10k rule; burst, small-but-critical and harmless-flood stress cases hold. | `reports/ops_robustness.md` |
| T17 | User testing | **Not done** | Needs participants. | — |
| T18 | Green finance | **Done (scope)** | Green investment against the 13-week buffer: cash vs green loan, extra funding needed, using the case's loan quote; labelled estimate, `green_certified: false`. | `tests/test_green_cash_impact.py` |

## Still open before claiming production readiness

Real cloud deployment run of `deploy_smoke.py`, Docker image build + scan, OIDC/MFA, external penetration test,
real bank / e-invoice / payment adapters with contract tests, a licensed SME dataset (T12), forecast back-testing (T13),
user testing (T17), and a shared (multi-process) store for sign-out revocation and login throttling.

## Final audit round (feature freeze)

Five verification checks were run after v8 with no new modules; see [FINAL_AUDIT_AND_ACCEPTANCE.md](FINAL_AUDIT_AND_ACCEPTANCE.md).
Defects found and fixed: planner cent rounding, lender-timeout 500, PDF-after-submission misreport, NaN/Infinity 500s,
missing-data 500, lender accepting evidence without checking the file, no consent withdrawal, no export/retention tooling,
static bank token usable in production, phone home screen hiding the accountant's next action.
