"""T15: lender <-> SME evidence loop on a released case.

open -> submit (content hash) -> reject with reason -> resubmit -> accept; revoke; expiry; stale review;
role and tenant boundaries; in-app notifications per role; every transition in the hash-chained audit log;
and APPROVE_FUNDING is blocked while any request is unresolved.
"""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from api.main import create_app
from scripts.run_demo_story import StoryClock
from security.audit_log import verify_chain
from tests.authed import RoleClient
from ui.backend_real import RealBackend
from workspace.store import EvidenceDesk

SHA_A = hashlib.sha256(b"bill of lading v1").hexdigest()
SHA_B = hashlib.sha256(b"bill of lading v2, signed").hexdigest()


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    monkeypatch.delenv("CASHBRIDGE_REQUIRE_DATA_GATE", raising=False)
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-ui"))
    assert client.post("/api/autopilot/run", json={"execute": True}).status_code == 200
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    pack_id = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()["snapshot"]["pack"]["pack_id"]
    return client, backend, pack_id


def test_full_loop_with_rejection_and_resubmission(api):
    client, backend, pack = api
    lan, minh, bank = client.header("sme.lan"), client.header("sme.minh"), client.header("bank.lihua")
    base = f"/api/workspace/cases/{pack}/evidence"
    opened = client.post(base, json={"item": "Signed bill of lading", "detail": "For INV-1030 shipment", "due_days": 5}, headers=bank)
    assert opened.status_code == 200, opened.text
    rid = opened.json()["id"]
    # Funding is blocked while the request is unresolved.
    assert client.post(f"/api/bank/cases/{pack}/verify", headers=bank).status_code == 200
    blocked = client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING"}, headers=bank)
    assert blocked.status_code == 409 and rid in blocked.json()["detail"]
    # SME sees the request in its notifications; the lender does not get its own notice back.
    assert any("Signed bill of lading" in n["text"] for n in client.get("/api/workspace/notifications", headers=lan).json()["items"])
    assert client.get("/api/workspace/notifications", headers=bank).json()["items"] == []
    # Submission needs a real content hash; only the preparer submits.
    assert client.post(f"{base}/{rid}/submit", json={"evidence_ref": "DOC-BL-1", "sha256": "abc"}, headers=lan).status_code == 422
    assert client.post(f"{base}/{rid}/submit", json={"evidence_ref": "DOC-BL-1", "sha256": SHA_A}, headers=minh).status_code == 403
    assert client.post(f"{base}/{rid}/submit", json={"evidence_ref": "DOC-BL-1", "sha256": SHA_A}, headers=bank).status_code == 403
    v1 = client.post(f"{base}/{rid}/submit", json={"evidence_ref": "DOC-BL-1", "sha256": SHA_A}, headers=lan).json()
    assert v1["status"] == "submitted" and v1["version"] == 1
    # The SME cannot review; the lender must give a reason.
    assert client.post(f"{base}/{rid}/review", json={"accept": True, "reason": "fine"}, headers=lan).status_code == 403
    assert client.post(f"{base}/{rid}/review", json={"accept": False, "reason": ""}, headers=bank).status_code == 422
    rej = client.post(f"{base}/{rid}/review", json={"accept": False, "reason": "Unsigned copy; need the carrier signature", "version": 1}, headers=bank)
    assert rej.json()["status"] == "rejected"
    assert any("rejected" in n["text"] for n in client.get("/api/workspace/notifications", headers=lan).json()["items"])
    # Resubmission; a review aimed at the old version is refused as stale.
    v2 = client.post(f"{base}/{rid}/submit", json={"evidence_ref": "DOC-BL-2", "sha256": SHA_B, "note": "carrier-signed"}, headers=lan).json()
    assert v2["version"] == 2 and v2["evidence_sha256"] == SHA_B
    stale = client.post(f"{base}/{rid}/review", json={"accept": True, "reason": "looks fine", "version": 1, "received_sha256": SHA_B}, headers=bank)
    assert stale.status_code == 409 and "Stale" in stale.json()["detail"]
    # Accepting needs proof the lender holds the same bytes: no hash, or the hash of a different file, is refused.
    nohash = client.post(f"{base}/{rid}/review", json={"accept": True, "reason": "Carrier signature verified", "version": 2}, headers=bank)
    assert nohash.status_code == 409 and "SHA-256 is required" in nohash.json()["detail"]
    wrong = client.post(f"{base}/{rid}/review", json={"accept": True, "reason": "Carrier signature verified", "version": 2,
                                                      "received_sha256": SHA_A}, headers=bank)
    assert wrong.status_code == 409 and "does not match" in wrong.json()["detail"]
    ok = client.post(f"{base}/{rid}/review", json={"accept": True, "reason": "Carrier signature verified", "version": 2,
                                                   "received_sha256": SHA_B.upper()}, headers=bank).json()
    assert ok["status"] == "accepted"
    assert [a["action"] for a in ok["timeline"]] == ["opened", "submitted", "rejected", "submitted", "accepted"]
    # Accepted is final.
    assert client.post(f"{base}/{rid}/submit", json={"evidence_ref": "DOC-BL-3", "sha256": SHA_A}, headers=lan).status_code == 409
    assert client.post(f"{base}/{rid}/revoke", json={"reason": "too late"}, headers=bank).status_code == 409
    listing = client.get(base, headers=lan).json()
    assert listing["ready_for_decision"] is True and listing["counts"]["accepted"] == 1
    assert client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING"}, headers=bank).status_code == 200
    # Every transition is in the tamper-evident audit chain.
    text = backend.coord.audit_path.read_text()
    for action in ("opened", "submitted", "rejected", "accepted"):
        assert f"evidence {action}" in text
    assert verify_chain(backend.coord.audit_path)[0] is True


def test_revoke_unblocks_and_other_parties_are_refused(api):
    from tests.test_adversarial import outsider
    client, _, pack = api
    bank = client.header("bank.lihua")
    base = f"/api/workspace/cases/{pack}/evidence"
    rid = client.post(base, json={"item": "Insurance certificate", "detail": "Cargo insurance for INV-1030"}, headers=bank).json()["id"]
    assert client.get(base, headers=outsider("bank_reviewer", tenant="LENDER-OTHER")).status_code == 403
    assert client.get(base, headers=outsider("sme_accountant")).status_code == 403
    assert client.post(base, json={"item": "Anything", "detail": "from SME"}, headers=client.header("sme.lan")).status_code == 403
    assert client.post(f"{base}/{rid}/revoke", json={"reason": "Not needed for factoring"}, headers=bank).json()["status"] == "revoked"
    assert client.get(base, headers=bank).json()["ready_for_decision"] is True
    assert client.post(f"/api/workspace/cases/{pack}/evidence/EVR-NOPE/submit",
                       json={"evidence_ref": "X-1", "sha256": SHA_A}, headers=client.header("sme.lan")).status_code == 404


def test_no_evidence_requests_before_release(tmp_path, monkeypatch):
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-ui"))
    r = client.post("/api/workspace/cases/PACK-ANY/evidence", json={"item": "B/L", "detail": "please"}, headers=client.header("bank.lihua"))
    assert r.status_code == 404


def test_unresolved_requests_expire_and_stop_blocking_as_expired(tmp_path):
    now = [datetime(2026, 10, 20, tzinfo=timezone.utc)]
    desk = EvidenceDesk(tmp_path / "ws.db", clock=lambda: now[0])
    rid = desk.open("T", "PACK-1", "bank.lihua", "Packing list", "for INV-1030", due_days=2)["id"]
    assert desk.blocking("T", "PACK-1") == [rid]
    now[0] += timedelta(days=3)
    listing = desk.list("T", "PACK-1")
    assert listing["items"][0]["status"] == "expired" and listing["blocking_funding"] == []
    with pytest.raises(ValueError):
        desk.submit("T", "PACK-1", rid, "sme.lan", "DOC-1", SHA_A)
    assert any("expired" in n["text"] for n in desk.notifications("T", "sme"))


def test_submission_limit(tmp_path):
    desk = EvidenceDesk(tmp_path / "ws.db")
    rid = desk.open("T", "P", "bank", "Statement", "October statement")["id"]
    for i in range(5):
        desk.submit("T", "P", rid, "sme", f"DOC-{i}", SHA_A)
        desk.review("T", "P", rid, "bank", False, "still wrong")
    with pytest.raises(ValueError, match="limit"):
        desk.submit("T", "P", rid, "sme", "DOC-6", SHA_A)
