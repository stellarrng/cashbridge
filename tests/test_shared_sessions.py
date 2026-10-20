"""Sign-out, sign-out-everywhere and the sign-in throttle are shared by every process using the same session store."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from security.auth import AuthError, MemorySessionState, SessionManager, SqliteSessionState, session_state

SECRET = "s" * 40
ROOT = Path(__file__).resolve().parent.parent


def manager(tmp_path, clock=None):
    env = {"CASHBRIDGE_SESSION_SECRET": SECRET, "CASHBRIDGE_SESSION_STORE": str(tmp_path / "sessions.sqlite3")}
    return SessionManager(env=env, **({"clock": clock} if clock else {}))


def test_store_selection():
    assert isinstance(session_state({}), MemorySessionState)
    assert isinstance(session_state({"CASHBRIDGE_SESSION_STORE": "memory"}), MemorySessionState)


def test_production_defaults_to_a_shared_file(tmp_path):
    st = session_state({"CASHBRIDGE_ENV": "production", "CASHBRIDGE_RUNTIME_DIR": str(tmp_path)})
    assert isinstance(st, SqliteSessionState) and st.shared and Path(st.path).parent == tmp_path


def test_sign_out_on_one_worker_is_enforced_on_another(tmp_path):
    a, b = manager(tmp_path), manager(tmp_path)  # two workers, same store
    token = a.demo_login("sme.lan")["token"]
    principal = b.verify(token)
    a.logout(principal)
    with pytest.raises(AuthError, match="signed out"):
        b.verify(token)


def test_sign_out_everywhere_ends_older_sessions_only(tmp_path):
    t = {"now": 1_800_000_000.0}
    a, b = manager(tmp_path, lambda: t["now"]), manager(tmp_path, lambda: t["now"])
    phone, laptop, other = a.demo_login("sme.lan")["token"], b.demo_login("sme.lan")["token"], a.demo_login("sme.minh")["token"]
    t["now"] += 5
    a.logout_everywhere(a.verify(phone))
    for tok in (phone, laptop):
        with pytest.raises(AuthError, match="all devices"):
            b.verify(tok)
    assert b.verify(other).user_id == "sme.minh"  # another user is untouched
    t["now"] += 2
    assert b.verify(a.demo_login("sme.lan")["token"]).user_id == "sme.lan"  # a fresh sign-in works


def test_throttle_counts_failures_from_every_worker(tmp_path):
    a, b = manager(tmp_path), manager(tmp_path)
    for i in range(8):
        with pytest.raises(AuthError):
            (a if i % 2 else b).login("sme.lan", "wrong", client_key="ip:1")
    with pytest.raises(AuthError) as err:
        a.login("sme.lan", "lan-demo-2026", client_key="ip:1")
    assert err.value.status == 429


def test_revocation_crosses_real_os_processes(tmp_path):
    a = manager(tmp_path)
    token = a.demo_login("sme.lan")["token"]
    script = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {str(ROOT)!r})
        from security.auth import SessionManager
        m = SessionManager(env={{"CASHBRIDGE_SESSION_SECRET": {SECRET!r}, "CASHBRIDGE_SESSION_STORE": {str(tmp_path / 'sessions.sqlite3')!r}}})
        m.logout(m.verify({token!r}))
    """)
    subprocess.run([sys.executable, "-c", script], check=True, cwd=ROOT, timeout=60)
    with pytest.raises(AuthError, match="signed out"):
        a.verify(token)


def test_logout_all_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import create_app
    from security import auth
    from ui.backend_real import RealBackend
    monkeypatch.setenv("CASHBRIDGE_RUNTIME_DIR", str(tmp_path / "rt"))
    auth.reset_sessions_for_tests(manager(tmp_path))
    try:
        client = TestClient(create_app(lambda: RealBackend(runtime_dir=tmp_path / "runtime"), dist_dir=tmp_path / "no-ui"))
        tok = client.post("/api/auth/demo-login", json={"user_id": "bank.lihua"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        r = client.post("/api/auth/logout-all", headers=h)
        assert r.status_code == 200 and r.json()["shared_across_processes"] is True
        assert client.get("/api/auth/me", headers=h).status_code == 401
    finally:
        auth.reset_sessions_for_tests(None)
