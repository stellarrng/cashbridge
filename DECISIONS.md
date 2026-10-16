# DECISIONS.md

Short log of design choices made during the build. `instructions.md` wins over every other document; where it was silent or ambiguous the simpler option was chosen and is recorded here.

## Alignment pass (2026-10-16)

The first scaffold was written against an older plan (company "Pacific Timber & Garment Exports Ltd.", a hard-coded Week 6 deficit of -USD 31,350, and a "WeBank Factoring" option). It conflicted with `instructions.md`. Phases 0 to 2 were rebuilt to the spec: `config/`, `schemas/`, `core/` and `security/` were rewritten and the old `core/cryptographic_registry.py` and `core/pdf_compiler.py` were superseded (`invoice_registry.py` replaces the first; the PDF pack comes back in Step 5.3).

Corrections made to the planning documents so the spec and plan agree:
- `buildplan.md` sample snapshot: week 6 closed negative (-1,610) although the spec says the first negative week is 7. Week 6 now closes at 8,390 (`at_risk`) and week 7 opens from it; week 7 still closes at -44,300.
- `buildplan.md` sample snapshot: bridge-loan interest corrected to 1,587.95 (46,000 x 14% x 90/365), total 2,047.95. APR stays 18.2%.
- File references now use the real file names `instructions.md` and `buildplan.md`.

## Choices

| # | Decision | Why |
|---|---|---|
| 1 | Money is integer minor units (`Money`) in document models and `Decimal` USD in forecast and funding models. `to_contract()` converts to plain JSON numbers. | Step 0.3: no floats for money. The UI contract needs JSON numbers. |
| 2 | `ExtractedField` uses `page` (spec section 6), not `source_page` (buildplan step text). | The spec wins. |
| 3 | Tier enum member is `L3_EXTERNAL` (not `L3_EXTERNAL_OTP`). | Matches the spec and the UI contract `tier_monitor` values. |
| 4 | `OTP_SECRET` falls back to the public demo secret `JBSWY3DPEHPK3PXP` when unset. | Tests and the offline demo must work with no `.env`. The secret is public by design and listed as a residual risk. |
| 5 | A DIO/DSO/DPO component is rounded to 0.1 day and CCC is the sum of the rounded components. | The published numbers always add up. |
| 6 | Net funds in the APR formula: factoring = the advance (fee and interest are paid at settlement); bridge loan = amount minus the upfront fee; discount = invoice minus discount. | This reproduces the spec table (17.1 / 18.2 / 37.2 / 14.9). |
| 7 | Simple interest uses actual/365. | Matches the published whitepaper formula. |
| 8 | Tolerance reconciliation: same currency needs `0 <= gap <= USD 50` (bank fee only reduces the amount received); different currency allows `abs(gap) <= USD 50` (`fx_difference`, confidence 0.9, so a human approves). | Overpayments are not fees. FX differences can go either way. |
| 9 | Reconciliation `gap` is in USD. | The fee tolerance is a USD constant. |
| 10 | 3-way match: missing documents, buyer, seller or currency mismatches are `BLOCKED`; amount, quantity, package and port differences are `FLAGGED`. | Parties disagreeing is a different risk than goods differing. |
| 11 | Shortfall attribution splits the first shortfall into deposits, late invoice value not yet received, tariff and FX effects, and one baseline term (opening cash plus full-value scheduled inflows minus recurring costs). The terms sum to the shortfall exactly. | Step 1.3 requires attribution to sum to the shortfall; the baseline term is negative when the business is cash-positive without the stress drivers. |
| 12 | What-if controls: `dso_change_days` shifts every due date; `deposit_pct` replaces the percentage on adjustable deposits; `tariff_shared_pct` cuts US invoice value by `SCENARIO_TARIFF_RATE_PCT` (10%, a hypothetical scenario rate, not a current tariff) times the share; `fx_change_pct` scales non-USD receivables. | Every control must really change inputs (Step 1.3). The spec forbids quoting a current tariff rate. |
| 13 | Payroll is paid in any week that contains a month-end date. | Simple, deterministic. |
| 14 | The gatekeeper takes the tool's registered tier as the floor. A call that declares a lower tier is `BLOCKED`. | An agent cannot downgrade `submit_pack` to L0 by lying about the tier. |
| 15 | An L3 approval works once and only inside its 120 s window; a used or expired approval is `REJECTED`. `record_approval()` writes the `APPROVED` / `REJECTED` line for each OTP attempt. | Spec Rule 2: used once, within 120 seconds. |
| 16 | `human_approver` on an L2 call lets a named human (Lan) clear a fuzzy write. | Spec: fuzzy matches need Lan. |
| 17 | BEC verdicts: any bank-change request, lookalike sender or unverified quoted account is `BLOCKED`; an unknown sender with no signals is `SUSPICIOUS`. | Spec Rule 3. |
| 18 | `invoice_registry.py` and `period_lock.py` take storage paths and clocks as arguments. | No hidden globals; tests use `tmp_path` and a fixed clock. |
| 20 | Seed tuning: opening cash USD 80,000, weekly fixed costs USD 38,000, payroll USD 15,000 on month-end weeks, PO-2214 deposit 30% of USD 92,000 in week 7, INV-1026 `p_on_time` 0.42. Result: first negative week 7, shortfall about USD 42.2k, advance USD 48,000 covers it. | Spec section 2.3 targets. The `buildplan.md` sample snapshot values (cash 61,200) are illustrative only. |
| 21 | `p_on_time` is stored per open invoice in the seed until the buyer risk agent (Step 6.1) estimates it. | The forecast needs it now. |
| 22 | INV-1027 belongs to the same US buyer as INV-1021 to 1026; subset-sum stays unique with it present (checked). Extra open invoices for other buyers (INV-1028 to 1035) give the forecast realistic weekly inflows without touching the wire match. | The six-invoice set in the spec is the buyer's open invoices at wire time. |
| 23 | TXN-0913 (exact INV-1025) and TXN-0914 (JPY 1,520,000, `PAYMENT OCT`, no match, NEEDS_HUMAN) are included to match the UI sample reconciliation table. | UI contract sample. |
| 24 | `data/loader.py` is the only reader of `sandbox_inputs/`; engines in `core/` receive typed data. | Keeps `core/` free of I/O. |
| 25 | After any provider failure (timeout, network, auth) the LLM client stays in `offline-demo` until `reset()`. A schema failure or a number-check rejection falls back for that one call only. | Spec: a failed call sets DEMO_MODE. A single bad model reply should not end live mode. |
| 26 | `complete_structured` runs the number lock by default with `locked_metrics`; field extraction passes `check_numbers=False` because its numbers come from a document, not from the model. | Spec: free-text output must pass the number lock. |
| 27 | Replies are unmasked locally after validation; the provider only ever sees masked text. | Spec: tokens are reversible and the map never leaves memory. |
| 28 | `weekly_run()` stops at `INVOICE_VERIFIED` so the Director chooses the option and presses "Prepare pack". `weekly_run(auto_prepare=True)` picks the top-ranked option and drafts the pack, reaching `AWAITING_APPROVAL` with no manual step (the Step 3.3 test). | Matches the demo story (step 6) and the test requirement. |
| 29 | Invoice nomination rule: verify every open invoice, then nominate the largest USD invoice that is ELIGIBLE, not in the registry, has a valid tax ID and is not yet due. Flagged invoices (INV-1027) are excluded. A registered invoice is never nominated again. | Deterministic and explainable; yields INV-1030. |
| 30 | `NEEDS_HUMAN` stops the case only when it cannot continue (no eligible invoice, cover letter fails the number lock). One unmatched bank transaction (TXN-0914) is listed as NEEDS_HUMAN but the case continues. `BLOCKED` is used when the gatekeeper refuses a call the pipeline itself made. Guard hits on emails (BEC, injection) become alerts only. | Spec: email content never decides actions; the story continues after the BEC block. |
| 31 | Only factoring and bridge-loan options produce a lender pack. An early-payment discount is agreed with the buyer, so `prepare_pack` refuses it. Only factoring writes the invoice to the registry. | A discount does not pledge the invoice to a lender. |
| 32 | The double-financing pre-check runs after the OTP is verified and before the L3 gate, so a duplicate attempt does not spend the approval. Retrying a financed invoice writes a `BLOCKED` audit line. | Keeps the demo negative test visible in the evidence. |
| 33 | `reset()` deletes the audit log and registry in the coordinator's evidence folder, builds a fresh gatekeeper and OTP verifier, and reruns the Monday flow. | A clean demo needs a clean chain; a fresh verifier avoids a false "replayed" on the same TOTP code. |
| 34 | The lender reference comes from an injected `lender_submit`; the default is now `api/lender_connector_mock.submit`. | The connector is the white-label integration point; it is MOCK and claims no real API. |
| 35 | Story step 10 needed a reminder and a reply-to-forecast path before Step 5.2, so a minimal real version exists: `agents/collections_agent.py` (gentle reminder template, date parser), `Coordinator.draft_reminder / approve_draft / on_buyer_reply`, and `OpenReceivable.promised_date` in the forecast. Step 5.2 adds the full ladder, JA/ZH templates and the OTP-gated send. | The 11-step story must run end to end now. |
| 36 | A dated promise replaces the probability model for that invoice: the whole amount lands in the promised week. | A stated date is stronger evidence than a historical rate. |
| 37 | Lan approving a draft is logged as an `APPROVED` audit line (L1 `draft_text`); the reminder then shows `awaiting_approval` because sending (`send_email`, L3) still needs the Director's OTP. The story does not send it. | Spec: every external email is L3 with OTP. |
| 38 | The story uses a simulated clock (07:00 UTC, +1 s per call), so audit lines, registry block, anchor and summary are byte-identical on every run. The TOTP is generated from the demo secret on that clock. | Reproducible execution evidence for judges. |
| 39 | The story's step 6 briefing is a template checked by the number lock (`[source: forecast run ...]` citations); the CFO assistant that writes it arrives in Step 5.1. | Keeps step 6 real without building Step 5.1 early. |
| 40 | The story also logs a refused L4 `update_payee` and a rejected tampered draft, so the audit log shows all five tiers. | Step 3.4 acceptance: L4-blocked line present. |
| 41 | The UI is React 18 + TypeScript (Vite) instead of Streamlit, as requested. It never calculates money: it renders `ui/backend_real.py` output through JSON endpoints in `api/main.py`. `instructions.md` section 5 and `buildplan.md` Phase 4 were rewritten to match. | The owner asked for a React UI that does not look generated. The contract is unchanged, so engines and tests are unaffected. |
| 42 | `api/main.py` is now P0 (it serves the UI) and one process on port 8000 serves both the API and the built bundle. The old two-service Docker layout became one service. | One command, one port, no CORS in production. |
| 43 | The built bundle `ui/web/dist` is committed. `make run` needs no Node and no network; `make ui` rebuilds it. | The spec requires a fresh clone to run offline. |
| 44 | Design system: dark editorial palette with one gold accent; green only for success, red only for deficit, block or warning; Archivo for headings, IBM Plex for text and numerals, all bundled; hand-built SVG charts; no component, chart or icon libraries. `tests/test_ui_bundle.py` enforces the palette, no gradients, no external URLs and no UI libraries. | Matches the brief: human-designed look, colour as utility only. |
| 45 | Chart and bar geometry in the UI derives pixel positions from values. It is drawing only; no financial value is computed in `ui/web/src`. | Needed to draw charts without a library. |
| 46 | The live UI keeps its session in `data/runtime/` (git-ignored), apart from the committed `data/execution_evidence/`. Every server start clears that folder's audit log and registry and runs the Monday flow again. | Clicking Reset or restarting must never alter the committed evidence, and a restart must not inherit a registered invoice from an earlier click-through. |
| 47 | There is no stub backend. The design-time sample is the JSON in `docs/UI_CONTRACT.md`, and `tests/test_ui_contract.py` checks the real snapshot against it. Added contract keys: `meta.last_error`, `pii_inspector.note`. | A stub would only duplicate the real backend. |
| 48 | The Node install on the build machine had no `npm` (its global `lib/node_modules` folder is missing). The bundle was built with a separate npm copy; nothing global was changed. Repair Node (for example `nvm reinstall 22`) before running `make ui`. | Environment note for whoever rebuilds the UI. |
| 49 | UI revision for navigation and tone: sticky top bar with the sections, a four-step journey strip with one "next" action, hash URLs, number-key shortcuts, in-page jump links, collapsible side panels, and the headline shown only on the first page (other pages get a short title and a one-line summary). | The first version buried the tabs under a tall header and repeated it on every page. |
| 50 | Look revision: Newsreader serif for headlines and figures, IBM Plex Sans with tabular numerals for text and tables, mono only for hashes; sentence-case labels instead of spaced mono capitals; plain-language section titles and alert reasons. `instructions.md` section 5.1 updated. | Spaced mono capitals and monospace numerals read as a generated template. |
| 51 | Journey progress is derived from the case (an option chosen means the earlier steps are behind you), not only from pages viewed. Repeated identical audit lines are folded in the side panel ("scan_email ×5"). | A click-through that skips a page must not send the user back to it. |
| 52 | Layout rebalance: one centred column (max 1184 px) with the header aligned to the same edges; the assistant, activity and privacy panels moved from a permanent left column to a right-hand drawer (button "Assistant", Esc or click outside to close). Display type returned to heavy condensed Archivo for headlines and figures; Plex Sans for text; sentence-case labels and plain copy kept. `instructions.md` section 5.1 updated. | The permanent sidebar was mostly empty and pushed the page off-centre; the serif headline felt detached from the data. |
| 53 | The README describes the project and how to set it up and run it; it carries no status, step numbers or "Built / Not built" table. Progress is tracked only in the PROGRESS table of `buildplan.md`. `instructions.md` section 0 and 6 and `buildplan.md` Step 7.1 updated to match. | Owner instruction. A README that mixes status with description goes stale and misleads readers. |
| 19 | `instructions.md` stays in `.gitignore`, as before. | It was ignored in the original repo. Remove the line to publish it. |

## Control to file to test

| Control | File | Test |
|---|---|---|
| Tier model L0 to L4, L4 always blocked | `security/permission_gatekeeper.py` (`check`) | `tests/test_gatekeeper_otp.py::test_l4_is_blocked_even_with_approval` |
| Agent tool allowlists, only coordinator has `submit_pack` / `send_email` | `config/tool_allowlist.py` | `tests/test_config.py`, `tests/test_gatekeeper_otp.py::test_disallowed_and_unknown_tools_are_blocked` |
| L3 needs OTP bound to action hash | `security/otp_verifier.py`, gatekeeper `_decide_l3` | `test_l3_without_otp_waits`, `test_approval_for_pack_a_cannot_send_pack_b`, `test_editing_the_payload_after_approval_invalidates_it` |
| OTP replay and expiry | `security/otp_verifier.py` (`verify`) | `test_replayed_code_is_refused`, `test_code_after_121_seconds_is_expired` |
| Tamper-evident audit log | `security/audit_log.py` (`verify_chain`) | `test_tampered_line_is_detected_at_its_seq`, `test_deleted_middle_line_is_detected` |
| One audit line per decision | `security/permission_gatekeeper.py` | `test_exactly_one_audit_line_per_call` |
| PII masking | `security/pii_masker.py` | `tests/test_guards.py::test_masking_removes_every_raw_sensitive_value_and_round_trips` |
| Prompt-injection guard | `security/injection_guard.py` | `test_injection_text_is_flagged`, `test_wrap_quotes_data_and_neutralises_embedded_delimiters` |
| Number lock | `security/number_check.py` | `test_invented_number_is_rejected_and_locked_number_passes` |
| BEC detection | `security/bec_fraud_detector.py` | `test_lookalike_domain_plus_bank_change_is_blocked_and_contacts_unchanged` |
| Anti-double-financing registry | `core/invoice_registry.py` | `tests/test_registry.py` |
| Period lock | `core/period_lock.py` | `test_period_lock_detects_changed_row` |
| Deterministic engines (matching, forecast, APR) | `core/` | `tests/test_matching.py`, `tests/test_forecast_and_apr.py` |
