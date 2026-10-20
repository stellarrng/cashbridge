"""Secure evidence transfer: encrypted vault, server-side hash, type/size checks, authorised viewer, view-before-accept."""

import base64
import hashlib
import os
import stat
from pathlib import Path

import pytest

from workspace.evidence_vault import EvidenceVault, VaultError, safe_name, sniff, vault_key

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
KEY = b"v" * 32


@pytest.fixture
def vault(tmp_path):
    return EvidenceVault(tmp_path / "vault", KEY)


def test_type_sniffing_trusts_bytes_not_names():
    assert sniff(PDF) == "application/pdf"
    assert sniff(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert sniff(b"\xff\xd8\xff\xe0....") == "image/jpeg"
    assert sniff("Bill of lading BL-77\nQty 120\n".encode()) == "text/plain"
    for bad in (b"MZ\x90\x00\x03", b"PK\x03\x04zip", b"\x00\x01\x02binary", "x\x07bell".encode()):
        with pytest.raises(VaultError):
            sniff(bad)


def test_filenames_are_sanitised():
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("bl<script>.pdf") == "bl_script_.pdf"
    assert safe_name("") == "document"


def test_round_trip_is_encrypted_and_hash_checked(vault, tmp_path):
    meta = vault.store("T1", "PACK-1", "EVR-1", "bl.pdf", PDF, "sme.lan")
    assert meta["sha256"] == hashlib.sha256(PDF).hexdigest() and meta["mime"] == "application/pdf"
    stored = next((tmp_path / "vault").rglob(f"{meta['file_id']}.bin")).read_bytes()
    assert PDF not in stored and b"%PDF" not in stored  # ciphertext at rest
    m, data = vault.read("T1", "PACK-1", meta["file_id"])
    assert data == PDF and m["filename"] == "bl.pdf"


def test_tampering_or_moving_a_ciphertext_is_detected(vault, tmp_path):
    meta = vault.store("T1", "PACK-1", "EVR-1", "bl.pdf", PDF, "sme.lan")
    path = next((tmp_path / "vault").rglob(f"{meta['file_id']}.bin"))
    raw = bytearray(path.read_bytes())
    raw[20] ^= 0xFF
    path.write_bytes(bytes(raw))
    with pytest.raises(VaultError, match="authentication"):
        vault.read("T1", "PACK-1", meta["file_id"])
    with pytest.raises(LookupError):
        vault.read("T1", "PACK-OTHER", meta["file_id"])  # bound to its case
    with pytest.raises(LookupError):
        vault.read("T2", "PACK-1", meta["file_id"])  # and to its tenant


def test_size_and_emptiness_limits(vault):
    with pytest.raises(VaultError):
        vault.store("T", "P", "R", "x.pdf", b"", "u")
    with pytest.raises(VaultError):
        vault.store("T", "P", "R", "x.pdf", b"%PDF-" + b"0" * 10_000_001, "u")


def test_key_handling(tmp_path):
    with pytest.raises(VaultError):
        vault_key(tmp_path, {"CASHBRIDGE_ENV": "production"})
    k = vault_key(tmp_path, {})
    assert len(k) == 32 and stat.S_IMODE(os.stat(tmp_path / "vault.key").st_mode) == 0o600
    assert vault_key(tmp_path, {}) == k  # stable across restarts
    assert vault_key(tmp_path, {"CASHBRIDGE_VAULT_KEY": base64.b64encode(KEY).decode()}) == KEY
    with pytest.raises(VaultError):
        vault_key(tmp_path, {"CASHBRIDGE_VAULT_KEY": base64.b64encode(b"short").decode()})


# --------------------------------------------------------------------------- through the API
@pytest.fixture
def api(tmp_path, monkeypatch):
    from api.main import create_app
    from scripts.run_demo_story import StoryClock
    from tests.authed import RoleClient
    from ui.backend_real import RealBackend
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    monkeypatch.setenv("CASHBRIDGE_RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.delenv("CASHBRIDGE_REQUIRE_DATA_GATE", raising=False)
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-ui"))
    client.post("/api/autopilot/run", json={"execute": True})
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    pack = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()["snapshot"]["pack"]["pack_id"]
    rid = client.post(f"/api/workspace/cases/{pack}/evidence", json={"item": "Signed bill of lading", "detail": "carrier-signed copy"},
                      headers=client.header("bank.lihua")).json()["id"]
    return client, backend, pack, rid


def test_upload_view_accept_flow(api):
    from security.audit_log import verify_chain
    client, backend, pack, rid = api
    base = f"/api/workspace/cases/{pack}/evidence/{rid}"
    up = client.post(f"{base}/upload", files={"file": ("../../bl.pdf", PDF, "application/x-msdownload")}, headers=client.header("sme.lan"))
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["status"] == "submitted" and body["evidence_sha256"] == hashlib.sha256(PDF).hexdigest()  # server-computed
    assert body["file"]["filename"] == "bl.pdf" and body["file"]["mime"] == "application/pdf"  # bytes decide, not the claim
    bank = client.header("bank.lihua")
    early = client.post(f"{base}/review", json={"accept": True, "reason": "Looks right"}, headers=bank)
    assert early.status_code == 409 and "Open the uploaded document" in early.json()["detail"]
    f = client.get(f"{base}/file", headers=bank)
    assert f.status_code == 200 and f.content == PDF
    assert f.headers["x-content-type-options"] == "nosniff" and "attachment" in f.headers["content-disposition"]
    assert "sandbox" in f.headers["content-security-policy"] and f.headers["x-cashbridge-sha256"] == hashlib.sha256(PDF).hexdigest()
    ok = client.post(f"{base}/review", json={"accept": True, "reason": "Carrier signature present"}, headers=bank)
    assert ok.status_code == 200 and ok.json()["status"] == "accepted"
    text = backend.coord.audit_path.read_text()
    assert "evidence uploaded" in text and "evidence opened" in text and verify_chain(backend.coord.audit_path)[0]


def test_upload_and_view_boundaries(api):
    from tests.test_adversarial import outsider
    client, backend, pack, rid = api
    base = f"/api/workspace/cases/{pack}/evidence/{rid}"
    assert client.post(f"{base}/upload", files={"file": ("x.exe", b"MZ\x90\x00", "application/pdf")}, headers=client.header("sme.lan")).status_code == 422
    assert client.post(f"{base}/upload", files={"file": ("bl.pdf", PDF, "application/pdf")}, headers=client.header("sme.minh")).status_code == 403
    assert client.post(f"{base}/upload", files={"file": ("bl.pdf", PDF, "application/pdf")}, headers=client.header("bank.lihua")).status_code == 403
    assert client.post(f"/api/workspace/cases/{pack}/evidence/EVR-NOPE/upload", files={"file": ("bl.pdf", PDF, "application/pdf")},
                       headers=client.header("sme.lan")).status_code == 404
    assert client.post(f"{base}/upload", files={"file": ("bl.pdf", PDF, "application/pdf")}, headers=client.header("sme.lan")).status_code == 200
    assert client.get(f"{base}/file", headers=outsider("bank_reviewer", tenant="LENDER-OTHER")).status_code == 403
    assert client.get(f"{base}/file", headers=outsider("sme_accountant")).status_code == 403
    assert client.get(f"/api/workspace/cases/PACK-OTHER/evidence/{rid}/file", headers=client.header("bank.lihua")).status_code == 404
    # SME opening its own upload does not count as the lender's review
    assert client.get(f"{base}/file", headers=client.header("sme.lan")).status_code == 200
    assert client.post(f"{base}/review", json={"accept": True, "reason": "ok fine"}, headers=client.header("bank.lihua")).status_code == 409
    # After consent withdrawal the lender cannot open the file any more
    from core import privacy_lifecycle as pl
    rt = Path(os.environ["CASHBRIDGE_RUNTIME_DIR"])
    inv = {x["store"]: x for x in pl.inventory(rt, rt / "none.db", rt / "none2.db")}
    assert inv["evidence vault"]["records"] == 1 and "encrypted" in inv["evidence vault"]["personal_data"]
    assert pl.export_tenant("TEN-BDT-001", rt, rt / "none.db")["evidence_files"][0]["sha256"] == hashlib.sha256(PDF).hexdigest()
    w = client.post("/api/withdraw_release", json={"reason": "Buyer objects"}, headers=client.header("sme.minh"))
    assert w.status_code == 200 and w.json()["evidence_files_deleted"] == 1
    assert client.get(f"{base}/file", headers=client.header("bank.lihua")).status_code == 404
    assert not list((rt / "vault").rglob("*.bin"))  # ciphertext removed too, not just hidden
