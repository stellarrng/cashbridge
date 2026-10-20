"""Sections 1-5 of the technical documentation (v9.1)."""
from docs.technical.tdoc import Diagram, Sequence, TEXT_W

F = "docs/technical/figures/"

BLOCKS = [
    ("h1", "Introduction", "sec:intro"),
    ("h2", "Problem statement", None),
    ("p", "An SME can be profitable on paper and still miss payroll, because cash leaves on a contractual schedule while receipts "
          "arrive on a buyer’s schedule. When a shortfall is foreseen, three questions follow in sequence: <i>when</i> does the balance "
          "turn negative; <i>which</i> receivables can credibly support a financing request; and <i>what</i> does each financing route "
          "really cost and how badly can it fail. In practice each question is answered in a different tool, by a different person, "
          "with different evidence, and the lender receives a pack whose figures cannot be traced back to their source."),
    ("p", "Two further problems sit around that workflow. The commercial contract that creates the receivable is usually drafted "
          "by hand, often without the clauses a lender needs (a right to assign the receivable, a protected payee account), so the "
          "invoice it produces is harder to finance and easier to defraud. And the receivable itself can be pledged to two lenders "
          "at once: no single lender, and no single SME installation, can see the other side’s books."),
    ("p", "CashBridge treats the three questions, the approval that follows them, the contract that precedes them and the "
          "uniqueness of the pledged receivable as one accountable workflow. The prototype also contains a contract- and "
          "document-intelligence module (OCR, clause and amount analysis, invoice reconciliation, deterministic drafting with Word "
          "export) and planning tools for capital allocation, project and bid funding, and green investment; these share the same "
          "evidence and approval controls and are described in Sections [[sec:contracts]] and [[sec:planning]]. The contribution of "
          "the prototype is not a single model but the way models, controls and evidence are composed so that an autonomous agent "
          "can prepare a financing decision without ever being able to commit the firm."),
    ("h2", "Design principles", None),
    ("table", ["Principle", "Engineering consequence"], [
        ["Financial facts before language", "Money, annualised cost, probability bands, policy results and contract figures are produced by local code. Text is a rendering of results, never a source of them."],
        ["Agency with bounded authority", "The Autopilot selects only from an authorised set of next steps. A guard that is independent of the planner can reject any proposal."],
        ["Evidence travels with the decision", "A locked figure carries its formula, its input records, the source file hash and any later correction, so a reviewer can re-derive it."],
        ["Humans own irreversible decisions", "External release needs a named Director and an action-bound one-time code. No agent holds a money-movement tool."],
        ["Fail closed where a check is promised", "When a control is enabled and cannot be evaluated (data gate in production, the cross-lender register when in use), the financing action is refused rather than allowed unchecked."],
    ], [1.15, 3.2], "tab:principles", "The five principles and how each is enforced in the implementation."),
    ("h2", "Scope and non-claims", None),
    ("p", "The system is a sandboxed prototype operating on a synthetic SME case (a timber exporter with two preparers, two approvers "
          "and a mock lender). The following are <b>not</b> claimed: live bank feeds, production credit eligibility, binding electronic "
          "signatures, actual disbursement, enterprise single sign-on, a certified KYC/AML process, legal advice, a deployment on a "
          "public or consortium blockchain, or an independent penetration test. The consortium ledger of Section [[sec:chain]] runs "
          "real EVM bytecode on an in-process chain on which the other lenders are simulated accounts. Forecast and risk models have "
          "been validated on public data and synthetic cases; they have not been validated on the cash flows of real firms."),
    ("h2", "What changed in v9.1", None),
    ("p", "This revision of the documentation describes release 9.1. The changes below were made after an internal review of the "
          "v9 security self-assessment; each is specified in the section named and tested by the module named."),
    ("table", ["Change", "Where specified", "Evidence"], [
        ["Contract drafting rebuilt: 21 articles and three schedules from a fixed clause library, English, Vietnamese or bilingual, amounts in words, formatted Word export", "Section [[sec:drafting]]", "tests/test_contract_drafting.py"],
        ["Contract analyser: no false alarms on well-formed contracts (line-level instruction scan, schedule-line milestones, Vietnamese wording)", "Section [[sec:analyser]]", "same; 9 of 9 generated drafts read back with 0 flags"],
        ["PDF active-content screen before parsing or storage", "Section [[sec:pdfscreen]]", "tests/test_pdf_screen.py; scorecard DOC-01"],
        ["Consortium ledger on an EVM: HMAC-commitment invoice register and Merkle anchoring of the audit log", "Section [[sec:chain]]", "tests/test_chain.py; scorecard FIN-04, EVID-04"],
        ["Failure semantics: register fails closed when in use and is required in production; anchor failures are recorded and shown", "Section [[sec:chainmodes]]", "tests/test_chain.py (fail-closed cases)"],
    ], [3.0, 1.15, 1.75], "tab:changes", "Release 9.1 changes."),

    ("h1", "Requirements", "sec:req"),
    ("p", "Seven engineering requirements drive the design. Each is paired with an acceptance signal that can be observed in the "
          "running system or in the archived test output."),
    ("table", ["ID", "Requirement", "Acceptance signal"], [
        ["R1", "Detect a cash gap in time", "13-week weekly cash balance, first shortfall week, driver attribution and alerts."],
        ["R2", "Ground every financing option", "Receivable three-way matching, an eligibility gate, and cost, tenor and annualised cost for each option."],
        ["R3", "Show downside, not only price", "Scenario paths, negative-week probability, CVaR<sub>95</sub>, a feasible plan and the binding policy limit."],
        ["R4", "Complete an accountable case", "Accountant prepares; Director releases with OTP; lender reviews evidence; mock decision returns to the SME."],
        ["R5", "Keep autonomous authority bounded", "Tier checks L0 to L4, per-agent allowlists, a refusal log, and no money-movement tool."],
        ["R6", "Make explanations verifiable", "Hash-chained audit log anchored outside the log file, evidence statuses, click-to-source provenance, versioned encrypted documents."],
        ["R7", "Keep a receivable financeable once", "Contracts carry an assignment clause and a payee call-back clause; a second lender’s registration of the same invoice is refused and funding is not recorded."],
    ], [0.35, 1.45, 3.4], "tab:req", "Requirements and acceptance signals."),

    ("h1", "System architecture", "sec:arch"),
    ("h2", "Logical layers", None),
    ("p", "The implementation separates a control plane from the computation it governs. A request enters a FastAPI gateway that "
          "verifies a signed session, the caller’s role and tenant. It is then routed to a typed workflow in the coordinator, not to a "
          "free-form planner. The coordinator calls local specialist engines and writes every consequential step to a tamper-evident "
          "audit log. The logical diagram does not imply one deployed service per agent: all components run in one Python process "
          "behind the API, including the optional in-process EVM of Section [[sec:chain]]."),
    ("fig", F + "fig_architecture.png", TEXT_W * 0.86,
     "Logical architecture, reproduced from the project README (Mermaid source rendered unchanged; line breaks were inserted inside "
     "node labels for legibility). Control passes from the human through the signed-session gate to the typed workflow orchestrator "
     "and the local agents. The optional language model receives only a public topic identifier and has no path to case data or tools.", "fig:arch"),
    ("h2", "Module map", None),
    ("table", ["Layer", "Modules", "Responsibility"], [
        ["Gateway", "api/main.py, api/lender_adapters.py", "About 95 REST routes; session and role checks; quote adapters with signed webhooks."],
        ["Orchestration", "agents/coordinator.py, autopilot.py, intelligence_core.py", "Case state, workflow transitions, bounded planning, pack lifecycle."],
        ["Contract intelligence", "contracts/intelligence, extraction, drafting, words, docx_export; agents/decision_copilot", "Bounded OCR, clause and amount analysis, contract–invoice reconciliation, clause-library drafting, Word rendering, policy workflows."],
        ["Planning tools", "core/financial_intelligence, project_cashflow, capital_planning, green_finance", "Ratios, budget and bid stress, milestone waterfall, capital allocation, green pre-screening and cash impact."],
        ["Specialist agents", "document_agent, buyer_risk_agent, collections_agent, cfo_assistant, concept_explainer", "Local extraction, scoring, reminder drafting, constrained explanations."],
        ["Finance core", "core/forecasting_engine, payment_timing, conformal, funding_evaluator, funding_schedule, funding_coverage, scenario_simulator", "Forecast, receipt timing, calibrated intervals, cost, settlement and coverage."],
        ["Integrity", "core/matching_engine, financing_gate, data_reliability, source_attestation, provenance, invoice_registry, period_lock", "Matching, fail-closed gate, signed attestations, lineage, duplicate detection within the installation."],
        ["Consortium ledger", "chain/contracts/*.vy, chain/ledger.py, chain/merkle.py, chain/build/*.json", "Cross-lender invoice register keyed by commitments; audit-log Merkle anchors; in-process EVM."],
        ["Security", "security/auth, permission_gatekeeper, otp_verifier, audit_log, injection_guard, number_check, bec_fraud_detector, pii_masker, pdf_screen", "Identity, authorisation, approvals, tamper evidence and input defences."],
        ["Workspace", "workspace/store, evidence_vault, corrections", "Versioned requests, messages, encrypted evidence, reviewed corrections."],
        ["Client", "frontend/src (React 18, TypeScript, Vite)", "Feature modules per workspace screen; no business logic is trusted in the browser."],
    ], [0.95, 2.1, 2.25], "tab:modules", "Source modules by architectural layer."),
    ("p", "The deterministic analysis engines added in the financial and contract intelligence extension (financial ratios, contract "
          "rules with local OCR, project and bid stress, green-upgrade payback) hang off the same gateway, as shown in Figure [[fig:engines]]."),
    ("fig", F + "fig_engines.png", TEXT_W * 0.92,
     "Deterministic analysis engines and their audit path, reproduced from docs/INTELLIGENCE_EXTENSION.md (Mermaid source rendered "
     "unchanged apart from label line breaks). No engine calls a language model; human verification of contract output is mandatory.", "fig:engines"),
    ("h2", "Runtime modes and technology stack", None),
    ("p", "The backend is Python with FastAPI, Pydantic v2 for typed inputs, NumPy for numerical work, and scikit-learn when installed "
          "(an equivalent NumPy Newton solver is used otherwise, and a test asserts that both agree). Cryptography uses the "
          "<font name='Mono' size='9'>cryptography</font> package (AES-256-GCM) and the standard library (HMAC-SHA256, SHA-256). "
          "Persistence is SQLite in WAL mode. Reports are generated with fpdf2 and python-docx. The optional consortium ledger uses "
          "web3.py with eth-tester and py-evm, the Python reference implementation of the Ethereum Virtual Machine; the contracts are "
          "written in Vyper 0.4.3 and their compiled bytecode is committed, so the server needs no compiler. The client is React 18 "
          "with TypeScript, built with Vite."),
    ("p", "Two deployment modes exist. In DEMO mode, one-click demo accounts and a public demo OTP secret keep the system runnable "
          "with zero configuration, and the data gate of Section [[sec:gate]] is off unless "
          "<font name='Mono' size='9'>CASHBRIDGE_REQUIRE_DATA_GATE=1</font> is set. In PRODUCTION mode the process refuses to start if "
          "any demo shortcut would remain active (a default OTP secret, a session secret shorter than 32 characters, no configured "
          "accounts, or no vault key); the data gate is forced on; the cross-lender register defaults to <i>required</i> "
          "(Section [[sec:chainmodes]]); and demo login, reset and tamper demonstrations are disabled. An unrecognised mode string "
          "(for example a misspelling) is treated as PRODUCTION, so that a configuration error fails closed."),

    ("h1", "Governed agent execution", "sec:gov"),
    ("h2", "Permission tiers", None),
    ("p", "Every tool is registered with exactly one tier in <font name='Mono' size='9'>config/tool_allowlist.py</font>. A permission "
          "gatekeeper checks the tier, the calling agent’s allowlist and, for writes, whether a human is required, and it logs every refusal."),
    ("table", ["Tier", "Class", "Representative tools", "Boundary"], [
        ["L0", "Read", "read_bank_statements, read_documents, read_payment_history", "Session, tenant and role checked."],
        ["L1", "Analyse", "run_forecast, three_way_match, rank_funding_options, score_buyer_risk, plan_liquidity", "Must be on the agent’s allowlist; no outside effect."],
        ["L2", "Internal write", "ledger_write, lock_period, propose_model_update, record_plan_decision", "Deterministic, or a named human; model activation is always human."],
        ["L3", "External", "submit_pack, send_email", "Coordinator only; Director OTP bound to the exact payload."],
        ["L4", "Money movement", "transfer_funds, update_payee, make_payment", "Recognised only so it can be refused; on no allowlist."],
    ], [0.35, 0.8, 2.3, 2.0], "tab:tiers", "The five-tier permission model."),
    ("p", "Allowlists are per agent. The coordinator alone holds the two L3 tools. The buyer-risk agent can read payment history and "
          "score risk and nothing else; the Intelligence Core may plan, simulate and propose a model update but cannot activate one. "
          "The lender’s reviewer can read documents and record a credit decision but cannot touch the pack."),
    ("p", "Two ledger operations sit outside the agent allowlists and are deliberately classed as internal records (L2), not as L3 "
          "releases. Publishing the Merkle root of the audit log is a digest of records the SME already holds; it is triggered "
          "automatically at release and at the lender’s decision, and may also be triggered manually by an authorised Accountant or "
          "Director without the pack-release OTP; the manual publication is attributed to that user in the audit log. Registering a "
          "funded invoice is performed for the lender inside its credit decision (Section [[sec:chainmodes]]). Neither operation can "
          "release a pack, change a payee or move money."),
    ("h2", "The Finance Autopilot as a finite-state agent", None),
    ("p", "The Autopilot observes case state, selects the next step, runs a tool, records the result as evidence, and stops or escalates "
          "when the evidence does not support progress. Its transitions are fixed by the table <font name='Mono' size='9'>ALLOWED_NEXT</font>."),
    ("diagram", Diagram(TEXT_W, 118, {
        "a": (0, 66, 64, 34, "analyze\ncash gap", False), "b": (77, 66, 64, 34, "verify\nreceivables", False),
        "c": (154, 66, 64, 34, "compare\nfunding options", False), "d": (231, 66, 64, 34, "stress\ntest", False),
        "e": (308, 66, 64, 34, "prepare\nfunding pack", False), "f": (385, 66, 64, 34, "request\napproval", False),
        "s": (0, 4, 96, 30, "stop\n(no shortfall)", True), "x": (140, 4, 190, 30, "escalate to a human\n(no eligible receivable, option or plan; gate blocks)", True),
        "h": (350, 4, 100, 30, "stop: hand over\nto the Director", True)},
        [("a", "b", ""), ("b", "c", ""), ("c", "d", ""), ("d", "e", ""), ("e", "f", ""), ("a", "s", ""), ("b", "x", ""), ("c", "x", ""),
         ("d", "x", ""), ("e", "x", ""), ("f", "h", "")], title="START"),
     "Authorised transitions of the Finance Autopilot. Terminal states stop or escalate. The agent has no transition to release a pack.", "fig:fsm"),
    ("p", "The default planner is a deterministic policy (<font name='Mono' size='9'>deterministic-policy-v1</font>). A different planner, "
          "including a language-model planner, can be injected through a callback, but it is held to the same guard: if its proposal "
          "differs from the policy choice, the proposal is classified and refused with a reason (money movement is never available to "
          "an agent; external actions require the Director; the step is not an allowed successor; or the evidence does not yet support "
          "the step). The refusal is appended to the audit log and the safe policy step is used. A planner that raises an exception "
          "cannot halt the run."),
    ("p", "Each step registers claims with an evidence status drawn from six values: VERIFIED, CALCULATED, MODEL_ESTIMATE, ASSUMPTION, "
          "NEEDS_HUMAN and NOT_VERIFIABLE_HERE. A reader can therefore distinguish a confirmed input from an engine-computed amount, a "
          "model estimate, an assumption, and a gap that the system cannot check."),
    ("h2", "Action-bound one-time approval", "sec:otp"),
    ("p", "An L3 action requires a time-based one-time code (RFC 6238) from the Director. The code is not a generic login factor; it is "
          "bound to the action by hashing the action type with the canonical JSON of its payload:"),
    ("eq", "action_hash = SHA-256( action_type ‖ canonical_json(payload) )", "eq:actionhash"),
    ("p", "An approval is accepted only if the code is current, matches the challenge’s action_hash, has not been consumed, and arrives "
          "within 120 seconds. Approving pack A therefore cannot authorise pack B, and altering the payload after approval invalidates "
          "it. A challenge is voided after five wrong attempts. The four error classes returned are invalid_code, expired, replayed and "
          "payload_mismatch. The coordinator additionally refuses an approval from the user who prepared the pack, enforcing segregation "
          "of duties in two places (permission matrix and coordinator)."),
    ("p", "<b>Code generation and guess probability.</b> The one-time code is the time-based construction of [1, 2]. With shared secret "
          "<i>K</i>, step <i>X</i> = 30 s and time <i>t</i>, the counter is <i>c</i> = floor(<i>t</i> / <i>X</i>) and"),
    ("eq", "code( <i>t</i> ) = ( Truncate( HMAC<sub><i>K</i></sub>( <i>c</i> ) ) mod 2<super>31</super> ) mod 10<super>6</super>", "eq:totp"),
    ("p", "where Truncate extracts four bytes at an offset taken from the low nibble of the digest, giving a six-digit code. The verifier "
          "accepts the current step and one step either side (clock drift), so three of the 10<super>6</super> values are valid at any "
          "time. A random guess therefore succeeds with probability at most 3 × 10<super>−6</super>, and because a challenge is voided "
          "after five failures, an attacker without the secret succeeds on a given challenge with probability at most 1.5 × "
          "10<super>−5</super>. Replay protection is separate: the pair (action hash, code) is remembered once consumed. That memory is "
          "held by the verifier inside the running server process; it is sufficient for the single-process deployment of the prototype, "
          "but a multi-instance production deployment needs a shared replay store, and the demo OTP secret is public by design. The "
          "approval binds to the action through the hash above and not through the secret alone, so a valid code for one payload is "
          "useless for another."),
    ("sequence", Sequence(TEXT_W, ["Director", "Gatekeeper / OTP", "Coordinator", "Lender (mock)"], [
        (0, 1, "request approval (pack id)"), (1, 0, "challenge: action_hash, expiry 120 s"), (0, 1, "TOTP code"),
        (1, 2, "verified, single-use, hash matches"), (2, 3, "release pack (recheck state, scope); anchor audit root"),
        (3, 2, "lender record: mock decision")]),
     "Release sequence. The one-time code is validated against the exact payload hash before the coordinator rechecks case state and "
     "lender scope. The audit-log root is anchored after the release (Section [[sec:anchor]]).", "fig:release"),
    ("h2", "Separation of duties", None),
    ("table", ["Actor", "May", "May not"], [
        ["Accountant (sme_accountant)", "Analyse; supply evidence; prepare or rework a pack; draft contracts; propose a correction; publish an audit anchor.", "Approve own release; act as lender."],
        ["Director (sme_director)", "Review or reject; confirm release by OTP; approve governed model changes and corrections; publish an audit anchor.", "Prepare; bypass the data gate, OTP or money prohibition."],
        ["Lender reviewer (bank_reviewer)", "Read released cases; request and open evidence; verify hashes, register and anchors; record a mock decision; run the duplicate drill.", "Access unreleased cases; fund an invoice another consortium lender holds; disburse funds."],
        ["Finance Autopilot", "Analyse, verify, price, stress-test, draft, request approval.", "Submit a pack; approve; lend; transfer."],
    ], [1.25, 2.6, 1.75], "tab:sod", "Role capabilities, taken from the permission matrix in security/auth.py."),
]
