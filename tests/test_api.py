"""FastAPI app serves the UI contract (Step 4.1)."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from tests.authed import RoleClient
from scripts.run_demo_story import StoryClock
from ui.backend_real import RealBackend

NO_PARAMS = {"dso_change_days": 0, "deposit_pct": 30, "tariff_shared_pct": 0, "fx_change_pct": 0}


@pytest.fixture
def backend(tmp_path):
    return RealBackend(runtime_dir=tmp_path, clock=StoryClock())


@pytest.fixture
def client(backend, tmp_path):
    return RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-dist"))


def test_snapshot_route_returns_the_contract_snapshot(client):
    snap = client.get("/api/snapshot").json()
    assert snap["kpis"]["first_shortfall_week"] == 7 and snap["meta"]["synthetic"] is True


def test_simulate_route(client):
    out = client.post("/api/simulate", json={"params": {**NO_PARAMS, "dso_change_days": 15}}).json()
    assert set(out) == {"forecast", "kpis", "delta"}
    assert out["delta"]["min_closing_after_usd"] < out["delta"]["min_closing_before_usd"]


def test_simulate_rejects_out_of_range_params_with_422(client):
    response = client.post("/api/simulate", json={"params": {**NO_PARAMS, "dso_change_days": 99}})
    assert response.status_code == 422 and "invalid scenario" in response.json()["detail"]


def test_missing_body_is_a_422(client):
    assert client.post("/api/approve", json={}).status_code == 422


def test_full_click_through_over_http(client, backend):
    assert client.post("/api/choose_option", json={"option_id": "factoring_inv1030"}).json()["selected_option_id"] == "factoring_inv1030"
    pack = client.post("/api/prepare_pack").json()["pack"]
    assert pack["status"] == "AWAITING_APPROVAL"
    challenge = client.post("/api/request_otp").json()
    assert challenge["action_hash"] == pack["action_hash"]
    assert client.post("/api/tamper_draft").json()["ok"] is False
    wrong = "000000" if backend.coord.otp.current_code() != "000000" else "111111"
    bad = client.post("/api/approve", json={"code": wrong}).json()
    assert bad["ok"] is False and bad["error"] == "invalid_code"
    good = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()
    assert good["ok"] and good["snapshot"]["meta"]["case_state"] == "SUBMITTED"
    assert client.post("/api/retry_double_financing").json()["error"] == "DoubleFinancingBlocked"
    assert client.post("/api/verify_chain").json()["ok"] is True
    broken = client.post("/api/tamper_demo").json()
    assert broken["ok"] is False and broken["note"] == "temporary copy only"


def test_approving_without_asking_for_an_otp_is_a_409(client):
    response = client.post("/api/approve", json={"code": "123456"})
    assert response.status_code == 409 and "request approval" in response.json()["detail"]


def test_a_refused_option_is_reported_in_meta(client):
    snap = client.post("/api/choose_option", json={"option_id": "overdraft"}).json()
    assert "not available" in snap["meta"]["last_error"]


def test_ask_cfo_and_reset(client):
    reply = client.post("/api/ask_cfo", json={"text": "When will I run out of cash?"}).json()
    assert reply["citations"] and reply["role"] == "assistant"
    client.post("/api/choose_option", json={"option_id": "bridge_loan"})
    assert client.post("/api/reset_demo").json()["selected_option_id"] is None


def test_unknown_routes_and_methods(client):
    assert client.post("/api/wire_money").status_code in (404, 405)
    assert client.get("/api/approve").status_code == 405


def test_openapi_docs_are_available(client):
    assert client.get("/docs").status_code == 200
    assert "/api/snapshot" in client.get("/openapi.json").json()["paths"]


def test_without_a_built_ui_the_root_explains_how_to_build_it(client):
    assert "frontend/dist" in client.get("/").json()["ui"]


def test_built_bundle_is_served_with_spa_fallback(backend, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "main.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    client = RoleClient(create_app(lambda: backend, dist_dir=dist))
    assert client.get("/").text == "<html>app</html>"
    assert client.get("/assets/main.js").text == "console.log(1)"
    assert client.get("/some/route").text == "<html>app</html>"  # client-side routing
    assert client.get("/../secret.txt").text == "<html>app</html>"  # no path traversal out of dist
    assert client.get("/api/nothing").status_code == 404
