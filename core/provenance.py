"""Field-level provenance for the locked metrics of a funding pack (v9).

For each number a lender sees in the pack this returns:

* the formula and the same formula with the actual inputs substituted;
* the value recomputed now from those inputs, and whether it reproduces the locked value (if an input
  changed after the pack was locked, the pack keeps its value and this says so: it never re-locks);
* the sources: input file + JSON path + SHA-256 of the file as it is now, and for values read from a
  scanned document the document id, page, line, character span [start, end), the source line, the
  extraction confidence, the review status and the SHA-256 of the scan text;
* the history: the locked value, and any correction proposed or decided afterwards.

Coordinates: the scans are text layers, so a field is located by character offsets, never by a
bounding box. ``bbox`` is always None with a note; nothing here invents OCR coordinates.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.forecasting_engine import compute_ccc
from core.funding_evaluator import calc_apr
from core.metrics import monthly_billing_volatility_pct, negative_cash_weeks, top_buyer_share_pct

NO_BBOX = "Text-layer scan: located by character offsets. No OCR coordinates exist, so no bounding box is shown."
SYNTHETIC = "SYNTHETIC demo record"


def _sha_file(path: Path) -> Optional[str]:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _num(x: Any) -> Optional[float]:
    return None if x is None else float(x)


def _record(coord, file: str, path: str, value: Any, note: str = SYNTHETIC) -> Dict[str, Any]:
    f = Path(coord.inputs_dir) / file
    return {"kind": "record", "file": file, "json_path": path, "file_sha256": _sha_file(f), "value": None if value is None else str(value),
            "review_status": note, "bbox": None}


def _index(coord, file: str, key: str, field: str, value: str) -> Optional[int]:
    try:
        rows = json.loads((Path(coord.inputs_dir) / file).read_text(encoding="utf-8"))[key]
    except (OSError, KeyError, ValueError):
        return None
    return next((i for i, r in enumerate(rows) if str(r.get(field)) == value), None)


def _scan_field(coord, invoice_no: str, doc_type: str, field: str) -> Optional[Dict[str, Any]]:
    scan = next((s for s in coord.scans if s["invoice_no"] == invoice_no and s["doc_type"] == doc_type), None)
    if scan is None or field not in scan.get("fields", {}):
        return None
    f = scan["fields"][field]
    text = next((d["text"] for d in coord.scanned if d["doc_id"] == scan["doc_id"]), "")
    excerpt = text[f["char_start"]:f["char_end"]] if f.get("char_start") is not None else None
    low = f["confidence"] < coord.docs.threshold
    status = ("needs human review (low confidence)" if low else
              "auto-read; matches the system record" if scan.get("matches_record") else
              "auto-read; DIFFERS from the system record" if scan.get("matches_record") is False else "auto-read")
    return {"kind": "scan", "doc_id": scan["doc_id"], "doc_type": doc_type, "field": field, "value": f["value"],
            "page": f["page"], "line": f["line"], "char_start": f["char_start"], "char_end": f["char_end"],
            "source_line": f["source_line"], "excerpt": excerpt,
            "span_verified": bool(excerpt) and excerpt in (f["source_line"] or "") and hashlib.sha256(text.encode("utf-8")).hexdigest() == scan.get("text_sha256"),
            "confidence": f["confidence"], "review_status": status, "text_sha256": scan.get("text_sha256"), "bbox": None, "bbox_note": NO_BBOX}


def _forecast_sources(coord) -> List[Dict[str, Any]]:
    return [_record(coord, "company_profile.json", "$.opening_cash_usd", coord.profile.get("opening_cash_usd")),
            _record(coord, "company_profile.json", "$.weekly_fixed_costs_usd", coord.profile.get("weekly_fixed_costs_usd")),
            _record(coord, "trade_documents.json", "$.invoices (open receivables)", f"{len(coord.forecast_inputs.receivables)} open invoices"),
            _record(coord, "payment_history.json", "$.records (on-time model)", f"{len(coord.billings)} paid invoices")]


def _round1(x: Decimal) -> Decimal:
    return Decimal(x).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def lineage(coord) -> Dict[str, Any]:
    pack = coord.pack
    if not pack.get("pack_id"):
        raise LookupError("No funding pack has been prepared")
    option = coord.selected_option()
    inv = coord.nominee
    locked = {m["key"]: m for m in pack["locked_metrics"]}
    out: List[Dict[str, Any]] = []

    def add(key: str, formula: str, substituted: str, recomputed: Any, inputs: List[Dict[str, Any]], sources: List[Dict[str, Any]]) -> None:
        m = locked.get(key)
        if m is None:
            return
        rv = _num(recomputed) if not isinstance(recomputed, int) or isinstance(recomputed, bool) else recomputed
        lv = m["value"]
        same = (rv == lv) if isinstance(lv, int) and not isinstance(lv, bool) else (rv is not None and lv is not None and abs(float(rv) - float(lv)) < 0.005)
        out.append({"key": key, "label": m["label"], "unit": m["unit"], "locked_value": lv, "formula": formula, "computation": substituted,
                    "recomputed_now": rv, "reproduces_locked_value": bool(same),
                    "note": None if same else "An input changed after the pack was locked. The pack keeps its locked value; prepare a new pack to use the new one.",
                    "inputs": inputs, "sources": [s for s in sources if s]})

    L = coord.ledger
    add("revenue_12m_usd", "Ledger revenue for the period", f"revenue = {L.revenue_usd} (period {L.period_days} days)", L.revenue_usd,
        [{"name": "revenue_usd", "value": str(L.revenue_usd)}], [_record(coord, "company_profile.json", "$.ledger.revenue_usd", L.revenue_usd)])

    months: Dict[str, Decimal] = defaultdict(Decimal)
    for issued, usd in coord.billings:
        months[f"{issued.year}-{issued.month:02d}"] += usd
    add("billing_volatility_pct", "Coefficient of variation of monthly billed USD = population stdev / mean x 100 (months with billing only)",
        f"{len(months)} months, mean {sum(months.values()) / max(1, len(months)):,.2f} USD", monthly_billing_volatility_pct(coord.billings),
        [{"name": k, "value": f"{v:,.2f}"} for k, v in sorted(months.items())],
        [_record(coord, "payment_history.json", "$.records[*].issue_date, amount, currency", f"{len(coord.billings)} invoices")])

    ccc = compute_ccc(L)
    add("ccc_days", "CCC = DIO + DSO - DPO; DIO = inventory / COGS x days, DSO = receivables / revenue x days, DPO = payables / COGS x days",
        f"{ccc.dio:g} + {ccc.dso:g} - {ccc.dpo:g} = {ccc.ccc:g}", ccc.ccc,
        [{"name": n, "value": str(getattr(L, n))} for n in ("avg_inventory_usd", "avg_receivables_usd", "avg_payables_usd", "cogs_usd", "revenue_usd", "period_days")],
        [_record(coord, "company_profile.json", f"$.ledger.{n}", getattr(L, n)) for n in ("avg_inventory_usd", "avg_receivables_usd", "avg_payables_usd", "cogs_usd", "revenue_usd")])

    rec = coord.forecast_inputs.receivables
    by_buyer: Dict[str, Decimal] = defaultdict(Decimal)
    for r in rec:
        by_buyer[r.buyer_id] += r.amount.to_usd()
    total = sum(by_buyer.values(), Decimal(0))
    top = max(by_buyer.items(), key=lambda kv: kv[1]) if by_buyer else ("-", Decimal(0))
    add("top_buyer_share_pct", "Largest buyer's open receivables / all open receivables x 100",
        f"{top[0]}: {top[1]:,.2f} / {total:,.2f} x 100", top_buyer_share_pct(rec),
        [{"name": b, "value": f"{v:,.2f}"} for b, v in sorted(by_buyer.items(), key=lambda kv: -kv[1])],
        [_record(coord, "trade_documents.json", "$.invoices[*] (open, not reconciled)", f"{len(rec)} open invoices")])

    weeks = coord.forecast.weeks
    neg = [w for w in weeks if w.closing < 0]
    wk_inputs = [{"name": f"week {w.week} ({w.start_date})", "value": f"open {w.opening:,.2f} + in {w.inflows:,.2f} - out {w.outflows:,.2f} = {w.closing:,.2f}"}
                 for w in weeks]
    fc_note = f"forecast run {coord.forecast_run_id}"
    add("negative_cash_weeks", "Number of forecast weeks whose closing cash is below zero",
        f"weeks {', '.join(str(w.week) for w in neg) or 'none'} -> {len(neg)} ({fc_note})", negative_cash_weeks(weeks), wk_inputs, _forecast_sources(coord))
    first = coord.forecast.first_shortfall_week
    add("first_shortfall_week", "First week with closing cash below zero; closing = opening + inflows - outflows",
        f"week {first} ({fc_note})", first, wk_inputs[:first] if first else wk_inputs, _forecast_sources(coord))
    if first:
        w = weeks[first - 1]
        add("shortfall_usd", "Shortfall = - closing cash of the first shortfall week",
            f"-({w.opening:,.2f} + {w.inflows:,.2f} - {w.outflows:,.2f}) = {-w.closing:,.2f}", -w.closing, wk_inputs[first - 1:first], _forecast_sources(coord))

    i_idx = _index(coord, "trade_documents.json", "invoices", "invoice_no", inv.invoice_no)
    rec_path = f"$.invoices[{i_idx}]" if i_idx is not None else "$.invoices[?invoice_no]"
    from config.settings import FX_NOTE, FX_VND_PER_UNIT, USD_VND
    fx = "" if inv.currency.value == "USD" else (
        f" x {FX_VND_PER_UNIT[inv.currency.value]} VND per {inv.currency.value} / {USD_VND} VND per USD ({FX_NOTE})")
    add("invoice_amount_usd", "Invoice face value in USD (record; the scanned invoice and PO must agree)",
        f"{inv.amount.display()}{fx} = USD {inv.amount.to_usd():,.2f}", inv.amount.to_usd(),
        [{"name": "amount", "value": inv.amount.display()}],
        [_record(coord, "trade_documents.json", f"{rec_path}.amount", inv.amount.display()),
         _scan_field(coord, inv.invoice_no, "invoice", "amount"), _scan_field(coord, inv.invoice_no, "purchase_order", "amount")])

    if option is not None:
        a = option.assumptions or {}
        cb = option.cost_breakdown or {}
        cat = "$.factoring" if option.type == "factoring" else "$.bridge_loan"
        if option.type == "factoring":
            adv = (inv.amount.to_usd() * Decimal(str(a.get("advance_pct", 0))) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            add("advance_usd", "Advance = invoice value x advance rate", f"{inv.amount.to_usd():,.2f} x {a.get('advance_pct')}% = {adv:,.2f}", adv,
                [{"name": "invoice_usd", "value": f"{inv.amount.to_usd():,.2f}"}, {"name": "advance_pct", "value": str(a.get("advance_pct"))}],
                [_record(coord, "lender_catalog.json", f"{cat}.advance_pct", a.get("advance_pct"), "MOCK lender terms (not a lender offer)"),
                 _record(coord, "trade_documents.json", f"{rec_path}.amount", inv.amount.display())])
            net = option.amount_usd
        else:
            add("advance_usd", "Loan amount from the catalogue", f"{option.amount_usd:,.2f}", option.amount_usd,
                [{"name": "amount_usd", "value": str(option.amount_usd)}],
                [_record(coord, "lender_catalog.json", f"{cat}.amount_usd", option.amount_usd, "MOCK lender terms (not a lender offer)")])
            net = option.amount_usd - Decimal(str(cb.get("fee_usd", 0)))
        days = int(a.get("days") or (inv.due_date - coord.as_of).days)
        total_cost = Decimal(str(cb.get("total_usd", 0)))
        add("apr_pct", "Annualised cost = total cost / net funds received x 365 / days (simple Actual/365; an internal convention, not a legal APR)",
            f"{total_cost:,.2f} / {net:,.2f} x 365 / {days} x 100", calc_apr(total_cost, net, days),
            [{"name": k, "value": str(v)} for k, v in {**cb, "net_funds_usd": f"{net:,.2f}", "days": days}.items()],
            [_record(coord, "lender_catalog.json", cat, ", ".join(f"{k}={v}" for k, v in a.items()), "MOCK lender terms (not a lender offer)")])

    add("days_outstanding", "Due date - as-of date", f"{inv.due_date} - {coord.as_of} = {(inv.due_date - coord.as_of).days}",
        (inv.due_date - coord.as_of).days, [{"name": "due_date", "value": str(inv.due_date)}, {"name": "as_of", "value": str(coord.as_of)}],
        [_record(coord, "trade_documents.json", f"{rec_path}.due_date", inv.due_date), _scan_field(coord, inv.invoice_no, "invoice", "due_date"),
         _record(coord, "company_profile.json", "$.as_of", coord.as_of)])

    return {"pack_id": pack["pack_id"], "bundle_sha256": pack.get("bundle_sha256"), "document_hashes": pack.get("document_hashes"),
            "metrics": out, "all_reproduce": all(m["reproduces_locked_value"] for m in out),
            "coordinates": NO_BBOX, "synthetic": True,
            "corrections_policy": "Corrections are proposed by a preparer and decided by a different person. The original value is kept; "
                                  "a locked pack is never changed. An approved correction applies to the next pack."}
