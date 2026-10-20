"""Server-side sign-in, signed sessions and role-based access control (RBAC).

Two portals share one evidence trail:

    SME portal   sme_accountant  prepares (runs the Autopilot, chooses an option, drafts the pack)
                 sme_director    approves (action-bound OTP), rejects, never prepares
    Bank portal  bank_reviewer   reads only what the SME submitted, verifies hashes, records a decision

Segregation of duties is enforced twice: by the permission matrix (a director has no
``sme:prepare``, an accountant has no ``sme:approve``) and by the coordinator, which refuses an
approval from the user who prepared the pack. Every check happens on the server; hiding a button
in the browser grants nothing.

Sessions are stateless HMAC-SHA256 tokens (``base64url(claims).base64url(sig)``) so they verify on
any serverless instance that shares ``CASHBRIDGE_SESSION_SECRET``. Sign-out, "sign out everywhere" and
the failed-sign-in throttle live in a session-state store (v9): SQLite shared by every worker process
on the host (``CASHBRIDGE_SESSION_STORE=/path/sessions.sqlite3``; the default in PRODUCTION is the
runtime folder), or process memory (``memory``; the DEMO default). On serverless hosts without a shared
disk, memory state is per instance: a sign-out there is enforced only where it happened, which is why
production on such hosts needs an external store (not shipped here). In DEMO mode a random secret is generated when none is configured (sessions then
end when the process restarts). PRODUCTION mode refuses to start without a strong secret.

SYNTHETIC MVP control, not a production identity provider (no MFA enrolment, no OIDC, no lockout store).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional

from fastapi import Depends, Header, HTTPException, Request

from config import runtime_mode

SESSION_TTL_SECONDS = 8 * 3600
TOKEN_VERSION = 1
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 8            # per client address
LOGIN_MAX_FAILURES_PER_ACCOUNT = 20  # per account, across all addresses (slows distributed guessing)

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "sme_accountant": frozenset({"sme:read", "sme:analyze", "sme:prepare", "demo:reset"}),
    "sme_director": frozenset({"sme:read", "sme:analyze", "sme:approve", "demo:reset"}),
    "bank_reviewer": frozenset({"bank:read", "bank:decide"}),
}
ROLE_PORTAL = {"sme_accountant": "sme", "sme_director": "sme", "bank_reviewer": "bank"}
ROLE_LABEL = {
    "sme_accountant": "Chief accountant (preparer)",
    "sme_director": "Director (approver)",
    "bank_reviewer": "Credit reviewer",
}

SME_TENANT = "TEN-BDT-001"
LENDER_TENANT = "LENDER-PF-01"

# Demo personas. Passcodes are public on purpose (they are printed on the sign-in screen) and only
# work in DEMO mode. All people and organisations are SYNTHETIC.
DEMO_ACCOUNTS: List[Dict[str, str]] = [
    # SME: Binh Duong Timberworks. Two preparers and two approvers so segregation of duties can be shown
    # with any pair. Names mix Vietnamese, English and Chinese on purpose (export SME, foreign lender).
    {"user_id": "sme.lan", "name": "Nguyễn Thị Lan", "role": "sme_accountant", "initials": "NL",
     "org": "Binh Duong Timberworks (SYNTHETIC)", "tenant_id": SME_TENANT, "passcode": "lan-demo-2026"},
    {"user_id": "sme.olivia", "name": "Olivia Bennett", "role": "sme_accountant", "initials": "OB",
     "org": "Binh Duong Timberworks (SYNTHETIC)", "tenant_id": SME_TENANT, "passcode": "olivia-demo-2026"},
    {"user_id": "sme.minh", "name": "Trần Văn Minh", "role": "sme_director", "initials": "TM",
     "org": "Binh Duong Timberworks (SYNTHETIC)", "tenant_id": SME_TENANT, "passcode": "minh-demo-2026"},
    {"user_id": "sme.chen", "name": "Chen Wei 陈伟", "role": "sme_director", "initials": "CW",
     "org": "Binh Duong Timberworks (SYNTHETIC)", "tenant_id": SME_TENANT, "passcode": "chen-demo-2026"},
    # Lender: Partner Factor (MOCK).
    {"user_id": "bank.lihua", "name": "Li Hua 李华", "role": "bank_reviewer", "initials": "LH",
     "org": "Partner Factor (MOCK lender)", "tenant_id": LENDER_TENANT, "passcode": "lihua-demo-2026"},
    {"user_id": "bank.daniel", "name": "Daniel Hughes", "role": "bank_reviewer", "initials": "DH",
     "org": "Partner Factor (MOCK lender)", "tenant_id": LENDER_TENANT, "passcode": "daniel-demo-2026"},
]


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str
    role: str
    org: str
    tenant_id: str
    session_id: str
    expires_at: int

    @property
    def portal(self) -> str:
        return ROLE_PORTAL[self.role]

    @property
    def permissions(self) -> FrozenSet[str]:
        return ROLE_PERMISSIONS[self.role]

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def public(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("session_id")
        data.update(portal=self.portal, role_label=ROLE_LABEL[self.role], permissions=sorted(self.permissions))
        return data


# ----------------------------------------------------------------------------- passwords
def hash_passcode(passcode: str, salt: Optional[str] = None, iterations: int = 200_000) -> str:
    """PBKDF2-SHA256 hash string ``pbkdf2_sha256$iterations$salt$hex``."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", passcode.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_passcode(passcode: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", passcode.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


# ----------------------------------------------------------------------------- tokens
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class AuthError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class MemorySessionState:
    """Per-process session state (DEMO default)."""

    shared = False

    def __init__(self) -> None:
        self._revoked: Dict[str, int] = {}
        self._cutoff: Dict[str, float] = {}
        self._failures: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def revoke(self, sid: str, exp: int) -> None:
        with self._lock:
            self._revoked[sid] = exp

    def is_revoked(self, sid: str) -> bool:
        return sid in self._revoked

    def revoke_user(self, user_id: str, before: float) -> None:
        with self._lock:
            self._cutoff[user_id] = before

    def cutoff(self, user_id: str) -> float:
        return self._cutoff.get(user_id, 0.0)

    def failures(self, key: str, since: float) -> int:
        with self._lock:
            recent = [t for t in self._failures.get(key, []) if t > since]
            self._failures[key] = recent
            return len(recent)

    def fail(self, key: str, at: float) -> None:
        with self._lock:
            self._failures.setdefault(key, []).append(at)


class SqliteSessionState:
    """Session state shared by every process that opens the same file (uvicorn/gunicorn workers on one host)."""

    shared = True

    def __init__(self, path: str | Path) -> None:
        import sqlite3
        self._sqlite3 = sqlite3
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript("""PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS revoked (sid TEXT PRIMARY KEY, exp INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS user_cutoff (user_id TEXT PRIMARY KEY, before REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS failures (key TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS failures_key ON failures(key, at);""")

    def _con(self):
        con = self._sqlite3.connect(self.path, timeout=10)
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def revoke(self, sid: str, exp: int) -> None:
        with self._con() as con:
            con.execute("INSERT OR IGNORE INTO revoked VALUES (?,?)", (sid, exp))
            con.execute("DELETE FROM revoked WHERE exp < ?", (int(time.time()) - 60,))  # expired tokens fail anyway

    def is_revoked(self, sid: str) -> bool:
        with self._con() as con:
            return con.execute("SELECT 1 FROM revoked WHERE sid=?", (sid,)).fetchone() is not None

    def revoke_user(self, user_id: str, before: float) -> None:
        with self._con() as con:
            con.execute("INSERT INTO user_cutoff VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET before=MAX(before, excluded.before)",
                        (user_id, before))

    def cutoff(self, user_id: str) -> float:
        with self._con() as con:
            row = con.execute("SELECT before FROM user_cutoff WHERE user_id=?", (user_id,)).fetchone()
        return float(row[0]) if row else 0.0

    def failures(self, key: str, since: float) -> int:
        with self._con() as con:
            con.execute("DELETE FROM failures WHERE at <= ?", (since,))
            return int(con.execute("SELECT COUNT(*) FROM failures WHERE key=? AND at > ?", (key, since)).fetchone()[0])

    def fail(self, key: str, at: float) -> None:
        with self._con() as con:
            con.execute("INSERT INTO failures VALUES (?,?)", (key, at))


def session_state(source: Mapping[str, str]) -> Any:
    configured = source.get("CASHBRIDGE_SESSION_STORE", "").strip()
    if configured.lower() == "memory":
        return MemorySessionState()
    if configured:
        return SqliteSessionState(configured)
    if runtime_mode.is_production(source):
        return SqliteSessionState(runtime_mode.runtime_dir(Path(__file__).resolve().parents[1], source) / "sessions.sqlite3")
    return MemorySessionState()


class SessionManager:
    """Issues and verifies signed session tokens; tracks sign-outs and failed sign-ins."""

    def __init__(self, secret: Optional[str] = None, env: Optional[Mapping[str, str]] = None,
                 clock=time.time) -> None:
        source = os.environ if env is None else env
        configured = (secret if secret is not None else source.get("CASHBRIDGE_SESSION_SECRET", "")).strip()
        self.production = runtime_mode.is_production(source)
        if len(configured) < 32:
            if self.production:
                raise runtime_mode.ProductionConfigError("CASHBRIDGE_SESSION_SECRET must be at least 32 characters")
            deployment = source.get("VERCEL_DEPLOYMENT_ID", "") or source.get("VERCEL_URL", "")
            if runtime_mode.is_serverless(source) and deployment:
                # DEMO on serverless without a configured secret: every instance of this deployment must accept
                # the same tokens, so derive one per deployment. Synthetic data only; set a real secret anyway.
                configured = hashlib.sha256(f"cashbridge-demo|{deployment}".encode()).hexdigest()
            else:
                configured = secrets.token_urlsafe(48)
            self.ephemeral_secret = True
        else:
            self.ephemeral_secret = False
        self._key = configured.encode()
        self._clock = clock
        self.state = session_state(source)
        self._lock = threading.Lock()
        self.users = self._load_users(source)

    # -- accounts
    def _load_users(self, source: Mapping[str, str]) -> Dict[str, Dict[str, str]]:
        users: Dict[str, Dict[str, str]] = {}
        if not self.production:
            for account in DEMO_ACCOUNTS:
                users[account["user_id"]] = {**account, "passcode_hash": hash_passcode(account["passcode"], salt="demo", iterations=1000)}
        raw = source.get("CASHBRIDGE_USERS_JSON", "").strip()
        path = source.get("CASHBRIDGE_USERS_FILE", "").strip()
        if path:
            raw = Path(path).read_text(encoding="utf-8")
        if raw:
            for entry in json.loads(raw):
                if entry.get("role") not in ROLE_PERMISSIONS:
                    raise ValueError(f"unknown role for user {entry.get('user_id')}")
                if not str(entry.get("passcode_hash", "")).startswith("pbkdf2_sha256$"):
                    raise ValueError(f"user {entry.get('user_id')} needs a pbkdf2_sha256 passcode_hash")
                users[entry["user_id"]] = {k: str(v) for k, v in entry.items()}
        return users

    def demo_accounts(self) -> List[Dict[str, str]]:
        """Personas shown on the sign-in screen (DEMO mode only, passcodes included on purpose)."""
        if self.production:
            return []
        return [{**a, "portal": ROLE_PORTAL[a["role"]], "role_label": ROLE_LABEL[a["role"]]} for a in DEMO_ACCOUNTS]

    # -- sign-in
    def _throttle(self, key: str, limit: int = LOGIN_MAX_FAILURES) -> None:
        if self.state.failures(key, self._clock() - LOGIN_WINDOW_SECONDS) >= limit:
            raise AuthError(429, "Too many failed sign-in attempts; wait a few minutes")

    def _fail(self, key: str) -> None:
        self.state.fail(key, self._clock())

    def login(self, user_id: str, passcode: str, portal: Optional[str] = None, client_key: str = "-") -> Dict[str, Any]:
        account_key = "acct:" + (user_id or "").strip().lower()[:80]
        self._throttle(client_key)
        self._throttle(account_key, LOGIN_MAX_FAILURES_PER_ACCOUNT)
        user = self.users.get((user_id or "").strip().lower())
        if user is None or not verify_passcode(passcode or "", user["passcode_hash"]):
            self._fail(client_key)
            self._fail(account_key)
            raise AuthError(401, "Unknown account or wrong passcode")
        if portal and ROLE_PORTAL[user["role"]] != portal:
            raise AuthError(403, f"This account belongs to the {ROLE_PORTAL[user['role']].upper()} portal")
        return self.issue(user)

    def demo_login(self, user_id: str, portal: Optional[str] = None) -> Dict[str, Any]:
        if self.production:
            raise AuthError(404, "Demo sign-in is disabled in production mode")
        account = next((a for a in DEMO_ACCOUNTS if a["user_id"] == user_id), None)
        if account is None:
            raise AuthError(404, "Unknown demo account")
        if portal and ROLE_PORTAL[account["role"]] != portal:
            raise AuthError(403, f"This account belongs to the {ROLE_PORTAL[account['role']].upper()} portal")
        return self.issue(self.users[account["user_id"]])

    def issue(self, user: Mapping[str, str]) -> Dict[str, Any]:
        now = int(self._clock())
        claims = {"v": TOKEN_VERSION, "sub": user["user_id"], "name": user["name"], "role": user["role"],
                  "org": user.get("org", ""), "ten": user["tenant_id"], "sid": secrets.token_hex(12),
                  "iat": now, "exp": now + SESSION_TTL_SECONDS}
        body = _b64(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode())
        signature = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        principal = self._principal(claims)
        return {"token": f"{body}.{signature}", "expires_at": claims["exp"], "user": principal.public()}

    @staticmethod
    def _principal(claims: Mapping[str, Any]) -> Principal:
        return Principal(user_id=claims["sub"], name=claims["name"], role=claims["role"], org=claims.get("org", ""),
                         tenant_id=claims["ten"], session_id=claims["sid"], expires_at=int(claims["exp"]))

    def verify(self, token: str) -> Principal:
        try:
            body, signature = token.split(".")
            expected = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise AuthError(401, "Invalid session signature")
            claims = json.loads(_unb64(body))
        except AuthError:
            raise
        except Exception as error:  # malformed token of any kind
            raise AuthError(401, "Malformed session token") from error
        if claims.get("v") != TOKEN_VERSION or claims.get("role") not in ROLE_PERMISSIONS:
            raise AuthError(401, "Unsupported session token")
        if int(claims.get("exp", 0)) <= self._clock():
            raise AuthError(401, "Session expired; sign in again")
        if self.state.is_revoked(str(claims.get("sid"))):
            raise AuthError(401, "Session signed out")
        if int(claims.get("iat", 0)) < self.state.cutoff(str(claims.get("sub"))):  # iat is whole seconds, so a sign-in in
            # the same second as "sign out everywhere" is also ended (errs on the safe side; sign in again)
            raise AuthError(401, "Session ended by a sign-out on all devices")
        return self._principal(claims)

    def logout(self, principal: Principal) -> None:
        self.state.revoke(principal.session_id, principal.expires_at)

    def logout_everywhere(self, principal: Principal) -> None:
        """End every session of this user, on every worker sharing the store (e.g. lost device, role change)."""
        self.state.revoke_user(principal.user_id, float(self._clock()))


_manager: Optional[SessionManager] = None
_manager_lock = threading.Lock()


def get_sessions() -> SessionManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = SessionManager()
        return _manager


def reset_sessions_for_tests(manager: Optional[SessionManager] = None) -> None:
    global _manager
    with _manager_lock:
        _manager = manager


# ----------------------------------------------------------------------------- FastAPI dependencies
def bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return None


def current_principal(authorization: Optional[str] = Header(default=None)) -> Principal:
    token = bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        return get_sessions().verify(token)
    except AuthError as error:
        raise HTTPException(status_code=error.status, detail=error.detail, headers={"WWW-Authenticate": "Bearer"}) from error


def require(permission: str):
    """Dependency factory: the signed-in user must hold ``permission`` (else HTTP 403)."""

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.can(permission):
            raise HTTPException(status_code=403,
                                detail=f"{ROLE_LABEL[principal.role]} is not allowed to do this ({permission})")
        return principal

    dependency.__name__ = f"require_{permission.replace(':', '_')}"
    return dependency


def trust_proxy_headers(env: Optional[Mapping[str, str]] = None) -> bool:
    """Honour X-Forwarded-For only behind a known reverse proxy (otherwise any caller can rotate it
    to dodge the sign-in throttle). On by default on serverless hosts; set CASHBRIDGE_TRUST_PROXY=1
    on Render/Fly/nginx deployments that overwrite the header."""
    source = os.environ if env is None else env
    flag = source.get("CASHBRIDGE_TRUST_PROXY", "").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    return flag in ("1", "true", "yes") or runtime_mode.is_serverless(source)


def client_key(request: Request) -> str:
    direct = request.client.host if request.client else "-"
    if trust_proxy_headers():
        # The right-most entry is the one the trusted proxy appended; left entries are caller-controlled.
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        return hops[-1] if hops else direct
    return direct
