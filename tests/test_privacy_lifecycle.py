"""Audit 3: consent withdrawal, export, retention purge, and no shared static credential in production."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from api.main import create_app
from core import privacy_lifecycle as pl
from scripts.run_demo_story import StoryClock
from security.audit_log import verify_chain
from tests.authed import RoleClient
from ui.backend_real import RealBackend


@pytest.fixture
def released(tmp_path, monkeypatch):
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    monkeypatch.delenv("CASHBRIDGE_REQUIRE_DATA_GATE", raising=False)
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-ui"))
    client.post("/api/autopilot/run", json={"execute": True})
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    pack = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()["snapshot"]["pack"]["pack_id"]
    return client, backend, pack, tmp_path


def test_director_can_withdraw_consent_and_the_lender_loses_access(released):
    client, backend, pack, _ = released
    bank = client.header("bank.lihua")
    client.post(f"/api/workspace/cases/{pack}/messages", json={"kind": "question", "message": "Need the B/L"}, headers=bank)
    # Only the consent giver (Director) may withdraw; a reason is required.
    assert client.post("/api/withdraw_release", json={"reason": "Buyer objects"}, headers=client.header("sme.lan")).status_code == 403
    assert client.post("/api/withdraw_release", json={"reason": ""}, headers=client.header("sme.minh")).status_code == 422
    r = client.post("/api/withdraw_release", json={"reason": "Buyer objects to assignment"}, headers=client.header("sme.minh"))
    assert r.status_code == 200 and r.json()["snapshot"]["pack"]["status"] == "WITHDRAWN_BY_SME"
    assert client.get("/api/bank/inbox", headers=bank).json()["items"] == []
    for path in (f"/api/bank/cases/{pack}", f"/api/bank/cases/{pack}/pdf", f"/api/workspace/cases/{pack}/messages",
                 f"/api/workspace/cases/{pack}/evidence"):
        assert client.get(path, headers=bank).status_code == 404, path
    assert client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING"}, headers=bank).status_code == 404
    assert any("withdrew" in n["text"] for n in client.get("/api/workspace/notifications", headers=bank).json()["items"])
    assert "Consent to share withdrawn by sme.minh" in backend.coord.audit_path.read_text()
    assert verify_chain(backend.coord.audit_path)[0]
    # The preparer can rework; the same invoice is not silently re-pledged (registry is append-only).
    assert client.post("/api/reopen_pack").status_code == 200
    assert backend.coord.state.value == "INVOICE_VERIFIED"


def test_withdrawal_is_refused_once_the_lender_has_decided(released):
    client, _, pack, _ = released
    bank = client.header("bank.lihua")
    client.post(f"/api/bank/cases/{pack}/verify", headers=bank)
    assert client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING"}, headers=bank).status_code == 200
    assert client.post("/api/withdraw_release", json={"reason": "Too late"}, headers=client.header("sme.minh")).status_code == 409


def test_export_contains_the_tenants_records_and_only_hashes_of_payloads(released):
    client, backend, pack, tmp = released
    client.post("/api/workspace/requests", json={"field": "marketing_usd", "proposed_value": "500", "reason": "Trade fair booth"})
    client.post(f"/api/workspace/cases/{pack}/messages", json={"kind": "question", "message": "Please send the packing list"},
                headers=client.header("bank.lihua"))
    out = pl.export_tenant("TEN-BDT-001", tmp / "runtime", tmp / "ws.db")
    assert out["workspace"]["requests"] and out["workspace"]["messages"] and out["case_files"]
    assert all("input_sha256" in line and "input_payload" not in line for line in out["audit_log"])
    assert pl.export_tenant("TEN-OTHER", tmp / "runtime", tmp / "ws.db")["workspace"]["requests"] == []
    inv = {i["store"]: i for i in pl.inventory(tmp / "runtime", tmp / "ws.db", tmp / "none.db")}
    assert inv["workspace.requests"]["records"] == 1 and inv["audit log"]["records"] > 10


def test_purge_redacts_old_pii_payloads_and_keeps_accounting_evidence(tmp_path):
    from automation.engine import AutomationStore
    db = tmp_path / "jobs.db"
    store = AutomationStore(db)
    ticket = store.enqueue("support_triage", {"message": "Customer Jane Doe, phone 0901 234 567, was double charged"}, "pii-ticket-001")
    recon = store.enqueue("accounting_reconcile", {"ledger": [{"reference": "A", "amount": "1"}], "bank": [{"reference": "A", "amount": "1"}]}, "recon-0000001")
    store.run_pending()
    store.review_audit(recon["id"], "auditor", "accepted")
    later = datetime.now(timezone.utc) + timedelta(days=200)
    dry = pl.purge(tmp_path, tmp_path / "ws.db", db, 90, now=later, dry_run=True)
    assert dry["job_payloads_redacted"] == 1 and "Jane" in db.read_bytes().decode(errors="ignore")
    pl.purge(tmp_path, tmp_path / "ws.db", db, 90, now=later)
    with store._connect() as con:
        payloads = {r["id"]: r["payload"] for r in con.execute("SELECT id,payload FROM jobs")}
    assert json.loads(payloads[ticket["id"]])["redacted"] is True and "Jane" not in payloads[ticket["id"]]
    assert "ledger" in payloads[recon["id"]]  # accounting evidence kept
    assert store.get_audit_seal(recon["id"])["verified"] is True
    assert pl.purge(tmp_path, tmp_path / "ws.db", db, 90, now=later)["job_payloads_redacted"] == 0  # idempotent
    with pytest.raises(ValueError):
        pl.purge(tmp_path, tmp_path / "ws.db", db, 0)


def test_purge_deletes_old_notifications_only(tmp_path):
    from workspace.store import EvidenceDesk
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    desk = EvidenceDesk(tmp_path / "ws.db", clock=lambda: now[0])
    desk.open("T", "P", "bank", "Statement", "October bank statement")
    now[0] = datetime(2026, 10, 1, tzinfo=timezone.utc)
    desk.open("T", "P", "bank", "Packing list", "for INV-1030")
    r = pl.purge(tmp_path, tmp_path / "ws.db", tmp_path / "none.db", 90, now=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert r["notifications_deleted"] == 1
    assert len(desk.notifications("T", "sme")) == 1 and len(desk.list("T", "P")["items"]) == 2  # case records kept


def test_static_bank_token_is_refused_in_production(tmp_path, monkeypatch):
    from config import runtime_mode
    from fastapi.testclient import TestClient
    from security import auth
    token = "static-demo-token-" + "x" * 20
    assert any("BANK_REVIEW_TOKEN" in p for p in runtime_mode.production_problems(
        {"CASHBRIDGE_ENV": "production", "CASHBRIDGE_BANK_REVIEW_TOKEN": token}))
    users = [{"user_id": "bank.lihua", "name": "Li", "role": "bank_reviewer", "org": "x", "tenant_id": auth.LENDER_TENANT,
              "passcode_hash": auth.hash_passcode("long-passcode-x")}]
    for k, v in {"CASHBRIDGE_ENV": "production", "OTP_SECRET": "KRSXG5CTMVRXEZLUKN2XAZLSKNSWG4TFOQ", "CASHBRIDGE_SESSION_SECRET": "s" * 40, "CASHBRIDGE_VAULT_KEY": "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s=",
                 "CASHBRIDGE_USERS_JSON": json.dumps(users)}.items():
        monkeypatch.setenv(k, v)
    auth.reset_sessions_for_tests(auth.SessionManager())
    try:
        backend = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
        c = TestClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
        monkeypatch.setenv("CASHBRIDGE_BANK_REVIEW_TOKEN", token)  # set after start-up, as a misconfiguration would
        assert c.get("/api/bank/review", headers={"Authorization": "Bearer " + token}).status_code == 401
        session = c.post("/api/auth/login", json={"user_id": "bank.lihua", "passcode": "long-passcode-x"}).json()["token"]
        assert c.get("/api/bank/review", headers={"Authorization": "Bearer " + session}).status_code == 200
    finally:
        auth.reset_sessions_for_tests(None)
