"""Negative tests: the server refuses what a role may not do, whatever the browser shows."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config import runtime_mode
from scripts.run_demo_story import StoryClock
from security import auth
from tests.authed import RoleClient
from ui.backend_real import RealBackend


@pytest.fixture
def backend(tmp_path):
    return RealBackend(runtime_dir=tmp_path, clock=StoryClock())


@pytest.fixture
def client(backend, tmp_path):
    return RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))


def test_every_case_route_needs_a_session(backend, tmp_path):
    raw = TestClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    for method, path in [("GET", "/api/snapshot"), ("POST", "/api/prepare_pack"), ("POST", "/api/approve"),
                         ("GET", "/forecast"), ("GET", "/api/bank/inbox"), ("POST", "/api/autopilot/run"),
                         ("POST", "/api/reset_demo"), ("GET", "/api/pack/pdf")]:
        response = raw.request(method, path, json={"code": "123456"} if path == "/api/approve" else {})
        assert response.status_code == 401, (path, response.status_code)


def test_tampered_expired_and_signed_out_tokens_are_refused(client):
    token = client.tokens["sme.lan"]
    body, sig = token.split(".")
    claims = json.loads(auth._unb64(body))
    claims["role"] = "sme_director"  # privilege escalation attempt: re-sign is impossible without the secret
    forged = auth._b64(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()) + "." + sig
    assert client.get("/api/snapshot", headers={"Authorization": "Bearer " + forged}).status_code == 401
    assert client.get("/api/snapshot", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    sessions = auth.get_sessions()
    old = sessions.issue(sessions.users["sme.lan"])
    sessions._clock = lambda: time.time() + auth.SESSION_TTL_SECONDS + 5
    try:
        assert client.get("/api/snapshot", headers={"Authorization": "Bearer " + old["token"]}).status_code == 401
    finally:
        sessions._clock = time.time
    fresh = sessions.issue(sessions.users["sme.lan"])["token"]
    assert client.post("/api/auth/logout", headers={"Authorization": "Bearer " + fresh}).status_code == 200
    assert client.get("/api/snapshot", headers={"Authorization": "Bearer " + fresh}).status_code == 401


def test_permission_matrix(client):
    director, accountant, banker = (client.header(u) for u in ("sme.minh", "sme.lan", "bank.lihua"))
    # The Director approves but never prepares; the accountant prepares but never approves.
    assert client.post("/api/choose_option", json={"option_id": "factoring_inv1030"}, headers=director).status_code == 403
    assert client.post("/api/prepare_pack", headers=director).status_code == 403
    assert client.post("/api/autopilot/run", json={"execute": True}, headers=director).status_code == 403
    assert client.post("/api/approve", json={"code": "123456"}, headers=accountant).status_code == 403
    assert client.post("/api/reject_pack", json={"reason": "nope"}, headers=accountant).status_code == 403
    # The lender sees nothing of the SME workspace, and the SME cannot act as the lender.
    for path in ("/api/snapshot", "/forecast", "/api/analytics/summary", "/api/pack/pdf"):
        assert client.get(path, headers=banker).status_code == 403, path
    assert client.get("/api/bank/inbox", headers=accountant).status_code == 403
    assert client.post("/api/bank/cases/PACK-X/decision", json={"decision": "APPROVE_FUNDING"}, headers=director).status_code == 403
    # Plan-only Autopilot is allowed for the Director.
    assert client.post("/api/autopilot/run", json={"execute": False}, headers=director).status_code == 200


def test_portal_mismatch_and_wrong_passcode(client):
    assert client.post("/api/auth/demo-login", json={"user_id": "bank.lihua", "portal": "sme"}).status_code == 403
    assert client.post("/api/auth/login", json={"user_id": "sme.lan", "passcode": "wrong"}).status_code == 401
    ok = client.post("/api/auth/login", json={"user_id": "sme.lan", "passcode": "lan-demo-2026", "portal": "sme"})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "sme_accountant"


def test_login_is_throttled(client):
    statuses = [client.post("/api/auth/login", json={"user_id": "sme.minh", "passcode": "x"},
                            headers={"X-Forwarded-For": "203.0.113.9"}).status_code for _ in range(auth.LOGIN_MAX_FAILURES + 1)]
    assert statuses[-1] == 429


def test_other_tenant_is_refused(client):
    sessions = auth.get_sessions()
    outsider = {**sessions.users["sme.lan"], "user_id": "sme.other", "tenant_id": "TEN-OTHER"}
    token = sessions.issue(outsider)["token"]
    assert client.get("/api/snapshot", headers={"Authorization": "Bearer " + token}).status_code == 403


def test_self_approval_is_refused_even_with_a_valid_code(backend):
    backend.coord.choose_option("factoring_inv1030")
    backend.prepare_pack(actor="sme.minh")
    backend.request_otp()
    code = backend.coord.otp.current_code()
    refused = backend.approve(code, approver="sme.minh")
    assert refused["ok"] is False and refused["error"] == "segregation_of_duties"
    assert backend.coord.state.value == "AWAITING_APPROVAL"
    assert "Segregation of duties" in backend.coord.audit_path.read_text()
    assert backend.approve(code, approver="sme.lan")["ok"] is True  # the code was not spent by the refusal


def test_production_mode_fails_closed(monkeypatch):
    env = {"CASHBRIDGE_ENV": "production", "OTP_SECRET": "JBSWY3DPEHPK3PXP"}
    problems = runtime_mode.production_problems(env)
    assert any("public demo secret" in p for p in problems)
    assert any("SESSION_SECRET" in p for p in problems)
    assert any("user accounts" in p for p in problems)
    monkeypatch.setenv("CASHBRIDGE_ENV", "production")
    monkeypatch.delenv("OTP_SECRET", raising=False)
    with pytest.raises(runtime_mode.ProductionConfigError):
        create_app(lambda: None)
    with pytest.raises(runtime_mode.ProductionConfigError):
        auth.SessionManager(env={"CASHBRIDGE_ENV": "production"})


def test_production_mode_disables_demo_shortcuts(monkeypatch, backend, tmp_path):
    users = [{"user_id": "sme.lan", "name": "Lan Nguyen", "role": "sme_accountant", "org": "x",
              "tenant_id": auth.SME_TENANT, "passcode_hash": auth.hash_passcode("a-long-real-passcode")}]
    env = {"CASHBRIDGE_ENV": "production", "OTP_SECRET": "KRSXG5CTMVRXEZLUKN2XAZLSKNSWG4TFOQ",
           "CASHBRIDGE_SESSION_SECRET": "s" * 40, "CASHBRIDGE_USERS_JSON": json.dumps(users)}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    auth.reset_sessions_for_tests(auth.SessionManager())
    try:
        c = TestClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
        assert c.get("/api/auth/config").json()["demo_accounts"] == []
        assert c.post("/api/auth/demo-login", json={"user_id": "sme.lan"}).status_code == 404
        token = c.post("/api/auth/login", json={"user_id": "sme.lan", "passcode": "a-long-real-passcode"}).json()["token"]
        h = {"Authorization": "Bearer " + token}
        assert c.get("/api/snapshot", headers=h).status_code == 200
        assert c.post("/api/reset_demo", headers=h).status_code == 404
        assert c.post("/api/tamper_demo", headers=h).status_code == 404
        assert c.get("/api/public/overview").status_code == 404
    finally:
        auth.reset_sessions_for_tests(None)


def test_security_headers_present(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
