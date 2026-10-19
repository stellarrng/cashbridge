# Back-office automation and provenance (local/cloud MVP)

The `automation` package has an opt-in SQLite queue and allowlisted worker (`scripts/automation_worker.py`). The code is a **local/cloud-capable framework**, not a deployed managed cloud service or continuous job scheduler. Run an always-on worker in a secured deployment to process jobs. No integration with real email, calendar, refund provider, payments, or accounting books is provided.

## Supported deterministic tasks

- `accounting_reconcile`: compare ledger and bank reference/amounts, highlight discrepancies.
- `audit_invoice`: highlight missing identifiers / potential duplicates; anomalies do not establish fraud.
- `provenance_review`: highlight recently edited numbers and machine-produced numbers (AI suggestion, ML prediction, deterministic calculation). Provenance is *supplied by the caller*: authenticate source adapters before treating those labels as verified.
- `support_triage`: route support ticket to support/security.
- `support_reply_draft`: create a controlled email reply *draft*, never send.
- `collections_draft`: draft an overdue invoice reminder, never send.
- `refund_review`: validate order-level refund amount and hold for human approval; never issue refund.
- `employee_task_plan`: validate proposed employee assignments; never send assignments.
- `schedule_reminder`: create an internal reminder job; no outbound alerts.
- `cash_alert`: check projected balances against minimum cash reserve.
- `executive_digest`: summarize allowlisted aggregate KPIs for a supervisor without private ticket details; external alert not sent.

## Audit highlights

The result `highlights` array includes `source`, `row`, `field`, `reason`, `severity`. `provenance_review` adds `origin`, `old_value`, `new_value`, `delta`, `method`, `actor_id`, `source_reference`, `status` and `color_hint`.

Suggested UI legend: **red** = discrepancy/duplicate requiring investigation; **blue** = changed manually; **purple** = AI/ML/calculated figure; **amber** = pending human review. Colors are cues, not verification. Always present original and modified numbers side by side. A model-generated value cannot overwrite the source ledger automatically.

Example API job payload (`POST /api/automation/jobs` with a configured bearer token):

```json
{"kind":"provenance_review","idempotency_key":"edited-figures-case-0001","payload":{"changes":[{"document_id":"INV-21","field":"amount","old_value":"1000.00","new_value":"1250.00","origin":"human_edit","actor_id":"accountant-7","source_reference":"invoice-21.pdf:page2"},{"document_id":"forecast-8","field":"cash_week_7","old_value":"8000.00","new_value":"7300.00","origin":"ml_prediction","method":"buyer-risk-v1","source_reference":"model-run-8"}]}}
```

A reviewer with the distinct `CASHBRIDGE_AUDIT_REVIEWER_TOKEN` can seal accounting/audit/provenance results using `POST /api/automation/audit/{job_id}/review` and retrieve evidence with `GET /api/automation/audit/{job_id}/evidence`. The **SHA-256 digest checks integrity, it is NOT encryption, an independently trusted timestamp or a digital signature**. Unreviewed content is not sealed. Secure storage, AES-GCM encryption at rest, identity checks, tenant isolation, and cryptographic signing require real infrastructure.

## Cloud security and scheduling limitations

Demo tokens are single shared secrets, not a tenant-specific user identity system. Do not expose these endpoints publicly or upload genuine financial/customer data until deploying real identity, tenant-scoped authorization, TLS, encrypted storage, monitored queues, migrations and backups. SQLite is intended for a single host demonstration; distributed cloud workers require an actual shared durable queue/DB and concurrency control. Setting a worker to run continuously does not create recurring tasks or outbound push notifications by itself.
