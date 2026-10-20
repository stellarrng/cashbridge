"""Black-box smoke + security checks against a running CashBridge deployment (T07).

    python scripts/deploy_smoke.py --base-url https://cashbridge.example.com --expect production \\
        [--user sme.lan --passcode ...] [--ca-bundle ca.pem] [--json reports/deploy_smoke.json]

Run it after every deploy. It only reads, plus one failed sign-in and harmless refused calls; it
never prepares, approves or funds anything. Exit code 0 means every check passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Dict, List, Optional

import httpx

PROTECTED = [("GET", "/api/snapshot"), ("GET", "/api/bank/inbox"), ("POST", "/api/prepare_pack"), ("POST", "/api/approve"),
             ("GET", "/api/workspace/requests"), ("GET", "/forecast"), ("GET", "/api/pack/pdf"), ("POST", "/packs"),
             ("GET", "/api/provenance"), ("GET", "/api/lender/quotes"), ("GET", "/api/bank/cases/PACK-X/provenance"),
             ("GET", "/api/workspace/cases/PACK-X/evidence/EVR-X/file"), ("POST", "/api/auth/logout-all")]
DEMO_ONLY = [("POST", "/api/reset_demo"), ("POST", "/api/tamper_demo"), ("GET", "/api/public/overview")]
LEAK_MARKERS = ("Traceback", 'File "/', "sqlite3.", "pydantic_core", "JBSWY3DPEHPK3PXP")


class Smoke:
    def __init__(self, base: str, expect: str, verify: Any = True, trust_env: bool = True) -> None:
        self.base = base.rstrip("/")
        self.expect = expect
        self.http = httpx.Client(base_url=self.base, verify=verify, timeout=15, follow_redirects=False,
                                 trust_env=trust_env and not base.startswith(("http://127.", "https://127.", "http://localhost", "https://localhost")))
        self.results: List[Dict[str, Any]] = []

    def check(self, name: str, fn: Callable[[], Optional[str]]) -> None:
        try:
            problem = fn()
        except Exception as error:  # a crash is a failed check
            problem = f"{type(error).__name__}: {error}"
        self.results.append({"check": name, "ok": problem is None, "detail": problem or ""})

    # ------------------------------------------------------------------ checks
    def health(self) -> Optional[str]:
        r = self.http.get("/api/health")
        if r.status_code != 200 or not r.json().get("ok"):
            return f"health returned {r.status_code}"
        if r.json().get("mode") != self.expect:
            return f"mode is {r.json().get('mode')!r}, expected {self.expect!r}"
        return None

    def https_and_hsts(self) -> Optional[str]:
        if not self.base.startswith("https://"):
            return "deployment is not served over HTTPS" if self.expect == "production" else None
        hsts = self.http.get("/api/health").headers.get("strict-transport-security", "")
        return None if "max-age=" in hsts else "Strict-Transport-Security header missing on HTTPS"

    def page_headers(self) -> Optional[str]:
        r = self.http.get("/")
        need = {"content-security-policy": "frame-ancestors 'none'", "x-frame-options": "DENY",
                "x-content-type-options": "nosniff", "referrer-policy": "no-referrer"}
        missing = [h for h, v in need.items() if v.lower() not in r.headers.get(h, "").lower()]
        if "unsafe-eval" in r.headers.get("content-security-policy", ""):
            missing.append("CSP allows unsafe-eval")
        return ", ".join(missing) or None

    def api_no_store(self) -> Optional[str]:
        r = self.http.get("/api/health")
        return None if "no-store" in r.headers.get("cache-control", "") else "API responses are cacheable"

    def auth_config(self) -> Optional[str]:
        cfg = self.http.get("/api/auth/config").json()
        if self.expect != "production":
            return None
        problems = []
        if cfg.get("demo_accounts"):
            problems.append("demo accounts listed")
        if cfg.get("otp_demo_secret"):
            problems.append("demo OTP secret exposed")
        if cfg.get("ephemeral_session_secret"):
            problems.append("session secret is ephemeral (sessions die on restart / differ per instance)")
        return ", ".join(problems) or None

    def demo_login_disabled(self) -> Optional[str]:
        if self.expect != "production":
            return None
        r = self.http.post("/api/auth/demo-login", json={"user_id": "sme.lan"})
        return None if r.status_code == 404 else f"demo login returned {r.status_code}"

    def demo_routes_disabled(self) -> Optional[str]:
        if self.expect != "production":
            return None
        bad = [f"{m} {p} -> {self.http.request(m, p, json={}).status_code}" for m, p in DEMO_ONLY]
        bad = [b for b in bad if not b.endswith((" 404", " 401"))]
        return "; ".join(bad) or None

    def api_docs_hidden(self) -> Optional[str]:
        if self.expect != "production":
            return None
        exposed = [p for p in ("/docs", "/openapi.json", "/redoc") if self.http.get(p).status_code == 200
                   and ("swagger" in self.http.get(p).text.lower() or '"openapi"' in self.http.get(p).text)]
        return ("exposed: " + ", ".join(exposed)) if exposed else None

    def protected_routes(self) -> Optional[str]:
        bad = []
        for method, path in PROTECTED:
            for header in ({}, {"Authorization": "Bearer forged.token"}, {"Authorization": "Bearer eyJ2IjoxfQ.AAAA"}):
                code = self.http.request(method, path, json={}, headers=header).status_code
                if code != 401:
                    bad.append(f"{method} {path} {header and 'forged' or 'anon'} -> {code}")
        return "; ".join(bad) or None

    def cors(self) -> Optional[str]:
        r = self.http.options("/api/snapshot", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET",
                                                        "Access-Control-Request-Headers": "authorization"})
        allowed = r.headers.get("access-control-allow-origin")
        if allowed in ("*", "https://evil.example"):
            return f"foreign origin allowed: {allowed}"
        if r.headers.get("access-control-allow-credentials") == "true" and allowed == "*":
            return "credentials with wildcard origin"
        return None

    def wrong_passcode(self) -> Optional[str]:
        r = self.http.post("/api/auth/login", json={"user_id": "smoke.nobody", "passcode": "definitely-wrong"})
        if r.status_code not in (401, 429):
            return f"bad sign-in returned {r.status_code}"
        return None if "token" not in r.text else "token in failed sign-in response"

    def no_internal_leaks(self) -> Optional[str]:
        probes = [self.http.post("/api/auth/login", content=b"{", headers={"Content-Type": "application/json"}),
                  self.http.get("/api/does-not-exist"), self.http.get("/api/bank/cases/%27%20OR%201%3D1"),
                  self.http.post("/api/auth/login", json={"user_id": "x" * 500, "passcode": "y"})]
        leaks = [f"{p.request.url.path} {m}" for p in probes for m in LEAK_MARKERS if m in p.text]
        fivexx = [f"{p.request.url.path} -> {p.status_code}" for p in probes if p.status_code >= 500]
        return "; ".join(leaks + fivexx) or None

    def body_limit(self) -> Optional[str]:
        r = self.http.post("/api/auth/login", content=b" " * 7_000_001, headers={"Content-Type": "application/json"})
        return None if r.status_code == 413 else f"oversized body returned {r.status_code}"

    def static_assets(self) -> Optional[str]:
        # The built app uses hashed file names (Vite), so read the script the served page actually loads.
        import re as _re
        page = self.http.get("/app").text
        found = _re.search(r'src="(/assets/[^"]+\.js)"', page)
        if not found:
            return "the app page loads no /assets/*.js script"
        r = self.http.get(found.group(1))
        if r.status_code != 200:
            return f"{found.group(1)} returned {r.status_code}"
        return None if r.headers.get("x-content-type-options") == "nosniff" else "assets lack nosniff"

    def traversal(self) -> Optional[str]:
        for path in ("/..%2f..%2fapi%2fmain.py", "/assets/..%2f..%2f..%2fMakefile", "/%2e%2e/%2e%2e/Dockerfile"):
            text = self.http.get(path).text
            if "create_app" in text or "PYTEST" in text or "FROM python" in text:
                return f"source file served at {path}"
        return None

    def webhook_needs_signature(self) -> Optional[str]:
        body = b'{"event_id":"smoke","quote_id":"Q","status":"funded"}'
        codes = [self.http.post("/api/lender/webhook", content=body, headers=h).status_code
                 for h in ({}, {"X-Lender-Signature": "t=1,v1=00"}, {"X-Lender-Signature": "garbage"})]
        return None if all(c == 401 for c in codes) else f"unsigned/forged webhook returned {codes}"

    def signed_in(self, user: str, passcode: str) -> Optional[str]:
        r = self.http.post("/api/auth/login", json={"user_id": user, "passcode": passcode})
        if r.status_code != 200:
            return f"sign-in failed: {r.status_code}"
        h = {"Authorization": "Bearer " + r.json()["token"]}
        problems = []
        if r.json()["user"]["portal"] == "sme":
            gate = self.http.get("/api/workspace/data-gate", headers=h).json()
            if self.expect == "production" and not gate.get("enabled"):
                problems.append("data gate is OFF in production")
            if self.http.get("/api/bank/inbox", headers=h).status_code != 403:
                problems.append("SME user can open the bank inbox")
        else:
            if self.http.get("/api/snapshot", headers=h).status_code != 403:
                problems.append("bank user can open the SME snapshot")
        self.http.post("/api/auth/logout", headers=h)
        if self.http.get("/api/auth/me", headers=h).status_code != 401:
            problems.append("token still valid after sign-out")
        return "; ".join(problems) or None

    def run(self, user: Optional[str] = None, passcode: Optional[str] = None) -> List[Dict[str, Any]]:
        for name in ("health", "https_and_hsts", "page_headers", "api_no_store", "auth_config", "demo_login_disabled",
                     "demo_routes_disabled", "api_docs_hidden", "protected_routes", "cors", "wrong_passcode",
                     "no_internal_leaks", "body_limit", "static_assets", "traversal", "webhook_needs_signature"):
            self.check(name, getattr(self, name))
        if user and passcode:
            self.check("signed_in_role_boundaries", lambda: self.signed_in(user, passcode))
        return self.results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expect", choices=("demo", "production"), default="production")
    parser.add_argument("--user")
    parser.add_argument("--passcode")
    parser.add_argument("--ca-bundle", help="PEM file to trust (for a private or local TLS certificate)")
    parser.add_argument("--json", help="write results to this file")
    args = parser.parse_args(argv)
    smoke = Smoke(args.base_url, args.expect, verify=args.ca_bundle or True)
    results = smoke.run(args.user, args.passcode)
    for r in results:
        print(("PASS " if r["ok"] else "FAIL ") + r["check"] + (f"  ({r['detail']})" if r["detail"] else ""))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"base_url": args.base_url, "expect": args.expect, "results": results}, fh, indent=2)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
