"""T05: adversarial tests by role and tenant, through the HTTP API.

Each test is an attack a judge (or a real adversary) could try with a valid session of the wrong
role or organisation, a malformed payload, a replayed code or a forged token. Every one must be
refused on the server, without a 500, and the audit chain must stay intact.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import DIST_DIR, MAX_BODY_BYTES, create_app
from scripts.run_demo_story import StoryClock
from security import auth
from security.audit_log import verify_chain
from tests.authed import RoleClient
from ui.backend_real import RealBackend


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    monkeypatch.delenv("CASHBRIDGE_REQUIRE_DATA_GATE", raising=False)
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-ui"))
    return client, backend


def outsider(role="sme_accountant", tenant="TEN-OTHER-002", user="intruder"):
    """A perfectly valid, correctly signed session for a user of ANOTHER organisation."""
    sessions = auth.get_sessions()
    token = sessions.issue({"user_id": user, "name": "Intruder", "role": role, "org": "Other Co", "tenant_id": tenant})["token"]
    return {"Authorization": "Bearer " + token}


def submit(client, backend):
    assert client.post("/api/autopilot/run", json={"execute": True}).status_code == 200
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    code = backend.coord.otp.current_code()
    published = client.post("/api/approve", json={"code": code})
    assert published.status_code == 200 and published.json()["ok"], published.text
    return published.json()["snapshot"]["pack"]["pack_id"], code


# --------------------------------------------------------------------------- tenant isolation
SME_READS = ["/api/snapshot", "/api/workspace/requests", "/api/workspace/data-gate", "/forecast", "/reconcile",
             "/funding-options", "/api/analytics/summary", "/api/intelligence", "/api/green-finance", "/audit/verify"]
SME_WRITES = [("/api/workspace/requests", {"field": "marketing_usd", "proposed_value": "10", "reason": "Cross-tenant write"}),
              ("/api/workspace/appeals", {"reason": "cross-tenant appeal attempt", "evidence_ref": "DOC-1"}),
              ("/api/workspace/scenario", {"available_cash_usd": 1, "minimum_reserve_usd": 1}),
              ("/api/workspace/quality", {}), ("/api/prepare_pack", {}), ("/api/choose_option", {"option_id": "factoring_inv1030"}),
              ("/packs", {"option_id": "factoring_inv1030"}), ("/api/autopilot/run", {"execute": False})]


def test_another_sme_tenant_cannot_read_or_write_anything(api):
    client, _ = api
    for role in ("sme_accountant", "sme_director"):
        h = outsider(role)
        for path in SME_READS:
            assert client.get(path, headers=h).status_code == 403, (role, path)
        for path, body in SME_WRITES:
            assert client.post(path, json=body, headers=h).status_code == 403, (role, path)


def test_another_lender_cannot_see_the_bank_inbox_or_cases(api):
    client, backend = api
    pack_id, _ = submit(client, backend)
    h = outsider("bank_reviewer", tenant="LENDER-OTHER-9")
    for path in ("/api/bank/inbox", f"/api/bank/cases/{pack_id}", f"/api/bank/cases/{pack_id}/pdf",
                 f"/api/workspace/cases/{pack_id}/messages"):
        assert client.get(path, headers=h).status_code == 403, path
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "APPROVE_FUNDING"}, headers=h).status_code == 403
    assert client.post(f"/api/workspace/cases/{pack_id}/messages", json={"kind": "question", "message": "hello there"},
                       headers=h).status_code == 403


def test_bank_never_sees_internal_sme_workspace(api):
    client, backend = api
    submit(client, backend)
    bank = client.header("bank.lihua")
    for path in ("/api/workspace/requests", "/api/workspace/data-gate", "/api/snapshot", "/api/pack/pdf"):
        assert client.get(path, headers=bank).status_code == 403, path
    for path, body in SME_WRITES:
        assert client.post(path, json=body, headers=bank).status_code == 403, path
    assert client.post("/api/workspace/requests/x/review", json={"approve": True, "note": "bank"}, headers=bank).status_code == 403


# --------------------------------------------------------------------------- separation of duties
def test_four_eyes_on_planning_changes_and_stale_requests(api):
    client, _ = api
    lan, olivia, minh = (client.header(u) for u in ("sme.lan", "sme.minh", "sme.minh"))
    first = client.post("/api/workspace/requests", json={"field": "green_investment_usd", "proposed_value": "5000",
                                                          "reason": "Solar roof deposit"}, headers=lan).json()["id"]
    second = client.post("/api/workspace/requests", json={"field": "green_investment_usd", "proposed_value": "9000",
                                                           "reason": "Bigger solar roof"}, headers=lan).json()["id"]
    # The preparer can neither review her own request nor anyone's; the Director cannot propose.
    assert client.post(f"/api/workspace/requests/{first}/review", json={"approve": True, "note": "self ok"}, headers=lan).status_code == 403
    assert client.post("/api/workspace/requests", json={"field": "marketing_usd", "proposed_value": "1",
                                                        "reason": "Director proposing"}, headers=minh).status_code == 403
    assert client.post(f"/api/workspace/requests/{first}/review", json={"approve": True, "note": "approved"}, headers=minh).status_code == 200
    # Decided requests cannot be re-decided; stale requests cannot overwrite a newer value.
    assert client.post(f"/api/workspace/requests/{first}/review", json={"approve": False, "note": "flip"}, headers=minh).status_code == 409
    stale = client.post(f"/api/workspace/requests/{second}/review", json={"approve": True, "note": "late"}, headers=minh)
    assert stale.status_code == 409 and "Stale" in stale.json()["detail"]


def test_preparer_cannot_approve_pack_and_director_cannot_prepare(api):
    client, backend = api
    lan, minh = client.header("sme.lan"), client.header("sme.minh")
    assert client.post("/api/autopilot/run", json={"execute": True}, headers=lan).status_code == 200
    client.post("/api/request_otp", headers=lan)
    code = backend.coord.otp.current_code()
    assert client.post("/api/approve", json={"code": code}, headers=lan).status_code == 403
    assert client.post(f"/packs/{backend.coord.pack['pack_id']}/approve", json={"code": code}, headers=lan).status_code == 403
    assert client.post("/api/prepare_pack", headers=minh).status_code == 403
    assert client.post("/packs", json={"option_id": "factoring_inv1030"}, headers=minh).status_code == 403


# --------------------------------------------------------------------------- OTP replay and brute force
def test_otp_replay_after_release_is_refused(api):
    client, backend = api
    pack_id, code = submit(client, backend)
    again = client.post("/api/approve", json={"code": code})
    assert again.status_code == 409  # no open challenge: the release cannot be repeated
    assert client.post(f"/packs/{pack_id}/approve", json={"code": code}).status_code in (403, 409)
    assert backend.coord.state.value == "SUBMITTED"


def test_otp_is_bound_to_the_exact_pack(api):
    client, backend = api
    assert client.post("/api/autopilot/run", json={"execute": True}).status_code == 200
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    code = backend.coord.otp.current_code()
    backend.coord._pack_payload = {**backend.coord._pack_payload, "amount_usd": "999999"}  # payload edited after the challenge
    refused = client.post("/api/approve", json={"code": code})
    assert refused.status_code == 200 and refused.json()["ok"] is False and refused.json()["error"] == "payload_mismatch"


def test_otp_brute_force_voids_the_challenge(api):
    from config.settings import OTP_MAX_FAILED_ATTEMPTS
    client, backend = api
    assert client.post("/api/autopilot/run", json={"execute": True}).status_code == 200
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    good = backend.coord.otp.current_code()
    wrong = [f"{(int(good) + i) % 1_000_000:06d}" for i in range(500_000, 500_000 + OTP_MAX_FAILED_ATTEMPTS)]
    for w in wrong:
        assert client.post("/api/approve", json={"code": w}).json()["error"] == "invalid_code"
    # Even the right code is now refused: the challenge is gone and a fresh one must be requested.
    assert client.post("/api/approve", json={"code": good}).status_code == 409
    assert "voided after" in backend.coord.audit_path.read_text()
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    assert client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()["ok"] is True


# --------------------------------------------------------------------------- lender decisions
def test_lender_cannot_decide_twice_or_before_verifying(api):
    client, backend = api
    pack_id, _ = submit(client, backend)
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "APPROVE_FUNDING"}).status_code == 409
    assert client.post(f"/api/bank/cases/{pack_id}/verify").status_code == 200
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "DECLINE"}).status_code == 409  # needs a reason
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "APPROVE_FUNDING"}).status_code == 200
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "DECLINE", "note": "changed mind"}).status_code == 409
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "WIRE_NOW"}).status_code == 422


def test_bank_cannot_open_a_pack_id_it_was_not_given(api):
    client, backend = api
    pack_id, _ = submit(client, backend)
    for probe in ("PACK-00000000", pack_id.lower(), pack_id + "x", "' OR 1=1 --", "..%2f..%2fetc%2fpasswd"):
        r = client.get(f"/api/bank/cases/{probe}")
        assert r.status_code == 404, (probe, r.status_code)


# --------------------------------------------------------------------------- correspondence
def test_message_kinds_are_bound_to_the_sender_role(api):
    client, backend = api
    pack_id, _ = submit(client, backend)
    url = f"/api/workspace/cases/{pack_id}/messages"
    lan, minh, bank = client.header("sme.lan"), client.header("sme.minh"), client.header("bank.lihua")
    assert client.post(url, json={"kind": "evidence_request", "message": "fake bank request"}, headers=lan).status_code == 403
    assert client.post(url, json={"kind": "response", "message": "bank pretending to be SME"}, headers=bank).status_code == 403
    assert client.post(url, json={"kind": "response", "message": "director answer"}, headers=minh).status_code == 403  # no sme:prepare
    assert client.post(url, json={"kind": "evidence_request", "message": "Please send the B/L"}, headers=bank).status_code == 200
    assert client.post(url, json={"kind": "response", "message": "B/L attached as DOC-7"}, headers=lan).status_code == 200


def test_hostile_text_is_stored_as_data_not_executed(api):
    client, backend = api
    pack_id, _ = submit(client, backend)
    url = f"/api/workspace/cases/{pack_id}/messages"
    payload = "<img src=x onerror=alert(1)>'); DROP TABLE messages;--"
    assert client.post(url, json={"kind": "question", "message": payload}, headers=client.header("bank.lihua")).status_code == 200
    items = client.get(url).json()["items"]
    assert items[-1]["message"] == payload  # stored verbatim; the UI escapes on render (see test_ui_escapes_*)
    assert client.post(url, json={"kind": "question", "message": "bell\x07char"}, headers=client.header("bank.lihua")).status_code == 422


# --------------------------------------------------------------------------- malformed input
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e400", "-5", "1.001", "9" * 40, "", "abc", "0x10"])
def test_malformed_amounts_are_rejected(api, value):
    client, _ = api
    r = client.post("/api/workspace/requests", json={"field": "marketing_usd", "proposed_value": value, "reason": "Fuzzing the amount"})
    assert r.status_code == 422, (value, r.status_code, r.text)


@pytest.mark.parametrize("body", [
    {"field": "ledger_cash", "proposed_value": "1", "reason": "Edit the ledger directly"},
    {"field": "marketing_usd", "proposed_value": "1", "reason": "short"},
    {"field": "marketing_usd", "proposed_value": "1", "reason": "x" * 501},
    {"field": "marketing_usd", "proposed_value": "1"},
    {"field": "marketing_usd", "proposed_value": True, "reason": "Boolean amount"},
])
def test_malformed_planning_requests_are_rejected(api, body):
    client, _ = api
    assert client.post("/api/workspace/requests", json=body).status_code == 422, body


def test_garbage_bodies_never_cause_a_server_error(api):
    client, _ = api
    h = {**client.header("sme.lan"), "Content-Type": "application/json"}
    for raw in (b"{", b"[]", b"null", b'{"field": {"$ne": null}}', "{\"reason\": \"\u0000\"}".encode(), b"\xff\xfe"):
        for path in ("/api/workspace/requests", "/api/workspace/appeals", "/api/approve", "/packs", "/api/simulate"):
            r = client.post(path, content=raw, headers=h if path != "/api/approve" else {**client.header("sme.minh"), "Content-Type": "application/json"})
            assert r.status_code < 500, (path, raw, r.status_code)
    for rid in ("' OR 1=1 --", "1;DROP TABLE requests", "%00", "a" * 300):
        r = client.post(f"/api/workspace/requests/{rid}/review", json={"approve": True, "note": "probe"}, headers=client.header("sme.minh"))
        assert r.status_code in (404, 409), (rid, r.status_code)


def test_oversized_and_lying_bodies_are_refused_early(api):
    client, _ = api
    h = {**client.header("sme.lan"), "Content-Type": "application/json"}
    assert client.post("/api/workspace/quality", content=b"{}", headers={**h, "Content-Length": str(MAX_BODY_BYTES + 1)}).status_code == 413
    big = json.dumps({"sources": [], "ledger_entries": [{"reference": "x" * 50, "amount": "1"}] * 150_000}).encode()
    assert len(big) > MAX_BODY_BYTES
    assert client.post("/api/workspace/quality", content=big, headers=h).status_code == 413
    too_many = {"sources": [], "ledger_entries": [{"reference": f"R{i}", "amount": "1"} for i in range(201)], "bank_entries": []}
    assert client.post("/api/workspace/quality", json=too_many, headers=h).status_code == 422


# --------------------------------------------------------------------------- sessions and sign-in
def test_forged_token_shapes_are_refused(api):
    client, _ = api
    body, sig = client.tokens["sme.minh"].split(".")
    claims = json.loads(auth._unb64(body))
    for token in ("", ".", body + ".", "." + sig, body + "." + sig + ".x", "eyJhbGciOiJub25lIn0." + body + ".",
                  auth._b64(json.dumps({**claims, "ten": auth.LENDER_TENANT}).encode()) + "." + sig,
                  auth._b64(json.dumps({**claims, "role": "admin"}).encode()) + "." + sig, body + "." + sig[:-2] + "AA"):
        r = client.get("/api/snapshot", headers={"Authorization": "Bearer " + token})
        assert r.status_code == 401, (token[:30], r.status_code)
    assert client.get("/api/snapshot", headers={"Authorization": "Basic " + client.tokens["sme.minh"]}).status_code == 401


def test_rotating_x_forwarded_for_does_not_bypass_the_sign_in_throttle(api, monkeypatch):
    client, _ = api
    monkeypatch.delenv("CASHBRIDGE_TRUST_PROXY", raising=False)
    statuses = [client.post("/api/auth/login", json={"user_id": "sme.chen", "passcode": "guess"},
                            headers={"X-Forwarded-For": f"198.51.100.{i}"}).status_code for i in range(auth.LOGIN_MAX_FAILURES + 1)]
    assert statuses[-1] == 429


def test_per_account_throttle_holds_behind_a_trusted_proxy(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv("CASHBRIDGE_TRUST_PROXY", "1")
    statuses = [client.post("/api/auth/login", json={"user_id": "sme.olivia", "passcode": "guess"},
                            headers={"X-Forwarded-For": f"198.51.100.{i}"}).status_code
                for i in range(auth.LOGIN_MAX_FAILURES_PER_ACCOUNT + 1)]
    assert statuses[:auth.LOGIN_MAX_FAILURES_PER_ACCOUNT] == [401] * auth.LOGIN_MAX_FAILURES_PER_ACCOUNT
    assert statuses[-1] == 429


# --------------------------------------------------------------------------- automation API tokens
def test_automation_operator_token_cannot_review_or_redrive(tmp_path, monkeypatch):
    monkeypatch.setenv("CASHBRIDGE_AUTOMATION_TOKEN", "op-" + "a" * 30)
    monkeypatch.setenv("CASHBRIDGE_AUDIT_REVIEWER_TOKEN", "rv-" + "b" * 30)
    monkeypatch.setenv("CASHBRIDGE_AUTOMATION_DB", str(tmp_path / "q.db"))
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    raw = TestClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    op = {"Authorization": "Bearer op-" + "a" * 30}
    rv = {"Authorization": "Bearer rv-" + "b" * 30}
    assert raw.get("/api/automation/dead-letters", headers=op).status_code == 403
    assert raw.post("/api/automation/dead-letters/x/redrive", headers=op).status_code == 403
    assert raw.get("/api/automation/dead-letters", headers=rv).status_code == 200
    assert raw.get("/api/automation/jobs").status_code == 401
    # A signed-in SME session is not an automation credential.
    sme = {"Authorization": "Bearer " + auth.get_sessions().issue(auth.get_sessions().users["sme.lan"])["token"]}
    assert raw.get("/api/automation/jobs", headers=sme).status_code == 403


# --------------------------------------------------------------------------- static files and audit
def test_static_route_never_serves_files_outside_the_web_root(tmp_path):
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    raw = TestClient(create_app(lambda: backend, dist_dir=DIST_DIR))
    for path in ("/../../api/main.py", "/..%2f..%2fapi%2fmain.py", "/assets/../../../README.md", "/%2e%2e/%2e%2e/Makefile"):
        r = raw.get(path)
        assert "create_app" not in r.text and "PYTEST" not in r.text and "uvicorn" not in r.text, path


def test_audit_chain_survives_the_attacks(api):
    client, backend = api
    test_another_sme_tenant_cannot_read_or_write_anything(api)
    client.post("/api/approve", json={"code": "000000"}, headers=client.header("sme.lan"))
    ok, _, lines = verify_chain(backend.coord.audit_path)
    assert ok and lines > 10
    assert "intruder (sme_accountant, TEN-OTHER-002)" in backend.coord.audit_path.read_text()
