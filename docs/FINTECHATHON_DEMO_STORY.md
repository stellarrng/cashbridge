> **Current architecture:** Demonstrate deterministic contract-to-financing agent orchestration, no LLM tool selection, and server token-gated bank review. See [privacy-first design](PRIVACY_FIRST_AGENT_ARCHITECTURE.md). If the original script below suggests live LLM execution, that part is obsolete.

# Three-minute demo scenario — no real loan or real client data

1. **SME liquidity pressure (30 s).** Open `/` → **Overview**. Explain original 13-week forecast, due invoices, shortfall and blocked business-email-compromise attempt. Click **Financing** and compare actual cost/APR from the existing engine; do not approve yet.
2. **Financial EDA + marketing decision (35 s).** Open **Finance EDA**, show liquidity, DSCR proxy, EBITDA margin and the 12-month expense table. Change marketing by 25% and receipts delayed by 10%, run scenario and show projected cash, minimum reserve and assumptions.
3. **Bid viability (25 s).** Open **Bid simulator**. Set contract $200,000, upfront cost $110,000, available cash $60,000, reserve $15,000, advance 20%, overrun 15%. Click assess; explain initial funding gap and stressed gap. Optionally adjust workforce hours, which affects cost but **never** grades individuals.
4. **OCR → contract fraud signals (35 s).** Open **Contracts + OCR**. Paste example contract or upload a text PDF / clear scan. Click **Review contract** to find milestones. Click **Compare invoice** on the intentionally inconsistent $260,000 invoice; show the mismatch as a flag, not fraud proof. Draft a supply agreement and show `UNSIGNED / LEGAL REVIEW REQUIRED`, then save TXT.
5. **Bank reviewer (25 s).** Select **Bank reviewer preview**. Show finance ratios, source-labelled evidence, audit chain, current contract flags and independent reviewer checklist. State clearly that the role toggle is only a presentation control, not authenticated RBAC or credit approval.
6. **Human-in-the-loop (25 s).** Return to SME, choose an eligible financing option, prepare a pack, request action-bound OTP, and demo a refusal for invalid OTP. Optionally enter the real demo authenticator code for the **MOCK** lender; never imply funds moved.
7. **Green opportunity (15 s).** Show Green evidence completeness + estimated simple payback at a **hypothetical** electricity tariff. No official taxonomy certification.

## Example chat utterances

- `Why is cash short in week 7?`
- `What happens if we increase our marketing budget?` (offline shortcut illustrates +25%; edit full scenario form for other inputs)
- `What is our DSCR?`
- `Explain contract risk` (after analyzing a contract)

## Risk disclosures to mention aloud

- Demo financial statements, buyer records, contracts, lenders, credit outcomes and environmental figures are synthetic.
- OCR/text extraction and the rule engine can miss clauses and produce false positives.
- A flagged mismatch is not proof of fraud; legal and financial decisions require human review.
- Bank role switching is a UI demo, not secure authentication or a production-ready lender portal.
- The web app is the no-build `ui/web/dist`; there is no other UI source (the old React prototype was removed in v5).
