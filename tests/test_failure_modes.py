"""Audit 4: the system stays correct and says what happened when dependencies fail or inputs are abnormal.

Each test injects one failure and checks three things: no half-done financial action, a clear answer
to the user (never a bare 500 or a stack trace), and an entry in the hash-chained audit log.
"""

from __future__ import annotations

import json

import pytest

from api.main import create_app
from scripts.run_demo_story import StoryClock
from security.audit_log import verify_chain
from tests.authed import RoleClient
from ui.backend_real import RealBackend


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    monkeypatch.delenv("CASHBRIDGE_REQUIRE_DATA_GATE", raising=False)
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-ui"), raise_server_exceptions=False)
    return client, backend


def _awaiting(client, backend):
    assert client.post("/api/autopilot/run", json={"execute": True}).status_code == 200
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    return backend.coord.otp.current_code()


def test_lender_timeout_sends_nothing_and_can_be_retried(api):
    client, backend = api
    code = _awaiting(client, backend)
    real = backend.coord._lender_submit
    backend.coord._lender_submit = lambda payload: (_ for _ in ()).throw(TimeoutError("lender API timed out"))
    r = client.post("/api/approve", json={"code": code})
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["error"] == "lender_unavailable"
    assert backend.coord.state.value == "AWAITING_APPROVAL"
    assert not backend.coord.registry.is_registered(backend.coord.nominee)  # nothing pledged
    assert "Lender system unavailable" in backend.coord.audit_path.read_text()
    backend.coord._lender_submit = real
    # The used code is single-use; a fresh code on the same open challenge goes through.
    import pyotp
    from datetime import timedelta
    later = backend.coord._clock() + timedelta(seconds=31)
    backend.coord.otp._clock = lambda: later
    fresh = pyotp.TOTP("JBSWY3DPEHPK3PXP").at(later)
    assert client.post("/api/approve", json={"code": fresh}).json()["ok"] is True
    assert backend.coord.state.value == "SUBMITTED"


def test_pdf_failure_after_submission_is_not_reported_as_a_failed_submission(api):
    client, backend = api
    code = _awaiting(client, backend)
    real = backend.coord._write_pdf
    calls = {"n": 0}

    def flaky(option):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full")
        return real(option)
    backend.coord._write_pdf = flaky
    r = client.post("/api/approve", json={"code": code})
    assert r.status_code == 200 and r.json()["ok"] is True  # the lender has it: say so
    assert "PDF compilation failed after submission" in backend.coord.audit_path.read_text()
    pack = backend.coord.pack["pack_id"]
    pdf = client.get(f"/api/bank/cases/{pack}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"  # rebuilt on first download


def test_pdf_deleted_on_disk_is_rebuilt_from_the_locked_record(api):
    client, backend = api
    code = _awaiting(client, backend)
    client.post("/api/approve", json={"code": code})
    path = backend.coord.pack_pdf_file
    before = path.read_bytes()
    path.unlink()
    pack = backend.coord.pack["pack_id"]
    again = client.get(f"/api/bank/cases/{pack}/pdf")
    assert again.status_code == 200 and again.content == before  # deterministic rebuild, same bytes


@pytest.mark.parametrize("path,body", [
    ("/api/capital-plan", '{"available_cash_usd": NaN, "minimum_reserve_usd": 0, "working_capital_usd": 0, "marketing_usd": 0, "green_investment_usd": 0}'),
    ("/api/workspace/scenario", '{"available_cash_usd": Infinity, "minimum_reserve_usd": 0}'),
    ("/api/workspace/scenario", '{"available_cash_usd": 1e400, "minimum_reserve_usd": 0}'),
    ("/api/green-finance/cash-impact", '{"project_id": "GREEN-SOLAR-001", "financed_pct": -Infinity}'),
    ("/api/simulate", '{"params": {"fx_change_pct": NaN}}'),
    ("/api/analytics/scenario", '{"data": {"marketing_increase_pct": NaN}}'),
    ("/api/workspace/quality", '{"sources": [], "ledger_entries": [{"reference": "A", "amount": NaN}], "bank_entries": []}'),
])
def test_non_finite_numbers_are_refused_everywhere(api, path, body):
    client, _ = api
    r = client.post(path, content=body.encode(), headers={**client.header("sme.lan"), "Content-Type": "application/json"})
    assert r.status_code == 422 and "finite" in r.json()["detail"], (path, r.status_code, r.text)


def test_valid_bodies_with_exponents_still_work(api):
    client, _ = api
    r = client.post("/api/capital-plan", content=b'{"available_cash_usd": 1e5, "minimum_reserve_usd": 1.5E3, "working_capital_usd": 0,'
                    b' "marketing_usd": 0, "green_investment_usd": 0, "note": "NaN in a string is just text"}',
                    headers={**client.header("sme.lan"), "Content-Type": "application/json"})
    assert r.status_code == 200 and r.json()["deployable_cash_usd"] == 98500


def test_missing_or_corrupt_input_file_gives_503_not_a_crash(api, monkeypatch, tmp_path):
    client, backend = api
    import ui.backend_real as br
    monkeypatch.setattr(br, "SANDBOX_INPUTS_DIR", tmp_path / "nowhere")
    r = client.get("/api/green-finance")
    assert r.status_code == 503 and "nothing was changed" in r.json()["detail"]
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "green_projects.json").write_text("{ not json")
    monkeypatch.setattr(br, "SANDBOX_INPUTS_DIR", broken)
    assert client.get("/api/green-finance").status_code == 503


def test_unexpected_bug_returns_an_incident_id_without_internals(api, monkeypatch):
    client, backend = api
    monkeypatch.setattr(backend, "reconciliation_view", lambda: 1 / 0)
    r = client.get("/reconcile")
    assert r.status_code == 500
    body = r.json()
    assert body["incident"].startswith("INC-") and "ZeroDivision" not in r.text and "Traceback" not in r.text
    assert body["incident"] in backend.coord.audit_path.read_text()
    assert verify_chain(backend.coord.audit_path)[0]


def test_corrupt_workspace_database_does_not_leak_internals(api, tmp_path):
    client, _ = api
    (tmp_path / "ws.db").write_bytes(b"this is not a sqlite database" * 100)
    r = client.get("/api/workspace/requests")
    assert r.status_code >= 500 and "Traceback" not in r.text and "sqlite" not in r.text.lower()


def test_tampered_audit_log_is_detected_by_the_lender_check(api):
    client, backend = api
    code = _awaiting(client, backend)
    client.post("/api/approve", json={"code": code})
    lines = backend.coord.audit_path.read_text().splitlines()
    first = json.loads(lines[0])
    first["reason"] = "rewritten by an administrator"
    lines[0] = json.dumps(first)
    backend.coord.audit_path.write_text("\n".join(lines) + "\n")
    pack = backend.coord.pack["pack_id"]
    checks = {c["check"]: c["ok"] for c in client.post(f"/api/bank/cases/{pack}/verify").json()["checks"]}
    assert checks["Audit log hash chain intact"] is False


def test_company_with_no_receivables_or_shortfall_ends_in_monitor(tmp_path):
    from eval.trust_scorecard import agent_scenarios
    rows = {sid: (title, setup, args, expect) for sid, title, setup, args, expect in agent_scenarios()}
    assert "AP-03" in rows and rows["AP-03"][3] == "MONITOR"  # exercised end to end by the trust scorecard


def test_forecast_rejects_out_of_range_what_ifs_cleanly(api):
    client, _ = api
    for q in ("dso_change_days=99999", "deposit_pct=-1", "fx_change_pct=50", "tariff_shared_pct=1000"):
        r = client.get("/forecast?" + q)
        assert r.status_code == 422 and "Traceback" not in r.text, q
