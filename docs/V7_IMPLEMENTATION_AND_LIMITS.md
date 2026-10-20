# CashBridge v7 — verified additions, usage and limits

This release extends the **synthetic SME financing prototype**; it is not connected to real payment, bank, credit-bureau or lending APIs. The natural-language LLM remains presentation-only. No agent is authorized to approve a loan, post a ledger entry, send external correspondence or execute a refund.

## Scope by FinTechathon category

| Category | Implemented in v7 | Verification/limits |
|---|---|---|
| **Task Completion (40%)** | Bounded data-quality/reconciliation check; versioned budget-change and scenario assumptions; evidence appeals; shared pack correspondence; offline model-validation CLI | Data gate must be configured against *server-held* quality evidence before financial actions; external dataset for SME underwriting **not included**; previously existing financing workflow remains the main demo |
| **Security & Compliance (30%)** | Server-enforced permissions, separate proposer/reviewer, stale-version rejection, released-pack check before cross-party messages; bounded SQLite queue retries, dead-letter inspection and operator-only redrive | Offline queue is safe only because all handlers are deterministic and side-effect-free. Real providers need transactional outbox, per-tenant worker identity, hardened secrets, shared storage, MFA/OIDC, security review and deployment tests |
| **Innovation & Interaction (30%)** | New role-dependent Evidence & Collaboration workspace, versioned history, explainable quality flags, approved-scenario recalculation, restricted bank messaging, direct chart-label bounds and defensive empty-state render | Messages are local sandbox records, **not emails**; changes affect scenario-only planning assumptions, never accounting books; appeals are review requests, not automatic model corrections |

## Role workflow

1. **Accountant** opens **Evidence & Collaboration** and checks the synthetic quality example, proposes a marketing/working-capital/green-investment planning assumption and gives a reason. The source data itself does not change.
2. **Director** signs in separately, reviews the request history, enters an explicit review reason and approves or rejects. A stale proposal cannot overwrite a newer approved value. Director can also appeal a finding.
3. Approved assumptions are used by **Calculate** for the *separate synthetic capital-allocation scenario only*. CashBridge labels the result accordingly. The main 13-week forecast is unchanged.
4. Once the existing OTP-protected funding flow has released a pack, Accountant and **Bank Reviewer** can exchange case-level questions or evidence requests in the workspace. Before release, both `GET` and `POST` reject it. Conversations cannot be sent externally.
5. **Appeals** have evidence references, review status, actor and append-only action history. They require a different approver. Rejected/approved decisions are not erasable through the UI.

## REST endpoints

All `/api/workspace/*` endpoints require an existing signed CashBridge session. Requests/appeals use `sme:prepare` (Director may also submit appeals) and review requires `sme:approve`; released-case messages require SME preparer or Bank reviewer privileges. Bank cannot access SME planning requests.

- `POST /api/workspace/quality` — bounded manifest and ledger/bank data check, 3 gate states: `BLOCKED_FOR_FINANCING`, `REVIEW_REQUIRED`, `READY_FOR_DRAFT`. Self-declared `verified_by` metadata **does not establish authenticity**.
- `GET /api/workspace/requests` — SME-only versioned request and approval history.
- `POST /api/workspace/requests` — change request, e.g. `{"field":"marketing_usd","proposed_value":"25000","reason":"Quarterly campaign budget"}`.
- `POST /api/workspace/appeals` — second-look request with evidence reference.
- `POST /api/workspace/requests/{id}/review` — Director-only approval/rejection, with note.
- `POST /api/workspace/scenario` — synthetic capital allocation using *approved* values.
- `GET/POST /api/workspace/cases/{pack_id}/messages` — authenticated release-gated case correspondence.

### Fail-closed data gate for financial actions

By default this extra gate is **off** so the provided synthetic demo still runs. To enforce it on `autopilot execute`, `prepare_pack` and `approve`, set:

```bash
export CASHBRIDGE_REQUIRE_DATA_GATE=1
export CASHBRIDGE_QUALITY_MANIFEST_PATH=/secure/config/quality_manifest.json
export CASHBRIDGE_VERIFIED_SOURCE_IDS=bank-2026Q3,ledger-2026Q3,aging-2026Q3
```

The manifest contains `sources` with `source_id`, `type`, `as_of`, `ledger_entries`, `bank_entries` in the same form as `/api/workspace/quality`. The environment IDs are provided by the trusted **server-side verification process**, *not* from uploaded documents or the browser. There is **no integrated identity/certificate verification service yet**; operators must ensure these IDs genuinely correspond to reviewed and controlled sources. Missing/stale/mismatched/unverified manifest fails closed. Quality `quality_index` is a triage index, **never** a calibrated probability.

### Automation queue

```bash
python -m scripts.automation_worker --once
```

Jobs are claimed under an SQLite write transaction, with `attempts`, `claimed_at`, due-time retry, backoff (2, 4 seconds then quarantine) and stale-claim recovery. Invalid inputs fail without retry; exhausted transient failures enter `dead_letter`. Reviewer-credential-only administrative routes:

```
GET  /api/automation/dead-letters
POST /api/automation/dead-letters/{job_id}/redrive
```

Both require `CASHBRIDGE_AUDIT_REVIEWER_TOKEN`. Enqueue idempotency fingerprints are unchanged. **For real-world financial actions, a crash after contacting a provider but before recording success still needs provider-side idempotency and reconciliation; these queue semantics alone are not sufficient.**

## Offline validation package: no real dataset bundled

Run with a **licensed and consented dataset you provide**. Columns must be strictly pre-decision numeric features, binary label and ISO date:

```bash
python -m eval.external_validation --csv /path/to/licensed_data.csv \
  --label defaulted --date observation_date \
  --features leverage,payment_delay_days,annual_revenue \
  --output /tmp/cashbridge_validation.json
```

The script chronologically splits train/test (70/30 without sharing an observation date across the boundary), fits a train-only standardised regularized logistic model and reports Brier, ROC-AUC and prevalence baseline. It never emits row-level predictions. Rejects short datasets, missing columns, invalid values, and obvious label leakage names. **No external data have been validated as part of this release**; one-off metrics do not justify production lending decisions.

## Tests and remaining work

- Targeted regression: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_v7_workflows.py tests/test_role_navigation_v5.py tests/test_copy_quality.py tests/test_ui_bundle.py tests/test_automation_all_kinds.py tests/test_automation_evidence.py tests/test_auth_rbac.py`.
- JS syntax: `node --check` the four edited scripts (`app.js`, `charts.js`, `i18n.js`, `api.js`).
- The complete legacy test suite and production-browser E2E were **not fully verified** during assembly; rerun before submission.
- Not delivered: live SME-lending model trained on geography-appropriate external data; production-ready cloud reliability; native Bank API; app-store-grade UX accessibility/usability evaluation; penetration test; genuine digitally signed source verification.
