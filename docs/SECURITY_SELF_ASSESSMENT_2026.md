# CashBridge v9 | Security Self-Assessment
## 2026 Shenzhen FinTechathon International Track, Topic E

**Assessment scope:** CashBridge v9 sandbox prototype, generated demonstrations and repository evidence reviewed 20 October 2026. This is a **self-assessment**, not an independent penetration test, legal compliance opinion or production readiness certificate.

## 1. System trust model

- **Actors:** SME chief accountant (preparer), SME director (approver/consent owner), lender reviewer (independent reviewer in a mocked lender environment), automated agent processes.
- **High-impact boundary:** The agent may analyse data, draft a financing plan/pack, route review items and report outcomes. It cannot silently bypass financing eligibility, obtain the Director's approval on their behalf, make a lender credit decision or execute real money movement.
- **Data:** Synthetic accounts, invoices, cash-flow forecasts and documents; evidence content is accessible only after appropriate release. Mock providers and test data are labelled as such.
- **Trust assumptions:** Host and configured secrets are trusted for the local demo. Server-side auth and data gates enforce permissions; browser display alone does not. Production mode requires separate configured secrets/users and disables demo shortcuts.

## 2. Permission tiers (server-enforced controls)

| Capability | Accountant | Director | Mock lender reviewer | Agent | Main enforcement/evidence |
|---|---|---|---|---|---|
| See organisation's permitted SME data | Yes, own tenant | Yes, own tenant | No, except specific released case | Only through allowed tools | `security/auth.py`; tenant and portal checks; adversarial tests |
| Detect cash gaps and analyse funding | Yes | Yes | Within released case, limited | Yes (read/analysis) | Role-aware API, financing/planner modules |
| Prepare a financing application and supply evidence | Yes, subject to validation | Review/return as allowed | Request clarification; review received evidence | Draft/route, not approve | `agents/coordinator.py`, evidence workflow tests |
| Approve and release financing pack | **No** | **Yes, action-bound OTP** | No | **No** | `security/otp_verifier.py`, `tests/test_adversarial.py` |
| Read unreleased SME material | Own tenant only | Own tenant only | **No** | Policy-scoped only | Tenant isolation and Director release controls |
| Verify lender evidence and record mock credit decision | No | No | **Yes**, within their role and case | **No** | `api/main.py`, `tests/test_evidence_loop.py` |
| Initiate real funds movement | **No** | **No** via this prototype | **No** | **No** | Non-mock provider and unsafe action guards |
| Withdraw consent before lender decision | As permitted by role/workflow | **Yes** | No | No unilateral withdrawal | `tests/test_privacy_lifecycle.py` |

*Table describes intended and tested access flows; fine-grained endpoint permissions are defined in the code, not by this document.*

## 3. Verified controls / self-assessment checks

| Area | Implemented evidence | Archived outcome | Remaining boundary |
|---|---|---|---|
| Signed sessions, tenant separation, role-bound messages | `security/auth.py`, `tests/test_adversarial.py` | 25/25 adversarial trust scorecard cases pass (broader suite) | Demo tenant set; production IAM not independently audited |
| Director approval + separation of duties | `security/otp_verifier.py`, `agents/coordinator.py` | Wrong/reused/action-mismatched approval denied | Demo OTP path is intentionally documented; use production configuration for a real deployment |
| Financial data reliability gate | `core/financing_gate.py`, `core/source_attestation.py`, `tests/test_financing_gate.py` | Missing, edited, stale, forged, or unverifiable data blocked | HMAC attestation proves key-holder action, not real document origin or legal validity |
| Evidence vault / privacy | `workspace/evidence_vault.py`, `tests/test_evidence_vault.py`, `tests/test_privacy_lifecycle.py` | MIME checked by bytes, server SHA-256, AES-256-GCM, integrity check on read; audited viewing and withdrawal | Key held in environment, not cloud KMS/HSM; malware scan not implemented |
| Auditability | `security/audit_log.py`, `data/execution_evidence/ANCHORS.md` | Tampering of logged event detected in tests; seeded chain anchor retained | Hash chaining alone is not external non-repudiation; secure external anchoring not claimed |
| Provider and queue robustness | `automation/outbox.py`, `automation/engine.py` | `reports/queue_faults.md`: 11/11 invariant checks | SQLite single-host assumptions; mock provider only |
| Deployment-mode hardening | `config/runtime_mode.py`, `scripts/verify_deployment_local.py` | `reports/deploy_verification.md`: 30/30 checks over local TLS, restart and 3 workers | Real host/cloud/WAF, container build, pentest and OIDC/MFA not verified |
| AI action boundary | `agents/autopilot.py`, `config/tool_allowlist.py`, `data/execution_evidence/trust_scorecard.md` | 5/5 agent outcomes; blocked attempts logged | Team-selected scenarios; not a guarantee against all attacks |

## 4. Known-risk register (do not hide these)

| ID | Residual risk | Severity for prototype | Current mitigation | Production-oriented next step (not a contest prerequisite) |
|---|---|---|---|---|
| R1 | Demo sign-in and public example OTP are designed for convenient judging | Medium if a demo URL is publicly reachable; low in isolated sandbox | DEMO/PRODUCTION split; production refuses demo shortcuts | Use configured accounts/MFA; publish demo as synthetic only |
| R2 | No independently run pentest or threat model review | Medium | Adversarial cases, strict RBAC, fault injection | Independent app assessment before real use |
| R3 | Stored encryption key is provided by environment variable, not KMS/HSM | Medium | AES-256-GCM with context binding, explicit production secret requirement | Use KMS/HSM and rotation |
| R4 | Evidence upload has no malware scanning | Medium | Content and size checks, audited viewer, hash verification | File scanning/isolation and content sanitisation |
| R5 | Simulated lender and payment rails do not prove external integration security | Low in prototype, high for real funds | Provider mock labels, non-mock provider refused | Contracted real provider integration plus idempotency reconciliation |
| R6 | Synthetic financial/behavioural data may not generalise to real SMEs | Medium for financial recommendation usefulness | Policy disclosure, public-data timing backtest, show uncertainty, human sign-off | Privacy-approved representative SME pilots and recalibration |
| R7 | SQLite-backed shared state across worker processes depends on a single host | Medium | Multi-worker restart tests | Shared managed DB, distributed worker stores |
| R8 | Retention periods and third-party copied evidence require legal/process controls | Medium | Withdrawal, audit, export/purge tools; notice to lender | Review jurisdictional requirements and contractual deletion obligations |
| R9 | Vulnerabilities in third-party dependencies or hosted environment not independently evaluated | Medium | Dependency lists, local production checks | SBOM/dependency scan, hosting threat review and monitoring |

## 5. Demonstrable refusal scenarios (high-value for judges)

1. Accountant attempts Director approval: **denied**, role and audit trail demonstrate separation of duties.
2. A wrong or reused OTP is provided: **denied**, with no release or double financing.
3. Source attestation is missing or document altered: financing prepare/approve routes **fail closed**.
4. Lender tries to access an unreleased tenant's material: **denied**.
5. Lender tries to accept additional evidence without opening current stored file: **denied**.
6. Planner attempts to send money or skip verification: policy blocks side effect and logs the refusal.

## 6. Judge-facing compliance statement

> CashBridge uses role separation, action-bound human approval, source verification, encryption, consent controls and auditable refusal paths to reduce risk in a sandbox financing workflow. All payments and lender decisions in the demo are MOCK, all SME inputs are SYNTHETIC. The system has not undergone independent penetration testing, regulatory certification, real lender onboarding or production credit-model validation. A human Director authorises each release, and the mocked lender's reviewer records the decision. Neither the AI agent nor the CashBridge demonstration disburses real funds.

## 7. How to inspect and re-run

```bash
make test-report        # archived result: reports/full_pytest.txt -> 1609 passed
make e2e                # browser role/permission journeys and screenshot proof
make trust              # 25 adversarial cases, 5 agent outcomes, model metric
make faults             # 11 queue/outbox fault scenarios
make deploy-check       # local production-mode HTTPS checks
# On an actual hosted deployment, only when available:
python scripts/deploy_smoke.py --base-url https://YOUR-HOST --expect production
```

**Related:** `docs/FINTECHATHON_2026_SCORECARD.md`, `docs/RUBRIC_EVIDENCE.md`, `reports/BENCHMARKS.md`.
