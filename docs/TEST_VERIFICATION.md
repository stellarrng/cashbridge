> Historical note (v1). Since v5 the React/Vite prototype is removed; the only web app is the no-build `ui/web/dist`. Current test count: run `make test`.

# Verification — Privacy-first CashBridge demo

**Date:** 2026-10-19 (synthetic project dataset).

## Results actually checked in packaging runtime

- `python -m pytest -ra --disable-warnings` → **415 passed**.
- `node --check ui/web/dist/assets/demo.js` → passed JavaScript syntax check.
- In-memory Chromium + FastAPI TestClient UI harness → passed: SME policy workflow, deterministic multi-tool trace and review status, public-concept local fallback, token-gated bank reviewer, explicit lock action; **zero browser JS errors**. See `docs/screenshots/10-policy-multi-agent.png` and `11-bank-token-gated.png`.
- `tests/test_contract_word_export.py` → unsigned DOCX export parsed successfully with python-docx; invalid 99% payment milestone rejected.
- `tests/test_contract_drafting.py` (v9) → Vietnamese and English amounts in words, every type × language has 21 articles and 3 schedules, instalments add up to the price to the cent, the analyzer raises no flag on our own drafts and finds a 100% schedule, financing and call-back clauses always present, missing data becomes open items, bad input refused, Word file is A4 / Times New Roman / watermarked / paginated / NOT SIGNED in every language. Rendered through LibreOffice and inspected page by page.
- Parametrized safety checks in `tests/test_policy_security.py` and `tests/test_concept_boundary.py` → pass, including prompt injections unable to change tool plans, secrets never sent to LLM provider spies, conflicting contract/scenario totals refused, bank Bearer auth required, audit entries containing input hashes rather than raw documents.

## Not independently verified / limitations

- **React/Vite bundle:** npm dependencies absent in the offline environment; React sources were edited but **not compiled**. The included `ui/web/dist` is the separately working zero-build browser dashboard. `npm ci && npm run build` should be run only if you intend to replace the fallback distribution.
- Browser harness uses Playwright's `set_content` with FastAPI TestClient-backed fetch responses. External network navigation was blocked in this environment. This does **not** validate HTTPS deployment, infrastructure, external APIs or all browsers.
- ML buyer-risk coefficients are trained on **synthetic** local transaction history, not validated as a real-world credit model. No trained fraud model or externally verified bank risk scores are claimed.
- Bank token is a **synthetic single-case read-only demo gate**. Not production RBAC, OIDC, MFA, tenant isolation or KYC/AML compliance.
- Fraud rules produce **review signals**, not determinations of fraud. Contract drafting creates **unsigned drafts for counsel** only (complete clause library, but not legal advice).
- Financing catalog is derived from an **existing separate demo invoice**, and cannot be treated as validated offers for the new project. The agent explicitly marks new-project matching / eligibility **NOT ASSESSED**.
- Contract-to-funding outputs are not credit decisions, and cannot submit or transfer money. The existing separate OTP flow targets only a MOCK lender.
