# CashBridge — SME Finance Copilot for Export Enterprises

> **2026 Shenzhen International FinTechathon Submission (Topic E: SME Finance Copilot)**
>
> **Core Principle:** *"Code Calculates, AI Writes"* — Deterministic Python Financial Core + Zero-Trust Multi-Agent Orchestration (`L0`–`L4`) + SHA-256 Anti-Double-Financing Registry.

---

## 1. Project Overview

### Executive Summary & Problem Statement

- **The Core Crisis:** Export SMEs frequently face severe cash flow shortages despite being profitable on paper. Cash is trapped in long accounts receivable cycles (DSO of 45–90 days) and upfront supplier deposits, governed by the Cash Conversion Cycle:

  `CCC = DIO + DSO - DPO`

- **Collateral & Lending Barriers:** Only 9.3% of SMEs in Vietnam secure bank loans, compared with 56.1% of large enterprises. Traditional lenders demand real estate collateral because they cannot independently verify unstructured international invoices and foreign buyers. International factoring accounts for only approximately 0.04% of Vietnam's trade volume due to disconnected data and rigorous verification hurdles.

- **Target Niche:** B2B export manufacturing and trading SMEs, including wood processing, garments, and subcontracting businesses selling on credit to buyers in the US, Japan, and China.

---

## 2. Core Solution & Workflow Loop

CashBridge operates on a continuous four-step workflow:

**Anticipate → Prove → Compare & Choose → Approve**

1. **Multi-Source Reconciliation:** Automatically ingests bank statements, electronic invoices, bills of lading (B/L), and purchase orders (POs), handling multi-currency matching (`USD`, `JPY`, `CNY`) and intermediary bank fee variances.

2. **13-Week Cash Flow Forecasting:** Predicts weekly cash positions, flagging upcoming shortfalls caused by supplier deposit demands or delayed customer payments.

3. **Liquidity & APR Comparison:** When a shortfall is detected, CashBridge scans eligible invoices and ranks financing options by their true annualized cost (APR).

4. **Verifiable Funding Packs:** Generates tamper-evident documentation packages backed by SHA-256 audit logs and hash registries to prevent double-financing.

---

## 3. Architecture & Safety Design

### 3.1 Deterministic Core — "Code Calculates, AI Writes"

LLMs are strictly prohibited from performing arithmetic or financial calculations.

- **Python core (`core/`):** Handles all financial calculations, formulas, deterministic rules, and validation.
- **LLM layer (`agents/`):** Limited to unstructured text extraction, OCR parsing, document interpretation, and drafting text.
- **Verification:** Financial results are computed by deterministic code and independently tested by `pytest`.

### 3.2 Five-Tier Permission Model (`L0`–`L4`)

| Level | Permission | Description |
|---|---|---|
| `L0` | Read | Read-only access to authorized data sources. |
| `L1` | Analyze & Draft | Internal calculations, cash flow forecasts, and draft messaging. |
| `L2` | Internal Write | Automated internal ledger updates for high-confidence reconciliations. |
| `L3` | External Action | Submitting loan application packs or sending external communications. Every action requires explicit human approval via OTP (`123456` in demo mode). |
| `L4` | Money Movement | **Zero autonomy. Hard-blocked at the code level.** Banking transactions remain entirely human-executed. |

### 3.3 Security & Fraud Protection

- **Business Email Compromise (BEC) Protection:** Detects and blocks suspicious or fraudulent bank account change requests and spoofed lookalike domains.
- **PII Data Masking:** Masks IBAN, SWIFT codes, Tax IDs, and personal emails before data is transmitted to cloud-based LLMs.
- **Immutable Audit Trail:** Uses SHA-256 hash-linked audit logs (`data/execution_evidence/sandbox_operation_logs.jsonl`) to detect unauthorized changes.
- **Anti-Double-Financing:** Maintains a SHA-256 hash chain registry (`data/execution_evidence/audit_hash_registry.json`) — any attempt to finance an already-pledged invoice raises `DOUBLE_FINANCING_BLOCKED`.
- **Human-in-the-Loop Approval:** Enforces OTP approval for all `L3` external actions.

---

## 4. Agent & Module Breakdown

| Module | File | Responsibilities |
|---|---|---|
| **Coordinator** | `agents/coordinator.py` | State machine managing workflows, event triggers, and L0–L4 permission boundaries. |
| **CFO Assistant** | `agents/cfo_assistant.py` | Conversational interface providing financial metric queries and scenario analyses with source citations. Offline deterministic fallback mode included. |
| **Verification & Matching Engine** | `core/matching_engine.py` | 3-way matching (Invoice–PO–B/L), multi-currency subset-sum reconciliation (SSMP), and SHA-256 period locking. |
| **Forecasting Engine** | `core/forecasting_engine.py` | 13-week direct cash flow projections (`CCC = 82 days`) and What-If scenario modeling. |
| **Funding Evaluator** | `core/funding_evaluator.py` | True APR calculation and ranking: WeBank Factoring (10.74%) < Early Discount (16.55%) < Bridge (18.90%). |
| **Cryptographic Registry** | `core/cryptographic_registry.py` | SHA-256 hash-chain ledger preventing double-financing. |
| **PDF Compiler** | `core/pdf_compiler.py` | Generates tamper-evident Verifiable Funding Pack PDFs. |
| **Debt Collection Agent** | `agents/debt_collection_agent.py` | Automated multi-tier reminder schedules (Gentle → Firm → Escalation) and buyer response parsing. |
| **Buyer Retention Agent** | `agents/buyer_retention_agent.py` | Buyer profiles, churn risk calculation, and seasonal marketing plans. |

---

## 5. Business Model & Expansion Roadmap

### Revenue Streams

- **SaaS Subscriptions:** Monthly subscription fees tiered by connected bank accounts and invoice volume.
- **Lender Referral Fees:** Transparent referral fees from financing partners.
- **White-Label Bank Integration:** Supply chain financing integration modeled on WeBank's approach.

### Expansion Phases

- **Phase 1 — Vietnam Export SMEs:** Wood processing, textiles, and manufacturing.
- **Phase 2 — Domestic Supply Chains:** Distributors, freight forwarders, and household businesses.
- **Phase 3 — Regional Expansion:** ASEAN and China via open banking APIs, e-invoicing connectors, and EU Carbon Border Adjustment Mechanism (CBAM) compliance add-ons.

---

## 6. Quickstart Guide

### How to Run Locally — No Docker Required

Everything runs natively in Python. Docker files are included as static architectural deliverables for judges only.

### Prerequisites

- Python 3.11+
- Git

### Step 1: Clone the Repository & Install Dependencies

```bash
git clone https://github.com/stellarrng/cashbridge.git
cd cashbridge
pip install -r requirements.txt
```

### Step 2: Initialize the Sandbox Data & Evidence Logs

```bash
python data/seed_sandbox.py
```

Generates realistic English mock data for **Pacific Timber & Garment Exports Ltd.**, including multi-currency invoices (USD, JPY, CNY), a bulk wire transfer with a $35 correspondent bank fee variance, a spoofed BEC fraud email, and pre-populated execution logs.

### Step 3: Run the Automated Test Suite

```bash
pytest -v
```

Runs automated tests covering the deterministic financial engines, 3-way match, subset-sum reconciliation, L3 OTP gating, L4 money movement block, and SHA-256 anti-double-financing.

### Step 4: Launch the CashBridge Web Application

```bash
streamlit run ui/app.py
```

### API Keys & Demo Mode

The application includes a built-in **Deterministic Demo Mode** that runs 100% offline without an OpenAI API key. To enable live GPT-4o tool calling, create a `.env` file:

```dotenv
OPENAI_API_KEY=your_key
```

---

## 7. Project Principles

1. **Deterministic Finance:** Financial calculations are performed by tested Python code, not generated by an LLM.
2. **Verifiable Evidence:** Trade documents and reconciliation results provide traceable evidence for financing decisions.
3. **Controlled Autonomy:** Agent permissions follow the `L0`–`L4` model, with explicit human approval for external actions.
4. **Financial Integrity:** Audit trails, SHA-256 hashes, and anti-double-financing controls protect the integrity of funding documentation.

**CashBridge turns verified trade data into actionable cash flow insights and evidence-backed financing opportunities for export SMEs.**
