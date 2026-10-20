"""Field-level provenance: every locked metric traces to a formula, inputs and a source span/hash; corrections never edit a locked pack."""

import hashlib

import pytest

from agents.document_agent import rule_extract

SCAN = "COMMERCIAL INVOICE\n--- page 1 ---\nInvoice No: INV-9\nCurrency: USD\n--- page 2 ---\nTotal Amount:   60,000.00  \nDue Date: 2026-12-18\n"


def test_rule_extraction_records_exact_character_spans():
    e = rule_extract(SCAN, "invoice")
    amount = e.fields["amount"]
    assert SCAN[amount.char_start:amount.char_end] == "60,000.00"
    assert amount.page == 2 and amount.line == 6 and amount.source_line.startswith("Total Amount:")
    due = e.fields["due_date"]
    assert SCAN[due.char_start:due.char_end] == "2026-12-18" and due.line == 7
    missing = e.fields["buyer_id"]
    assert missing.char_start is None and missing.line is None  # nothing located, nothing invented


def test_spans_survive_windows_line_endings():
    text = SCAN.replace("\n", "\r\n")
    f = rule_extract(text, "invoice").fields["amount"]
    assert text[f.char_start:f.char_end] == "60,000.00"


@pytest.fixture
def api(tmp_path, monkeypatch):
    from api.main import create_app
    from scripts.run_demo_story import StoryClock
    from tests.authed import RoleClient
    from ui.backend_real import RealBackend
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    monkeypatch.setenv("CASHBRIDGE_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.delenv("CASHBRIDGE_REQUIRE_DATA_GATE", raising=False)
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-ui"))
    client.post("/api/autopilot/run", json={"execute": True})
    return client, backend


def test_every_locked_metric_has_a_reproducible_lineage(api):
    client, backend = api
    r = client.get("/api/provenance", headers=client.header("sme.lan"))
    assert r.status_code == 200, r.text
    lin = r.json()
    locked = {m["key"] for m in backend.coord.pack["locked_metrics"]}
    assert {m["key"] for m in lin["metrics"]} == locked  # nothing locked is left untraced
    assert lin["all_reproduce"] is True
    for m in lin["metrics"]:
        assert m["formula"] and m["computation"] and m["sources"], m["key"]
        for s in m["sources"]:
            assert s["bbox"] is None  # never invented coordinates
            if s["kind"] == "record":
                assert len(s["file_sha256"]) == 64 and s["json_path"].startswith("$")


def test_scan_sources_point_at_the_exact_text_and_hash(api):
    client, backend = api
    lin = client.get("/api/provenance", headers=client.header("sme.lan")).json()
    face = next(m for m in lin["metrics"] if m["key"] == "invoice_amount_usd")
    scan = next(s for s in face["sources"] if s["kind"] == "scan" and s["doc_type"] == "invoice")
    text = next(d["text"] for d in backend.coord.scanned if d["doc_id"] == scan["doc_id"])
    assert text[scan["char_start"]:scan["char_end"]] == scan["excerpt"] == "60,000.00"
    assert scan["text_sha256"] == hashlib.sha256(text.encode()).hexdigest() and scan["span_verified"]
    assert scan["confidence"] >= 0.85 and "matches the system record" in scan["review_status"]
    assert "No OCR coordinates" in scan["bbox_note"]
    apr = next(m for m in lin["metrics"] if m["key"] == "apr_pct")
    assert any("MOCK" in s["review_status"] for s in apr["sources"])  # mock terms are never presented as a lender offer


def test_lender_sees_lineage_only_for_the_released_pack(api):
    from tests.test_adversarial import outsider
    client, backend = api
    pack = backend.coord.pack["pack_id"]
    assert client.get(f"/api/bank/cases/{pack}/provenance", headers=client.header("bank.lihua")).status_code == 404  # not released yet
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    client.post("/api/approve", json={"code": backend.coord.otp.current_code()})
    ok = client.get(f"/api/bank/cases/{pack}/provenance", headers=client.header("bank.lihua"))
    assert ok.status_code == 200 and ok.json()["pack_id"] == pack
    assert client.get("/api/bank/cases/PACK-OTHER/provenance", headers=client.header("bank.lihua")).status_code == 404
    assert client.get(f"/api/bank/cases/{pack}/provenance", headers=outsider("bank_reviewer", tenant="LENDER-OTHER")).status_code == 403
    assert client.get("/api/provenance", headers=client.header("bank.lihua")).status_code == 403


def test_corrections_are_four_eyes_and_never_change_the_locked_pack(api):
    client, backend = api
    before = [dict(m) for m in backend.coord.pack["locked_metrics"]]
    bundle = backend.coord.pack["bundle_sha256"]
    lin = client.get("/api/provenance", headers=client.header("sme.lan")).json()
    face = next(m for m in lin["metrics"] if m["key"] == "invoice_amount_usd")
    scan = next(s for s in face["sources"] if s["kind"] == "scan" and s["doc_type"] == "invoice")
    ref = f"{scan['doc_id']}:{scan['field']}"
    bad = client.post("/api/provenance/corrections", json={"metric_key": "invoice_amount_usd", "source_ref": "made-up:field",
                                                           "proposed_value": "1", "reason": "typo in the scan"}, headers=client.header("sme.lan"))
    assert bad.status_code == 422
    assert client.post("/api/provenance/corrections", json={"metric_key": "invoice_amount_usd", "source_ref": ref, "proposed_value": "59000.00",
                                                            "reason": "Credit note CN-12 reduces it"}, headers=client.header("bank.lihua")).status_code == 403
    p = client.post("/api/provenance/corrections", json={"metric_key": "invoice_amount_usd", "source_ref": ref, "proposed_value": "59000.00",
                                                         "reason": "Credit note CN-12 reduces it"}, headers=client.header("sme.lan"))
    assert p.status_code == 200 and p.json()["original_value"] == "60000.00" and p.json()["status"] == "pending"
    rid = p.json()["id"]
    assert client.post(f"/api/provenance/corrections/{rid}/decision", json={"approve": True, "note": "self"}, headers=client.header("sme.lan")).status_code == 403
    d = client.post(f"/api/provenance/corrections/{rid}/decision", json={"approve": True, "note": "Checked CN-12"}, headers=client.header("sme.minh"))
    assert d.status_code == 200 and d.json()["status"] == "approved" and d.json()["locked_pack_changed"] is False
    assert client.post(f"/api/provenance/corrections/{rid}/decision", json={"approve": False, "note": "again"}, headers=client.header("sme.minh")).status_code == 409
    assert backend.coord.pack["locked_metrics"] == before and backend.coord.pack["bundle_sha256"] == bundle
    after = client.get("/api/provenance", headers=client.header("sme.lan")).json()
    face = next(m for m in after["metrics"] if m["key"] == "invoice_amount_usd")
    assert face["locked_value"] == 60000.0 and face["corrections"][0]["status"] == "approved"
    assert "correction proposed" in backend.coord.audit_path.read_text()
