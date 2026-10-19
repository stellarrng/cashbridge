"""Bank portal: sees only what the Director released, re-verifies it, records a human decision."""

import pytest

from api.main import create_app
from scripts.run_demo_story import StoryClock
from tests.authed import RoleClient
from ui.backend_real import RealBackend


@pytest.fixture
def backend(tmp_path):
    return RealBackend(runtime_dir=tmp_path, clock=StoryClock())


@pytest.fixture
def client(backend, tmp_path):
    return RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))


def submit(client, backend):
    assert client.post("/api/autopilot/run", json={"execute": True}).json()["decision"] == "AWAITING_DIRECTOR_APPROVAL"
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    result = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()
    assert result["ok"], result
    return result["snapshot"]["pack"]["pack_id"]


def test_nothing_is_visible_before_submission(client):
    inbox = client.get("/api/bank/inbox").json()
    assert inbox["items"] == []
    client.post("/api/autopilot/run", json={"execute": True})  # drafted but not approved
    assert client.get("/api/bank/inbox").json()["items"] == []
    pack_id = client.get("/api/snapshot").json()["pack"]["pack_id"]
    assert client.get(f"/api/bank/cases/{pack_id}").status_code == 404


def test_full_two_portal_flow(client, backend):
    pack_id = submit(client, backend)
    inbox = client.get("/api/bank/inbox").json()["items"]
    assert [i["pack_id"] for i in inbox] == [pack_id]
    assert inbox[0]["prepared_by"] == "sme.lan" and inbox[0]["submitted_by"] == "sme.minh"
    case = client.get(f"/api/bank/cases/{pack_id}").json()
    assert case["invoice"]["invoice_no"] == "INV-1030" and "Inbox and contacts" in case["not_shared"]
    assert "alerts" not in case and "chat" not in case  # data minimisation
    # A decision needs a verification first.
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "APPROVE_FUNDING"}).status_code == 409
    verify = client.post(f"/api/bank/cases/{pack_id}/verify").json()
    assert verify["all_verifiable_ok"] is True
    assert any(c["ok"] is None for c in verify["checks"])  # cross-lender check stays honest
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "DECLINE"}).status_code == 409  # needs a reason
    done = client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "APPROVE_FUNDING", "note": "KYC done offline"}).json()
    assert done["case_state"] == "FUNDED" and done["review"]["status"] == "FUNDED_MOCK"
    snap = client.get("/api/snapshot").json()
    assert snap["lender_review"]["decision"] == "APPROVE_FUNDING" and snap["meta"]["case_state"] == "FUNDED"
    assert "credit decision recorded by human reviewer Li Hua 李华" in backend.coord.audit_path.read_text()


def test_tampered_documents_fail_bank_verification(client, backend):
    pack_id = submit(client, backend)
    invoice = backend.coord.nominee
    backend.coord.all_invoices[backend.coord.all_invoices.index(invoice)] = invoice.model_copy(update={"package_count": 999})
    backend.coord.nominee = backend.coord.all_invoices[[i.invoice_no for i in backend.coord.all_invoices].index(invoice.invoice_no)]
    checks = {c["check"]: c["ok"] for c in client.post(f"/api/bank/cases/{pack_id}/verify").json()["checks"]}
    assert checks["Source documents hash to the values in the pack"] is False
    assert checks["Bundle SHA-256 recomputed from documents + locked metrics"] is False


def test_director_can_reject_and_accountant_rework(client):
    client.post("/api/autopilot/run", json={"execute": True})
    rejected = client.post("/api/reject_pack", json={"reason": "Size the facility to the trough first"}).json()
    assert rejected["pack"]["status"] == "REJECTED_BY_DIRECTOR" and rejected["meta"]["case_state"] == "NEEDS_HUMAN"
    assert client.post("/api/approve", json={"code": "123456"}).status_code == 409  # nothing awaiting approval
    reopened = client.post("/api/reopen_pack").json()
    assert reopened["meta"]["case_state"] == "INVOICE_VERIFIED" and reopened["pack"]["status"] == "NOT_STARTED"
