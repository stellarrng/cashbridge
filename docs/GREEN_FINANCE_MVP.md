# Green Finance Readiness — experimental extension

This MVP adds a **synthetic, human-review-only** green project pre-screening to CashBridge.
It is not a green taxonomy certification, a lending recommendation or a bank approval.

## New components
- `core/green_finance.py`: deterministic input validation, evidence completeness, transparent indicative annual tCO2e calculation. The emissions factor is an explicit **illustrative assumption**, not a verified local grid factor.
- `data/sandbox_inputs/green_projects.json`: two invented example projects.
- `GET /api/green-finance`: read-only project assessments.
- `POST /api/green-finance/request-review`: `{ "project_id": "GREEN-SOLAR-001" }` marks the case `PENDING_HUMAN_REVIEW` in **this demo process only**. It does not transmit a financing application or contact a bank.
- UI navigation: `Green Finance`, with SME and Bank reviewer perspectives. Views are illustrative and do not implement bank user authentication.

## Important controls still required for deployment
1. Authenticated borrower and reviewer accounts, segregation of duties, persistent review queue and audit logs.
2. Jurisdiction- and lender-specific taxonomy rules versioned with source references and formal signoff.
3. Metered/baseline energy evidence, validated emission factors and documented uncertainty.
4. Consent, secure connectors and authorization for banking/ERP/energy data access.
5. Green loan monitoring (use of proceeds, allocation, impact and post-disbursement reporting).
6. Credit evaluation, bank product eligibility and lender-sandbox integration under agreements.

## How to test
`python -m pytest tests/test_green_finance.py -q`
Full application tests need all packages in `requirements.txt` (including `pyotp`).
The web app is the React project in `frontend/` (built into `frontend/dist`).
