"""Extra engine endpoints (Step 6.2)."""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from tests.authed import RoleClient
from scripts.run_demo_story import StoryClock
from ui.backend_real import RealBackend


@pytest.fixture
def backend(tmp_path):
    return RealBackend(runtime_dir=tmp_path, clock=StoryClock())


@pytest.fixture
def client(backend, tmp_path):
    return RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))


def audit(backend):
    return [json.loads(l) for l in backend.coord.audit_path.read_text().splitlines()]


def test_forecast_returns_thirteen_weeks_and_the_first_shortfall(client):
    body = client.get("/forecast").json()
    assert len(body["forecast"]["weeks"]) == 13 and body["kpis"]["first_shortfall_week"] == 7


def test_forecast_with_scenario_parameters_changes_the_result_and_is_logged(client, backend):
    base = client.get("/forecast").json()["forecast"]["weeks"]
    scenario = client.get("/forecast", params={"dso_change_days": 15})
    assert scenario.status_code == 200
    assert scenario.json()["forecast"]["weeks"] != base and scenario.json()["delta"]["first_shortfall_week_before"] == 7
    assert audit(backend)[-1]["tool"] == "run_scenario" and audit(backend)[-1]["decision"] == "ALLOWED"


def test_forecast_rejects_out_of_range_parameters(client):
    assert client.get("/forecast", params={"fx_change_pct": 50}).status_code == 422


def test_reconcile_lists_the_matches(client):
    body = client.get("/reconcile").json()
    wire = next(r for r in body["rows"] if r["txn_id"] == "TXN-0912")
    assert wire["tier"] == 3 and wire["gap"] == 35 and body["featured_wire"]["txn_id"] == "TXN-0912"


def test_funding_options_are_ranked_cheapest_first(client):
    options = client.get("/funding-options").json()
    assert [o["id"] for o in options][:3] == ["factoring_inv1030", "bridge_loan", "early_discount"]
    assert options[-1]["eligible"] is False and options[0]["apr_pct"] < options[1]["apr_pct"]


def test_creating_a_pack_drafts_it_and_writes_the_pdf(client, backend):
    response = client.post("/packs", json={"option_id": "factoring_inv1030"})
    assert response.status_code == 201
    pack = response.json()
    assert pack["status"] == "AWAITING_APPROVAL" and pack["pack_id"].startswith("PACK-") and pack["pdf_path"]
    assert backend.pack_pdf().exists()


def test_a_refused_option_is_a_409(client):
    assert client.post("/packs", json={"option_id": "overdraft"}).status_code == 409
    assert client.post("/packs", json={"option_id": "early_discount"}).status_code == 409


def test_approving_without_asking_for_a_code_first_fails(client):
    pack_id = client.post("/packs", json={"option_id": "factoring_inv1030"}).json()["pack_id"]
    response = client.post(f"/packs/{pack_id}/approve", json={"code": "123456"})
    assert response.status_code == 409 and "request approval" in response.json()["detail"]


def test_approval_needs_the_real_otp_and_then_submits(client, backend):
    pack_id = client.post("/packs", json={"option_id": "factoring_inv1030"}).json()["pack_id"]
    challenge = client.post(f"/packs/{pack_id}/request-approval").json()
    assert set(challenge) == {"action_hash", "expires_at", "instructions"}
    wrong = "000000" if backend.coord.otp.current_code() != "000000" else "111111"
    bad = client.post(f"/packs/{pack_id}/approve", json={"code": wrong})
    assert bad.status_code == 403 and bad.json() == {"ok": False, "error": "invalid_code", "pack": bad.json()["pack"]}
    assert bad.json()["pack"]["status"] == "AWAITING_APPROVAL" and backend.coord.registry.blocks() == []
    good = client.post(f"/packs/{pack_id}/approve", json={"code": backend.coord.otp.current_code()})
    assert good.status_code == 200 and good.json()["ok"] and good.json()["pack"]["status"] == "SUBMITTED"
    assert good.json()["pack"]["lender_ref"].startswith("MOCK-") and len(backend.coord.registry.blocks()) == 1


def test_the_audit_log_shows_the_gatekeeper_decisions_for_every_step(client, backend):
    pack_id = client.post("/packs", json={"option_id": "factoring_inv1030"}).json()["pack_id"]
    client.post(f"/packs/{pack_id}/request-approval")
    client.post(f"/packs/{pack_id}/approve", json={"code": "000000" if backend.coord.otp.current_code() != "000000" else "111111"})
    client.post(f"/packs/{pack_id}/approve", json={"code": backend.coord.otp.current_code()})
    decisions = [(l["tool"], l["decision"]) for l in audit(backend) if l["tool"] == "submit_pack"]
    assert decisions == [("submit_pack", "AWAITING_APPROVAL"), ("submit_pack", "REJECTED"), ("submit_pack", "APPROVED"), ("submit_pack", "ALLOWED")]


def test_a_second_approval_of_a_submitted_pack_is_refused(client, backend):
    pack_id = client.post("/packs", json={"option_id": "factoring_inv1030"}).json()["pack_id"]
    client.post(f"/packs/{pack_id}/request-approval")
    client.post(f"/packs/{pack_id}/approve", json={"code": backend.coord.otp.current_code()})
    again = client.post(f"/packs/{pack_id}/approve", json={"code": backend.coord.otp.current_code()})
    assert again.status_code == 409 and len(backend.coord.registry.blocks()) == 1


def test_an_unknown_pack_is_a_404(client):
    client.post("/packs", json={"option_id": "factoring_inv1030"})
    assert client.post("/packs/PACK-NOPE/request-approval").status_code == 404
    assert client.post("/packs/PACK-NOPE/approve", json={"code": "123456"}).status_code == 404


def test_audit_verify_reports_the_chain(client):
    body = client.get("/audit/verify").json()
    assert body["ok"] is True and body["broken_seq"] is None and body["lines_checked"] > 0


def test_engine_endpoints_are_documented(client):
    paths = client.get("/openapi.json").json()["paths"]
    for route in ("/forecast", "/reconcile", "/funding-options", "/packs", "/packs/{pack_id}/approve", "/audit/verify"):
        assert route in paths, route
    assert client.get("/docs").status_code == 200
