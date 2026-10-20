"""T07: deployment smoke checks run in-process (demo and production app), plus evidence archiving."""

import json

from fastapi.testclient import TestClient

from api.main import DIST_DIR, create_app
from scripts.deploy_smoke import Smoke
from scripts.run_demo_story import StoryClock
from security import auth
from ui.backend_real import RealBackend


def _smoke(app, expect):
    smoke = Smoke("http://testserver", expect)
    smoke.http = TestClient(app, raise_server_exceptions=False)
    return smoke


def test_demo_app_passes_the_smoke_checks(tmp_path):
    backend = RealBackend(runtime_dir=tmp_path / "rt", clock=StoryClock())
    results = _smoke(create_app(lambda: backend, dist_dir=DIST_DIR), "demo").run()
    assert all(r["ok"] for r in results), [r for r in results if not r["ok"]]


def test_production_app_passes_the_smoke_checks(tmp_path, monkeypatch):
    users = [{"user_id": "sme.lan", "name": "Lan", "role": "sme_accountant", "org": "x", "tenant_id": auth.SME_TENANT,
              "passcode_hash": auth.hash_passcode("long-passcode-for-tests")}]
    for k, v in {"CASHBRIDGE_ENV": "production", "OTP_SECRET": "KRSXG5CTMVRXEZLUKN2XAZLSKNSWG4TFOQ",
                 "CASHBRIDGE_SESSION_SECRET": "s" * 40, "CASHBRIDGE_VAULT_KEY": "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s=", "CASHBRIDGE_USERS_JSON": json.dumps(users)}.items():
        monkeypatch.setenv(k, v)
    auth.reset_sessions_for_tests(auth.SessionManager())
    try:
        backend = RealBackend(runtime_dir=tmp_path / "rt", clock=StoryClock())
        smoke = _smoke(create_app(lambda: backend, dist_dir=DIST_DIR), "production")
        results = smoke.run("sme.lan", "long-passcode-for-tests")
        failed = [r for r in results if not r["ok"] and r["check"] != "https_and_hsts"]  # in-process test has no TLS
        assert failed == [], failed
        assert smoke.http.get("/api/health", headers={"X-Forwarded-Proto": "https"}).headers["strict-transport-security"]
    finally:
        auth.reset_sessions_for_tests(None)


def test_restart_archives_evidence_with_intact_chain(tmp_path):
    first = RealBackend(runtime_dir=tmp_path / "rt", clock=StoryClock())
    first.prepare_pack  # noqa: B018 - the Monday run already wrote audit lines
    lines_before = first.coord.audit_path.read_text().count("\n")
    RealBackend(runtime_dir=tmp_path / "rt", clock=StoryClock())  # simulated restart
    manifests = sorted((tmp_path / "rt" / "evidence" / "archive").glob("*/MANIFEST.json"))
    assert manifests
    newest = json.loads(manifests[-1].read_text())
    assert newest["audit_chain"]["ok"] is True and newest["audit_chain"]["lines"] >= lines_before
