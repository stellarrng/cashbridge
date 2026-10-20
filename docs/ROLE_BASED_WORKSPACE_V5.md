# CashBridge v5: least-privilege role workspaces

The web UI is a **React + TypeScript** app (`frontend/`, built into `frontend/dist`). It uses the session's **server-issued permissions** to select task-centric navigation and the default landing page. The frontend does **not** grant authorization: every API request remains subject to backend authentication, role and tenant checks.

| Persona | Default | Navigation | Intended workflow |
|---|---|---|---|
| SME accountant (prepare) | Overview | Overview, Autopilot, Evidence, Cash, Funding, Analytics, Projects, Contracts, Green, Trust | Reconcile, assess, prepare; cannot approve own funding pack |
| SME director (approve) | Intelligence Core | Intelligence Core, Funding, Cash, Analytics, Projects, Green, Trust | Focus on exceptions, financing decisions and approvals rather than raw evidence operations |
| Bank reviewer | Bank inbox | Bank inbox, Trust (case details in inbox) | Review cases disclosed to the bank, not arbitrary SME operational data |

**Existing features preserved:** Intelligence Core already includes Director Inbox, `Decision / Analysis / Evidence` views and simulation event controls; `#cash` already has What-if scenario sliders; `#trust` includes security and test evidence. The changes intentionally do not duplicate those features.

**Security:** Hiding a menu does not secure an API. Check session authorization for every endpoint, tenant-scoped document grants, separation of duties, and cross-tenant access in automated tests. Demo persona switching uses `demo-login` and is for explicitly configured demo accounts only. Do not configure demo accounts in production.

**Not claimed:** Full production workflows for separate Auditor, Employee or Support identities, external email sending, refund execution, calendar integrations, or a live cloud 24/7 scheduler. These require corresponding server permissions and integration tests before their UI should be enabled.

**Recommended demo:** Accountant logs in, prepares and examines exceptions; Director logs in to review `#core/decide` and approves where policy permits; Bank reviewer logs in to review the shared case. Show the forbidden action test for each role.
