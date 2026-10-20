"""Build the 2-page Security Self-Assessment PDF from the controls that exist in this repository.

    python scripts/security_self_assessment.py [--tests N] [--out reports/CashBridge_Security_Self_Assessment.pdf]

Every control named here points to a file; every count is read from an archived report when available.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = Path("/usr/share/fonts/truetype/crosextra")
NAVY, TEAL, GOLD, RED, INK, MUTED, RULE, ZEBRA, NOTE = (colors.HexColor(x) for x in
    ("#14324f", "#1c6f7f", "#d9a441", "#b3261e", "#1d2125", "#6b7177", "#d8dce0", "#f5f7f9", "#e8f3f4"))


def fonts() -> tuple:
    try:
        for name, file in (("Body", "Carlito-Regular.ttf"), ("Body-Bold", "Carlito-Bold.ttf"), ("Body-Italic", "Carlito-Italic.ttf")):
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-Bold")
        return "Body", "Body-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


BODY, BOLD = fonts()
S = {
    "p": ParagraphStyle("p", fontName=BODY, fontSize=8.6, leading=11.2, textColor=INK, alignment=TA_LEFT),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=7.9, leading=9.9, textColor=INK),
    "cellm": ParagraphStyle("cellm", fontName=BODY, fontSize=7.6, leading=9.5, textColor=MUTED),
    "cellb": ParagraphStyle("cellb", fontName=BOLD, fontSize=7.9, leading=9.9, textColor=INK),
    "head": ParagraphStyle("head", fontName=BOLD, fontSize=7.4, leading=9, textColor=colors.white),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=9.6, leading=12, textColor=TEAL, spaceBefore=7, spaceAfter=3),
    "bullet": ParagraphStyle("bullet", fontName=BODY, fontSize=8.1, leading=10.5, textColor=INK, leftIndent=9, bulletIndent=0, spaceAfter=2),
}
code = lambda s: f'<font color="#1c6f7f">{s}</font>'  # noqa: E731


def table(header, rows, widths, sev_col=None):
    data = [[Paragraph(h, S["head"]) for h in header]]
    for r in rows:
        cells = []
        for i, v in enumerate(r):
            style = "cellb" if i == (1 if sev_col is not None else 0) else ("cellm" if i == len(r) - 1 and sev_col is not None else "cell")
            if sev_col is not None and i == sev_col:
                hi = "HIGH" in v
                v = f'<font color="{"#b3261e" if hi else "#6b7177"}">{v}</font>'
            cells.append(Paragraph(v, S[style]))
        data.append(cells)
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6),
          ("LEFTPADDING", (0, 0), (-1, -1), 4.5), ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
          ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE)]
    st += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(data), 2)]
    t.setStyle(TableStyle(st))
    return t


def h2(text):
    return KeepTogether([Paragraph(text, S["h2"]), Table([[""]], colWidths=[180 * mm], rowHeights=[0.1],
                                                       style=[("LINEABOVE", (0, 0), (-1, -1), 0.5, RULE)])])


def bullets(items):
    return [Paragraph(f"<b>{b}:</b> {t}", S["bullet"], bulletText="•") for b, t in items]


def note(text):
    t = Table([[Paragraph(text, S["p"])]], colWidths=[180 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NOTE), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("ROUNDEDCORNERS", [4, 4, 4, 4])]))
    return t


def band(title, subtitle, page):
    def draw(c, doc):
        w, h = A4
        c.saveState()
        c.setFillColor(NAVY); c.rect(0, h - 28 * mm, w, 28 * mm, stroke=0, fill=1)
        c.setFillColor(GOLD); c.rect(15 * mm, h - 28 * mm, 18 * mm, 1.2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont(BOLD, 17); c.drawString(15 * mm, h - 13 * mm, title)
        c.setFont(BODY, 8.5); c.setFillColor(colors.HexColor("#d5dde6")); c.drawString(15 * mm, h - 20 * mm, subtitle)
        c.setStrokeColor(RULE); c.setLineWidth(0.5); c.line(15 * mm, 13 * mm, w - 15 * mm, 13 * mm)
        c.setFont(BODY, 7); c.setFillColor(MUTED)
        c.drawString(15 * mm, 9 * mm, "CASHBRIDGE  /  FINTECHATHON SHENZHEN 2026  /  TOPIC E")
        c.drawRightString(w - 15 * mm, 9 * mm, f"SECURITY SELF-ASSESSMENT  ·  PAGE {doc.page}")
        c.restoreState()
    return draw


def build(out: Path, tests: str) -> None:
    sc_path = ROOT / "data/execution_evidence/trust_scorecard.json"
    sc = json.loads(sc_path.read_text()) if sc_path.exists() else {}
    sec = sc.get("summary", {}).get("security", {"passed": 28, "total": 28})
    agent = sc.get("summary", {}).get("agent", {"passed": 5, "total": 5})
    doc = BaseDocTemplate(str(out), pagesize=A4, title="CashBridge Security Self-Assessment (v9.1)", author="CashBridge team",
                          subject="Permission tiers, controls and residual risks of the CashBridge prototype")
    frame = Frame(15 * mm, 16 * mm, 180 * mm, A4[1] - 50 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate("p1", [frame], onPage=band("Security Self-Assessment", "Implemented permission tiers, controls, residual risks  |  20 October 2026  |  v9.1", 1)),
        PageTemplate("p2", [frame], onPage=band("Residual Risk Register", "Honest known risks, controls and remaining gaps  |  v9.1", 2)),
    ])
    s = []
    s.append(Paragraph("<b>Assessment boundary:</b> CashBridge v9.1 is a functional financial-agent prototype using synthetic SME cases and mock "
                       "lender/payment paths. Statements below reference the submitted code and archived checks; they are <b>not</b> a production "
                       "certification or an independent penetration test.", S["p"]))
    s.append(h2("1. PERMISSION TIERS: WHAT THE AGENT MAY DO"))
    s.append(table(["TIER", "ACTION CLASS", "AGENT / HUMAN BOUNDARY"], [
        ["L0 Read", "View permitted balances, documents, inbox and payment history.", "Session, tenant and role checked; no blanket access."],
        ["L1 Analyse", "Reconcile, 13-week forecast, buyer scoring, financing comparison, simulation; unsigned contract drafts from a fixed clause library.",
         "Named tool must be on the agent allowlist; every decision logged. Drafts are never signed."],
        ["L2 Internal", "Write/lock internal evidence; propose learning/model updates.", "Deterministic matches may proceed; ambiguous writes and decisions require a named human."],
        ["L3 External", "Release a financing pack / send simulated financing communication.",
         "Coordinator only; Director confirms the exact action and payload with a time-limited, single-use, action-bound OTP. No autonomous submission."],
        ["L4 Funds", "Transfer funds, change payee, execute payment.", "<b>Always forbidden.</b> No money-movement tool on any agent allowlist."],
    ], [22 * mm, 82 * mm, 76 * mm]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("<b>Outside the agent tiers (internal records, L2):</b> publishing the audit-log Merkle root is a digest of records the SME "
                       "already holds. It runs automatically after release and after the lender's decision (best effort: a failure never blocks the "
                       "human action but is written to the audit log, shown on the Trust page and fails the lender's anchor check), and an "
                       "Accountant or Director may publish one manually <b>without</b> the pack-release OTP; the publisher is recorded. Registering "
                       "a funded invoice on the consortium register is performed inside the lender's credit decision. Neither can release a pack, "
                       "change a payee or move money.", S["p"]))
    s.append(h2("2. SEPARATION OF DUTIES AND RELEASE PATH"))
    s.append(table(["ACTOR", "CAN PERFORM", "CANNOT PERFORM"], [
        ["Accountant", "Analyse; provide evidence; prepare/rework funding pack; draft contracts for counsel.", "Approve own release or act as lender."],
        ["Director", "Review/reject; OTP-confirm pack release; approve governed model changes.", "Bypass source gate, OTP or money prohibition."],
        ["Lender human", "Read released case; request/open evidence; verify hashes, on-chain register and anchors; record mock credit decision.",
         "Access unreleased cases; fund an invoice another consortium lender holds; disburse real funds."],
        ["Finance Autopilot", "Analyse → verify → price → stress-test → draft → request approval.", "Submit pack itself; approve, lend or transfer."],
    ], [28 * mm, 82 * mm, 70 * mm]))
    s.append(h2("3. SECURITY ENFORCEMENT POINTS AND INSPECTION PATHS"))
    s += bullets([
        ("Tool gate", f"registered tier, per-agent allowlist, confidence/human checks and logged denial ({code('config/tool_allowlist.py')}; {code('security/permission_gatekeeper.py')})."),
        ("Identity + release", f"signed role/tenant sessions; Director OTP tied to the approval payload; released-case lender scope ({code('security/auth.py')}; {code('security/otp_verifier.py')}; {code('agents/coordinator.py')})."),
        ("Document custody", f"type by bytes, 10 MB, <b>PDF active-content screen</b> (JavaScript, launch, embedded files, XFA, auto-actions; hex-escaped names and compressed object streams inspected) before parsing or storage; SHA-256; AES-256-GCM bound to tenant/case/file; audited view; lender must open the current file to accept ({code('security/pdf_screen.py')}; {code('workspace/evidence_vault.py')})."),
        ("Financial integrity", f"3-way invoice matching, local duplicate registry, source attestations, fail-closed funding gate, click-to-source provenance ({code('core/financing_gate.py')}; {code('core/provenance.py')})."),
        ("Consortium ledger (optional, in-process EVM)", f"Vyper contracts executed by py-evm/eth-tester inside the server; other lenders are simulated accounts. Invoice register keyed by HMAC commitments (no invoice data on chain) refuses a second lender at funding. Modes ({code('CASHBRIDGE_CHAIN')}): <i>evm</i> (default in DEMO) fails closed, i.e. any register error refuses funding; <i>required</i> (default in PRODUCTION) also refuses funding when the module is absent; <i>off</i> lets funding proceed and records 'register not checked' in the audit log and lender history ({code('chain/ledger.py')}; {code('ui/backend_real.py')})."),
        ("Conditional control", f"the data reliability gate is always on in PRODUCTION; in DEMO it is off unless {code('CASHBRIDGE_REQUIRE_DATA_GATE=1')} ({code('core/financing_gate.py')})."),
    ])
    s.append(Spacer(1, 5))
    s.append(note("<b>Design rule (as implemented and tested, not a proof):</b> document and message text is parsed as data only; no code path lets it "
                  "grant a role, register a tool, skip an evidence check, confirm an L3 action or reach an L4 tool. The adversarial cases in "
                  "section 5 exercise these paths. Refusals are written to the hash-chained audit log; its Merkle root is anchored on the "
                  "in-process EVM, which detects a consistent rewrite of the whole log but is not yet an independent, externally operated anchor."))
    s.append(NextPageTemplate("p2"))
    s.append(PageBreak())
    s.append(Paragraph("<b>Status:</b> mitigations listed are implemented to the extent described in CashBridge v9.1; residual risk is not zero. "
                       "Severity is an engineering prioritisation for this prototype, not a formal quantified risk rating. "
                       "<b>Changed since v9:</b> 04, 05, 06, 11 (controls and residual exposure restated after an internal review), 12 (new).", S["p"]))
    s.append(h2("4. KNOWN RISKS, MITIGATION AND RESIDUAL EXPOSURE"))
    s.append(table(["ID / PRIORITY", "THREAT", "IMPLEMENTED MITIGATION", "REMAINING EXPOSURE"], [
        ["01 / HIGH", "Prompt injection / tool hijacking", "Fixed workflow state machine; untrusted strings treated as data; off-policy proposal refused and logged.", "Local parsing errors still possible."],
        ["02 / HIGH", "Wrong financial answer / hallucination", "Numerical values from local engines; typed inputs; evidence status, audit trail and human release.", "Assumptions and forecasts may be wrong."],
        ["03 / HIGH", "Cross-tenant or role data leak", "Signed sessions, server-side RBAC, lender release scope and denial tests.", "No external IdP/OIDC or enterprise IAM."],
        ["04 / HIGH", "Malicious document / unsafe OCR", "Byte-level type check, 10 MB cap; <b>active-content screen</b> refuses JS, launch, embedded files, XFA, auto-actions (incl. hex-escaped and object-stream names); bomb cap; encrypted PDFs refused; encrypted vault; sandboxed viewer.",
         "Not an antivirus or content disarm; a malformed file aimed at a viewer bug is not detected."],
        ["05 / HIGH", "Tampered / stale / duplicate invoices", "SHA-256 and provenance links; 3-way match; data gate (always on in PRODUCTION); local registry; <b>consortium register</b> on an in-process EVM checked at verification; funding refused (409) when another lender holds the invoice or the register cannot be checked.",
         "Other lenders simulated in one process; with CASHBRIDGE_CHAIN=off funding proceeds unchecked (recorded); key custody (HSM) and consortium governance not built."],
        ["06 / HIGH", "OTP replay / unauthorised release", "Action- and payload-bound, 120 s, one-use TOTP; 5-attempt cap; Director-only endpoint; denial logs.", "Demo OTP secret is public; replay memory is per server process, not a shared store; not institutional MFA."],
        ["07 / MED", "Partner API replay / duplicate effect", "Sandbox adapter validates quotes/webhooks; idempotent outbox and replay checks.", "No real lender connection certified."],
        ["08 / MED", "Confidentiality at rest and in logs", "AES-256-GCM evidence; privacy-filtered/no-store interfaces; export/purge tooling; only commitments and roots on chain.", "Local env secret, no KMS/HSM or third-party audit."],
        ["09 / MED", "Model shift, bias, false confidence", "Calibrated intervals, domain warnings, published backtests, public distress benchmark, risk caps and human review.", "Synthetic SME cases; no real SME credit-default validation."],
        ["10 / MED", "Revoked data still held by recipient", "Revoke released-case access and remove internal evidence; record recipient notice.", "Files downloaded earlier need recipient deletion."],
        ["11 / MED", "Infrastructure & audit compromise", "Fail-closed production mode, local TLS/CSP checks, hash-chained log; <b>Merkle root anchored</b> on the in-process EVM (a consistent whole-log rewrite is detected in tests; anchors cannot shrink); anchor failures recorded and shown.",
         "Anchoring is best effort and the chain is controlled by the same operator, so not externally immutable; testnet script not run; no independent pentest."],
        ["12 / MED", "Generated contract mistaken for advice or signed", "Fixed clause library (no LLM); DRAFT watermark, NOT SIGNED header, [●] gaps and listed defaults, review checklist; payee call-back clause; no e-signature.",
         "No jurisdiction-specific mandatory clauses; counsel must approve."],
        ["13 / MED", "Consortium key exposure", "Commitments are HMAC-SHA256 under a consortium key held off chain; production refuses to start the register without CASHBRIDGE_CONSORTIUM_KEY; demo key in an owner-only runtime file.",
         "Any key holder can test guessed invoices against the register; no HSM, rotation or membership governance."],
    ], [20 * mm, 36 * mm, 76 * mm, 48 * mm], sev_col=0))
    s.append(h2("5. VERIFICATION, SCOPE AND HANDOVER"))
    s += bullets([
        ("Archived proof", f"{sec['passed']}/{sec['total']} adversarial cases (incl. FIN-04 cross-lender duplicate refused, EVID-04 whole-log rewrite caught by the anchor, "
                           f"DOC-01 hidden-JavaScript PDF refused) and {agent['passed']}/{agent['total']} agent-governance cases ({code('data/execution_evidence/trust_scorecard.md')}); "
                           f"30/30 local production-mode checks ({code('reports/deploy_verification.md')}); full regression: {tests} ({code('reports/full_pytest_v9_1.txt')}, with the environment it ran in). These are team-run reports, not third-party certification."),
        ("On-chain evidence", "transaction hashes, blocks and gas come from the <b>in-process EVM</b> (py-evm via eth-tester); they are real EVM executions but "
                              "<b>not transactions on a public network</b>. The testnet deployment script exists (dry-run tested) and has not been run."),
        ("Important exclusions", "no live money movement, no production bank integration, no certified KYC/AML process, no public-chain deployment, "
                                 "no external penetration test or regulator approval."),
        ("Safe evaluation", "synthetic case credentials only, Director consent for all outward actions, mock credit decisions, verified and anchored audit log, "
                            "encrypted evidence viewer."),
    ])
    doc.build(s)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", default="the full regression of")
    ap.add_argument("--out", default=str(ROOT / "reports" / "CashBridge_Security_Self_Assessment.pdf"))
    a = ap.parse_args()
    build(Path(a.out), a.tests)
    print(a.out)
