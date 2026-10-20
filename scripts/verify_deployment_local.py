"""T07 local deployment verification: PRODUCTION mode behind real TLS, restart, log scan.

    python scripts/verify_deployment_local.py      # writes reports/deploy_verification.{md,json}

What it does (all on 127.0.0.1, nothing leaves the machine):
1. creates a throw-away CA and a server certificate, private secrets and three hashed user accounts;
2. starts ``uvicorn api.main:app`` in PRODUCTION mode with HTTPS;
3. runs scripts/deploy_smoke.py against it (headers, HSTS, CORS, demo shortcuts off, docs hidden,
   401 on every protected route, no stack traces, body limit, path traversal, role boundaries);
4. creates a planning request, RESTARTS the server and checks the session, the request and the
   archived audit evidence (with an intact hash chain) all survived;
5. scans the server log for secrets, passcodes, session tokens and personal data.

This verifies the application's own deployment behaviour. It is not a cloud deployment review,
a penetration test or a check of the hosting provider's TLS/WAF configuration.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from scripts.deploy_smoke import Smoke  # noqa: E402
from security.auth import SME_TENANT, LENDER_TENANT, hash_passcode  # noqa: E402

REPORT_DIR = ROOT / "reports"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_tls(tmp: Path) -> Dict[str, Path]:
    def run(*args: str) -> None:
        subprocess.run(args, check=True, capture_output=True)
    ca_key, ca_crt, key, csr, crt, ext = (tmp / n for n in ("ca.key", "ca.pem", "server.key", "server.csr", "server.pem", "ext.cnf"))
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(ca_key), "-out", str(ca_crt),
        "-days", "2", "-subj", "/CN=CashBridge local test CA",
        "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        "-addext", "subjectKeyIdentifier=hash")
    run("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(csr), "-subj", "/CN=localhost")
    ext.write_text("subjectAltName=DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
                   "extendedKeyUsage=serverAuth\nauthorityKeyIdentifier=keyid\nsubjectKeyIdentifier=hash\n")
    run("openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(crt), "-days", "2", "-extfile", str(ext))
    return {"ca": ca_crt, "key": key, "cert": crt}


class Server:
    def __init__(self, env: Dict[str, str], tls: Dict[str, Path], log: Path, workers: int = 1) -> None:
        self.env, self.tls, self.log, self.workers = env, tls, log, workers
        self.port = free_port()
        self.proc: Any = None

    @property
    def url(self) -> str:
        return f"https://127.0.0.1:{self.port}"

    def start(self) -> float:
        started = time.perf_counter()
        fh = open(self.log, "ab")
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(self.port),
                                      "--ssl-keyfile", str(self.tls["key"]), "--ssl-certfile", str(self.tls["cert"])]
                                     + (["--workers", str(self.workers)] if self.workers > 1 else []),
                                     cwd=ROOT, env=self.env, stdout=fh, stderr=subprocess.STDOUT)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("server exited during start-up; see " + str(self.log))
            try:
                if httpx.get(self.url + "/api/health", verify=str(self.tls["ca"]), timeout=2, trust_env=False).status_code == 200:
                    return round(time.perf_counter() - started, 2)
            except httpx.HTTPError:
                time.sleep(0.3)
        raise RuntimeError("server did not become healthy in 60 s")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def main() -> int:
    results: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        tls = make_tls(tmp)
        passcodes = {u: secrets.token_urlsafe(18) for u in ("sme.lan", "sme.minh", "bank.lihua")}
        users = [
            {"user_id": "sme.lan", "name": "Lan Nguyen", "role": "sme_accountant", "org": "Test SME", "tenant_id": SME_TENANT},
            {"user_id": "sme.minh", "name": "Minh Tran", "role": "sme_director", "org": "Test SME", "tenant_id": SME_TENANT},
            {"user_id": "bank.lihua", "name": "Li Hua", "role": "bank_reviewer", "org": "Test Lender", "tenant_id": LENDER_TENANT},
        ]
        for u in users:
            u["passcode_hash"] = hash_passcode(passcodes[u["user_id"]])
        (tmp / "users.json").write_text(json.dumps(users))
        otp_secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
        session_secret = secrets.token_urlsafe(48)
        runtime = tmp / "runtime"
        env = {**os.environ, "CASHBRIDGE_ENV": "production", "OTP_SECRET": otp_secret, "CASHBRIDGE_SESSION_SECRET": session_secret,
               "CASHBRIDGE_VAULT_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
               "CASHBRIDGE_USERS_FILE": str(tmp / "users.json"), "CASHBRIDGE_RUNTIME_DIR": str(runtime),
               "CASHBRIDGE_ALLOWED_ORIGINS": "", "PYTHONDONTWRITEBYTECODE": "1"}
        for k in ("CASHBRIDGE_WORKSPACE_DB", "CASHBRIDGE_AUTOMATION_DB", "CASHBRIDGE_REQUIRE_DATA_GATE", "VERCEL", "AWS_LAMBDA_FUNCTION_NAME"):
            env.pop(k, None)
        log = tmp / "server.log"
        server = Server(env, tls, log)

        def record(name: str, ok: bool, detail: str = "") -> None:
            results.append({"check": name, "ok": bool(ok), "detail": detail})

        # 0. production refuses to start with demo shortcuts
        bad = subprocess.run([sys.executable, "-c", "import api.main"], cwd=ROOT, capture_output=True, text=True,
                             env={**env, "OTP_SECRET": "JBSWY3DPEHPK3PXP"})
        record("Production refuses to start with the public demo OTP secret", bad.returncode != 0 and "Refusing to start" in bad.stderr)

        try:
            boot = server.start()
            record("Starts in PRODUCTION mode over HTTPS", True, f"healthy after {boot} s on {server.url}")
            smoke = Smoke(server.url, "production", verify=str(tls["ca"]))
            for r in smoke.run("sme.lan", passcodes["sme.lan"]):
                record("smoke: " + r["check"], r["ok"], r["detail"])
            bank = Smoke(server.url, "production", verify=str(tls["ca"]))
            bank.check("bank role boundaries", lambda: bank.signed_in("bank.lihua", passcodes["bank.lihua"]))
            record("smoke: bank role boundaries", bank.results[0]["ok"], bank.results[0]["detail"])

            # 4. state that must survive a restart
            http = httpx.Client(base_url=server.url, verify=str(tls["ca"]), timeout=15, trust_env=False)
            tok = http.post("/api/auth/login", json={"user_id": "sme.lan", "passcode": passcodes["sme.lan"]}).json()["token"]
            h = {"Authorization": "Bearer " + tok}
            created = http.post("/api/workspace/requests", headers=h,
                                json={"field": "marketing_usd", "proposed_value": "12000", "reason": "Restart persistence check"})
            record("Planning request created before restart", created.status_code == 200, f"HTTP {created.status_code}")
            gate = http.post("/packs", headers=h, json={"option_id": "factoring_inv1030"})
            record("Financing blocked in production without verified data (gate on by default)", gate.status_code == 409,
                   gate.json().get("detail", "")[:120])
            server.stop()
            server.port = free_port()
            boot2 = server.start()
            http = httpx.Client(base_url=server.url, verify=str(tls["ca"]), timeout=15, trust_env=False)
            me = http.get("/api/auth/me", headers=h)
            record("Session survives restart (shared signing secret)", me.status_code == 200, f"restart took {boot2} s")
            reqs = http.get("/api/workspace/requests", headers=h).json().get("requests", [])
            record("Workspace requests survive restart", any(r["reason"] == "Restart persistence check" for r in reqs), f"{len(reqs)} request(s)")
            archives = sorted((runtime / "evidence" / "archive").glob("*/MANIFEST.json"))
            chains = [json.loads(p.read_text()).get("audit_chain", {}) for p in archives]
            record("Previous session's audit log archived with an intact hash chain",
                   bool(archives) and all(c.get("ok") for c in chains if c),
                   f"{len(archives)} archive(s); lines {[c.get('lines') for c in chains]}")
            refused_logged = any("data_reliability_gate" in p.parent.joinpath("sandbox_operation_logs.jsonl").read_text()
                                 for p in archives if p.parent.joinpath("sandbox_operation_logs.jsonl").exists())
            record("The pre-restart gate refusal is in the archived audit evidence", refused_logged)
        except Exception as error:
            tail = " / ".join(log.read_text(errors="replace").splitlines()[-4:])
            record("Harness completed", False, f"{type(error).__name__}: {error} :: {tail}"[:600])
        finally:
            server.stop()

        # 5. several worker processes share sign-out and the sign-in throttle (v9 session store)
        multi = Server(env, tls, log, workers=3)
        try:
            multi.start()
            http = httpx.Client(base_url=multi.url, verify=str(tls["ca"]), timeout=15, trust_env=False)
            tok2 = http.post("/api/auth/login", json={"user_id": "sme.minh", "passcode": passcodes["sme.minh"]}).json()["token"]
            h2 = {"Authorization": "Bearer " + tok2}
            http.post("/api/auth/logout", headers=h2)
            fresh = lambda: httpx.Client(base_url=multi.url, verify=str(tls["ca"]), timeout=15, trust_env=False)  # noqa: E731
            codes = [fresh().get("/api/auth/me", headers=h2).status_code for _ in range(15)]  # new connections spread over workers
            record("3 workers: a signed-out token is refused by every worker (shared session store)", all(c == 401 for c in codes), f"codes {sorted(set(codes))}")
            fails = [fresh().post("/api/auth/login", json={"user_id": "sme.minh", "passcode": "wrong"}).status_code for _ in range(9)]
            record("3 workers: the sign-in throttle counts failures from every worker", fails[-1] == 429, f"codes {fails}")
        except Exception as error:
            record("Multi-worker session checks completed", False, f"{type(error).__name__}: {error}"[:300])
        finally:
            multi.stop()

        # 6. log scan
        text = log.read_text(errors="replace")
        needles = {"OTP secret": otp_secret, "session secret": session_secret, "session token": tok if 'tok' in locals() else "\0",
                   **{f"passcode of {u}": p for u, p in passcodes.items()}, "personal name": "Lan Nguyen", "Vietnamese name": "Nguyễn"}
        found = [k for k, v in needles.items() if v and v in text]
        record("Server log contains no secrets, passcodes, tokens or personal names", not found,
               ("found: " + ", ".join(found)) if found else f"{len(text.splitlines())} log lines scanned")
        record("Server log has no stack traces", "Traceback" not in text)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "deploy_verification.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    passed = sum(r["ok"] for r in results)
    lines = ["# Local deployment verification (T07)", "",
             "Generated by `python scripts/verify_deployment_local.py`: PRODUCTION mode, uvicorn behind HTTPS with a throw-away CA "
             "on 127.0.0.1, private secrets and hashed accounts, one restart.", "",
             f"**{passed}/{len(results)} checks passed.**", "", "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {r['check']} | {'pass' if r['ok'] else '**FAIL**'} | {r['detail'].replace('|', '/')} |" for r in results]
    lines += ["", "## Not covered here", "",
              "- A real cloud deployment (Render/Vercel/Fly): run `python scripts/deploy_smoke.py --base-url https://<your-host> "
              "--expect production --user ... --passcode ...` after each deploy.",
              "- The Docker image build: the base image could not be pulled in the verification sandbox. Build it with "
              "`docker build -t cashbridge .` and run the same smoke script against the container.",
              "- Hosting-provider TLS settings, WAF/rate limiting in front of the app, penetration testing, OIDC/MFA."]
    (REPORT_DIR / "deploy_verification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for r in results:
        print(("PASS " if r["ok"] else "FAIL ") + r["check"] + (f"  ({r['detail']})" if r["detail"] else ""))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
