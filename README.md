# CashBridge — SME Finance Copilot for Export Enterprises

> **2026 Shenzhen International FinTechathon submission (Topic E: SME Finance Copilot)**
>
> **Principle:** *code calculates, AI writes.* Financial arithmetic and hard
> rules live in tested Python. Language models are confined to reading
> unstructured documents and drafting text.

---

## 0. What is built, what is simulated, what is not built

This section is first on purpose. The previous version of this README described
eight agents, a Streamlit application, a FastAPI service, a seed script and a
test suite. `agents/`, `api/`, `ui/` and `tests/` were empty directories, and
`data/seed_sandbox.py` did not exist, so a reviewer following the quickstart hit
an immediate crash. A reviewer who finds one claim unsupported reasonably
discounts the rest.

| Component | State |
|---|---|
| `core/forecasting_engine.py` — 13-week direct cash flow, CCC | **Built, tested** |
| `core/matching_engine.py` — 3-way match, subset-sum reconciliation | **Built, tested** |
| `core/funding_evaluator.py` — same-basis APR comparison and ranking | **Built, tested** |
| `core/cryptographic_registry.py` — hash-chained pledge registry | **Built, tested** |
| `security/permission_gatekeeper.py` — L0-L4 gate, hash-chained audit log | **Built, tested** |
| `security/otp_verifier.py` — human approval gate | **Built, tested** |
| `security/pii_masker.py` — identifier redaction | **Built, tested** |
| `security/bec_fraud_detector.py` — BEC screening | **Built, tested** |
| `core/pdf_compiler.py` — funding pack PDF | **Built, tested** |
| `demo_walkthrough.py` — runnable end-to-end flow | **Built, tested** (runs twice in a row from a clean checkout) |
| `config/runtime.py` — per-run evidence isolation | **Built, tested** |
| Financing partner terms (advance rates, fees, APR quotes) | **Simulated.** No funder has been approached or signed. |
| Buyer / counterparty verification | **Not built.** No registry, tax-authority or carrier lookup. |
| Bank Open API, e-invoice, factoring API, email/Zalo connectors | **Not built.** No integration, no mock service, no access agreement. |
| LLM document extraction (`agents/`) | **Not built.** The directory is empty. |
| Streamlit UI, FastAPI service | **Not built.** `Dockerfile`/`docker-compose.yml` are architectural sketches and will not start. |
| ML forecasting / payment-probability models | **Not built**, and deliberately so — see §4. |
| Cash flow figures, invoices, emails | **Synthetic.** Not customer data and not customer results. |

**What CashBridge does not promise.** It does not turn an invoice into cash.
A funder can decline on buyer, country, goods, dispute or contract grounds.
Three states are kept distinct throughout the code and the UI copy:

1. **Pre-screened eligible** — CashBridge's own checks pass.
2. **Pack accepted** — a funder agreed to review it.
3. **Facility disbursed** — money arrived.

Only state 1 is implemented. States 2 and 3 require a funding partner.

---

## 1. Problem

Export SMEs are profitable on paper and short of cash. Receivables sit for
45-90 days while suppliers want deposits up front:

```
CCC = DIO + DSO - DPO
```

Lenders ask for real estate collateral because they cannot independently verify
an unstructured international invoice or assess a foreign buyer. The target
user is a B2B export manufacturer or trader — wood processing, garments,
subcontracting — selling on credit into the US, Japan and China.

> Market figures previously quoted here (SME bank-loan access rates,
> international factoring as a share of trade volume) have been removed pending
> a citable source. Unsourced statistics in a pitch invite exactly the question
> you least want.

---

## 2. The loop

**Anticipate → Prove → Compare → Approve**

1. **Reconcile.** Bank credits against invoices, including multi-currency and
   bulk wires net of correspondent bank fees.
2. **Forecast.** Weekly cash position over 13 weeks; locate the trough, not
   just the first dip.
3. **Compare.** When a gap appears, rank financing options by true cost on cash
   actually received *and* by whether they close the gap.
4. **Pack.** Produce documentation tied to a content hash of the underlying
   documents, behind a human approval gate.

Run it:

```bash
python demo_walkthrough.py
```

Each run creates its own evidence directory under `data/demo_runs/` and writes
its audit log, pledge registry and funding pack there. The committed
`data/execution_evidence/` files stay empty and are never touched, so the demo
is repeatable and nothing in the archive has to be deleted before it works.

The first version of this script wrote into the committed directory, so a
second run raised `DoubleFinancingError` — and because the archive was
packaged after a demo run, it failed on the very first attempt from the ZIP.

---

## 3. Design decisions that carry the submission

### 3.1 Two cost measures, both reported

Every product is modelled as a **dated cash flow schedule** from the
borrower's point of view, and two figures are derived from it:

```
annualized_simple_cost = (total_cost / cash_in_hand) x (365 / days) x 100
effective_apr          = the annual rate that discounts the dated flows to
                         zero (an IRR), actual/365, compounded
```

`cash_in_hand` is cash the business can actually spend after upfront fees,
discounts and holdbacks.

The simple measure is the convention behind the familiar "2/10 net 30 is about
36% a year" figure. It is easy to check on paper and it is a fair same-basis
comparison — but it does not compound and it flattens a product with payments
at several dates into a single term, so it is **not** an effective APR under
any standard convention. An earlier version of this submission reported it
under the name `apr_pct`, which overstated how standardised the comparison was.
Both figures are now shown and the **ranking uses the effective rate**.

This matters because the products are not quoted on comparable bases. The
factoring fee is deducted at drawdown, so the borrower never holds the gross
advance, and the 15% reserve comes back at maturity — cash deferred, not a
cost, which only a dated schedule gets right. The buyer discount runs over a
term set by the payment terms, not by the time left on the invoice. The bridge
quotes a simple annual rate with interest at maturity. On the reference
invoice ($65,000, 45 days):

| Option | Headline | Cash in hand | Cost | Simple p.a. | **Effective APR** |
|---|---|---|---|---|---|
| Factoring (85% advance, 1.125% + $110) | 1.125% | $54,518.44 | $731.56 | 10.88% | **11.42%** |
| Buyer discount (2/10 net 55) | 2% | $63,700.00 | $1,300.00 | 16.55% | **17.81%** |
| Unsecured bridge | 18.90% | $65,000.00 | $1,514.59 | 18.90% | **20.54%** |

The bridge is the control: with no fee and interest at maturity its simple
cost must equal the quoted 18.90% exactly, and a test asserts it. Its
effective rate is legitimately higher, because the quote does not compound.

Each option publishes its `cash_flows`, so a reviewer can re-derive the rate
rather than taking it on trust.

### 3.2 Ranking by fit, then by cost

The cheapest option is not the best option if it leaves a hole. Against the
$66,350 peak need on the sandbox data, **no single product closes the gap** —
and factoring, the cheapest, leaves the largest shortfall ($11,831.56). The
engine therefore builds packages, sizing any amount-flexible facility to the
residual so no interest is paid on cash the business does not need.

### 3.2a A package is several facilities, not one product

A package carries its facilities separately, each with its own counterparty,
cash flows and conditions. An earlier version collapsed one into a single
`provider` string and a single advance figure, and the demo then wrote that
package into the pledge registry as **one pledge** — recording security over
the invoice on behalf of two funders, only one of which actually takes any.

Now:

- `LiquidityOption.facilities` lists each line separately.
- `Facility.pledges_receivable` marks which one takes security. Factoring
  does; a buyer discount settles the invoice and an unsecured bridge does not
  touch it. **Only a secured facility is registered as a pledge.**
- `check_facility_compatibility()` refuses two facilities that both claim the
  same receivable, and refuses factoring alongside a buyer discount on one
  invoice.
- It checks only conflicts CashBridge can see. **Exclusivity, negative-pledge
  and cross-default clauses in the real agreements have not been reviewed**,
  and no counterparty has agreed to lend alongside another. A package is a
  proposal, never an approved structure — the option's `cons` say so.

### 3.3 The trough, not the first dip

On the seed schedule the balance first goes negative in **week 6 (-$31,350)**
and reaches its low in **week 8 (-$56,350)**, staying negative for five
consecutive weeks and closing week 13 at -$11,850.

An earlier version of this submission described "a Week 6 shortfall of $31,350"
and proposed a $55,250 factoring advance against it. Net of fees that advance
releases $54,518.44, against a trough of $56,350 before any operating buffer —
the headline claim was arithmetically false. The facility is now sized to the
trough plus a $10,000 operating float, and `tests/test_financial_core.py`
asserts that the old narrative fails.

### 3.4 `REVIEW_REQUIRED` is a first-class outcome

Pass / fail is the wrong shape for a verification system. Three states are
distinguished:

- **finding** — the evidence present is inconsistent (amounts disagree);
- **absence of evidence** — a document is missing, so the check could not run;
- **ambiguity** — several answers fit, and the data does not choose between them.

Concretely: if two different invoice subsets both fit an incoming wire within
tolerance, the reconciliation is **not posted**; the alternatives are returned
for a human to resolve using the remittance advice. A bank-detail change from an
unrecognised sender is held for out-of-band verification rather than rated safe.

### 3.5 Honest limits on the cryptographic claims

**3-way match.** Establishes that the invoice, PO and bill of lading are
mutually consistent. A consistent set of forged documents passes every check.
Each bundle returns a `checks_not_performed` list naming what was not verified
(buyer existence, e-invoice status, carrier confirmation, dispute status,
pledges made outside this platform).

**Duplicate registry.** Detects a second pledge *made through CashBridge*,
indexed by both invoice ID and document content hash — so a renumbered
resubmission of the same trade is caught. It cannot see a pledge made to a
funder that does not use CashBridge. The industry problem is double financing
*across* funders; that needs a shared registry or a funder-side check.

**Audit log.** Hash-chained, so an edited, deleted or reordered entry is
detected. It is **not immutable against whoever controls the process**: that
party can recompute every hash from genesis and produce a valid chain.
`get_chain_head()` exposes the head hash precisely so a deployment can anchor it
externally — counter-signed by the funder, published, or written to append-only
storage. `tests/test_matching_and_registry.py` contains a test that performs
exactly this wholesale rewrite and shows it is caught *only* by the anchor.

**PII masking.** Reduces exposure of direct identifiers. It is not
anonymisation: prices, quantities, shipment dates, port pairs and buyer names
remain, and in a narrow export sector that combination often identifies the deal.
Whether a document may be sent to a third-party model at all is a data-rights
question that must be settled before the masker is called.

### 3.6 Five-tier permission model

| Level | Permission | Enforcement |
|---|---|---|
| `L0` | Read | Auto-approved |
| `L1` | Analyse and draft | Auto-approved |
| `L2` | Internal ledger write | Auto-approved, logged |
| `L3` | External action | Requires a verified OTP session bound to that exact action and resource, consumed on first use |
| `L4` | Money movement | Hard-blocked in code. No override exists. |

L3 approval is redeemed against the OTP module. It is not a boolean the caller
can set — an earlier version accepted `otp_verified=True` from the caller, so
any code path could declare its own human approval.

---

## 4. Why there is no ML model here

The 13-week projection is arithmetic: opening balance, scheduled receipts,
fixed outflows, deposits. A model predicting payment probability or forecast
error needs historical payment behaviour to train on and held-out data to be
measured against. Neither exists yet.

Reporting MAE or WAPE from synthetic data would measure nothing. The projection
is labelled a projection under stated assumptions — `ForecastSummary.assumptions`
carries them — and the honest next step is the scenario simulator
(`simulate_forecast`), which stresses buyer delays without claiming predictive
accuracy. ML belongs here once there is real payment history and an
out-of-sample measurement to report.

---

## 5. Verification

```bash
pip install -r requirements.txt
pytest -q                 # the full suite
pytest -q -m "not slow"   # skip the subprocess demo runs
```

`pytest` reports the count; this file deliberately does not, because a number
written in prose is stale on the next commit. (It said 91 when the suite had
92, which a reviewer noticed.)

Expected figures live in `tests/golden_values.py`, derived by hand from the
stated product terms and **importing nothing from `core/`** — so a passing
test is a check, not the engine agreeing with itself.

`tests/test_packaging.py` checks the archive itself: that the committed
evidence files are empty, that no run output is bundled, and that
`demo_walkthrough.py` completes **twice in a row** from a clean checkout. That
suite exists because an earlier archive shipped with a populated registry, so
the demo raised `DoubleFinancingError` on first run while every unit test
passed. Unit tests did not look inside the box.

This replaced an arrangement in which `config/settings.py` carried an
`expected_apr` per product and the evaluator contained:

```python
if invoice_id == "INV-2026-103":
    net_advance_a = 55250.00
    total_fee_a = 731.25     # also wrong: 55,250 x 1.125% + 110 = 731.5625
```

A substantial number of the tests are regressions against specific defects
found in that build, each naming what it covers:

| Area | Defect |
|---|---|
| APR | Hard-coded override reproducing spec numbers for the demo invoice |
| APR | Each product measured on a different denominator |
| APR | Discount term read from `days_until_due` instead of the payment terms |
| Ranking | Sorted by APR alone; the cheapest option left the largest shortfall |
| Combination | Pooled both facilities at full size — $119,518 drawn for a $66,350 need |
| Forecast | Narrative sized the facility to week 6 rather than the week 8 trough |
| Forecast | Delayed receipts clamped into week 13, fabricating an inflow |
| OTP | Blank code approved any L3 action outside demo mode (`_secret_otp` never set) |
| OTP | No expiry, no attempt limit, non-constant-time comparison |
| Gate | `otp_verified=True` accepted from the caller |
| Audit log | No chain at all, despite the claim; edits and deletions undetectable |
| Bundle hash | Covered only 3 identifiers plus today's date — amount changes invisible |
| Bundle hash | Changed daily, so the duplicate check could be beaten by waiting |
| Registry | Duplicate check by invoice ID only; renumbering defeated it |
| Registry | Partner and amount sat outside the block hash |
| Registry | Accepted the literal placeholder `"sha256hash"` as a bundle digest |
| Matching | $0.01 USD tolerance applied to JPY after conversion (~1.5 JPY slack) |
| Matching | Ambiguous reconciliations posted to the ledger silently |
| Matching | Largest-subset-first search, preferring coincidental basket matches |
| PII | `[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}` + IGNORECASE redacted SHIPMENT, CONTRACT, DELIVERY |
| PII | Unlabelled 9-13 digit pattern redacted invoice amounts as tax IDs |
| BEC | Twelve single phrases each triggering CRITICAL_BLOCK, incl. "effective immediately" |
| BEC | Bank-change request from an unrelated domain scored SAFE |
| BEC | Trust list contained `pacifictiber.vn`, a typo of the exporter's own domain |
| Packaging | Archive shipped with a populated registry; demo failed on first run |
| Packaging | Demo wrote into committed evidence, so it worked once and then broke |
| Rates | Linear cost annualisation reported under the name "true APR" |
| Rates | Factoring reserve not modelled as a dated flow, so the rate was off |
| Packages | Two funders collapsed into one `provider` and one registry pledge |
| Packages | Unsecured facilities recorded as pledges over the receivable |
| PDF | `cash_in_hand_usd=0.0` fell back to the gross advance via `or` |
| PDF | Bundle hash validated on length only, so `"z" * 64` passed |
| PDF | Em dashes and Vietnamese diacritics crashed generation outright |
| Docs | README stated a test count that was already wrong |

---

## 6. What to do before submitting

Carried over from review, in priority order.

**P0**
1. Interview three to five SME finance leads or chief accountants. Everything
   above is a build; none of it is demand evidence.
2. Decide the honest story for data connectivity. Either build labelled mock
   connectors for bank statements, e-invoices and factoring APIs, or state
   plainly that integration is unproven. §0 currently does the latter.
3. Quantify the value to the SME: reconciliation hours before and after,
   discrepancies caught pre-submission, cost of capital of the option they
   would have picked versus the one recommended, minus an assumed CashBridge
   fee. Label it an illustrative scenario, not a customer result.

**P1**
4. Build the LLM extraction layer against a labelled document set and report
   per-field accuracy and missing-field rate. `agents/` is empty, so the
   "code calculates, AI writes" split is currently asserted rather than shown.
5. Add `DISPUTED` handling end to end — the status exists in `MatchStatus` but
   nothing populates it.
6. Test `pdf_compiler` and check the pack renders the disclosures correctly.

**P2**
7. Cut the agent roster in the pitch to the ones on the main path. Eight agents
   invites "why not one workflow with a few tools?", and the answer has to be
   about permissions, testability and failure isolation — not that eight sounds
   more modern.

---

## 7. Business model

- **SaaS subscription**, tiered by connected accounts and invoice volume.
- **Lender referral fees**, disclosed to the SME.
- **White-label integration** with a bank's supply chain finance programme.

Referral revenue only exists once a funding partner does, and none of the three
has been validated with a paying customer. Treat §6 item 3 as the gate.

---

## 8. Principles

1. **Deterministic finance.** Arithmetic in tested Python, never generated.
2. **Traceable evidence.** Every figure reaches back to a document, a formula
   and a stated assumption.
3. **Controlled autonomy.** L0-L4, with a human gate on every external action
   and no autonomy over money.
4. **Stated limits.** Where the system cannot conclude, it says so and stops.

CashBridge turns scattered receivable data into a cash flow decision and a
funding pack a third party can re-derive. That is the claim, and §0 states
exactly how much of it runs today.
