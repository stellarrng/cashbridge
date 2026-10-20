"""Encrypted evidence vault: the SME uploads a document once, the lender opens exactly that document (v9).

* Accepted: PDF, PNG, JPEG and plain UTF-8 text/CSV, recognised by their first bytes (the file name and the
  browser's MIME type are not trusted); at most 10 MB; empty files refused.
* The server computes the SHA-256 itself; that hash, not a client claim, is what the evidence request records.
* Stored encrypted with AES-256-GCM (authenticated): a 32-byte key from CASHBRIDGE_VAULT_KEY (base64), or in
  DEMO a random key created once in the runtime folder with owner-only permissions. Production refuses to start
  without a configured key. The tenant, case and file id are bound as associated data, so a ciphertext copied
  to another case does not decrypt.
* Every read decrypts, re-hashes and compares with the stored SHA-256 before returning a byte.

Access decisions (who may upload or open) are made by the API; this module stores and verifies.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_BYTES = 10_000_000
TYPES = {"application/pdf": (b"%PDF-",), "image/png": (b"\x89PNG\r\n\x1a\n",), "image/jpeg": (b"\xff\xd8\xff",)}


class VaultError(ValueError):
    pass


def sniff(data: bytes) -> str:
    for mime, magics in TYPES.items():
        if any(data.startswith(m) for m in magics):
            return mime
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise VaultError("Only PDF, PNG, JPEG or UTF-8 text files are accepted") from None
    if any(ord(c) < 9 or 13 < ord(c) < 32 for c in text[:4096]):
        raise VaultError("Text file contains control characters")
    return "text/plain"


def safe_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name or "document").name)[:120].strip(" .")
    return base or "document"


def vault_key(runtime: Path, env: Optional[dict] = None) -> bytes:
    from config import runtime_mode
    source = os.environ if env is None else env
    raw = source.get("CASHBRIDGE_VAULT_KEY", "").strip()
    if raw:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise VaultError("CASHBRIDGE_VAULT_KEY must be 32 bytes, base64-encoded")
        return key
    if runtime_mode.is_production(source):
        raise VaultError("CASHBRIDGE_VAULT_KEY is required in production")
    path = Path(runtime) / "vault.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(base64.b64encode(secrets.token_bytes(32)))
    return base64.b64decode(path.read_bytes())


class EvidenceVault:
    def __init__(self, root: Path, key: bytes) -> None:
        if len(key) != 32:
            raise VaultError("vault key must be 32 bytes")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.aead = AESGCM(key)
        self.db = self.root / "vault.sqlite3"
        with self._con() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS files (file_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, case_id TEXT NOT NULL,
                request_id TEXT NOT NULL, filename TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL,
                uploader TEXT NOT NULL, created TEXT NOT NULL)""")

    def _con(self):
        con = sqlite3.connect(self.db, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _aad(tenant: str, case_id: str, file_id: str) -> bytes:
        return f"{tenant}|{case_id}|{file_id}".encode()

    def store(self, tenant: str, case_id: str, request_id: str, filename: str, data: bytes, uploader: str) -> Dict[str, Any]:
        if not data:
            raise VaultError("Empty file")
        if len(data) > MAX_BYTES:
            raise VaultError(f"File larger than {MAX_BYTES // 1_000_000} MB")
        mime = sniff(data)
        if mime == "application/pdf":
            from security.pdf_screen import PdfRefused, screen_pdf
            try:
                screen_pdf(data)  # no scripts, launch actions, embedded files or submitting forms reach a lender
            except PdfRefused as exc:
                raise VaultError(str(exc)) from None
        sha = hashlib.sha256(data).hexdigest()
        file_id = "EVF-" + secrets.token_hex(8).upper()
        nonce = secrets.token_bytes(12)
        blob = nonce + self.aead.encrypt(nonce, data, self._aad(tenant, case_id, file_id))
        folder = self.root / hashlib.sha256(tenant.encode()).hexdigest()[:16]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{file_id}.bin").write_bytes(blob)
        meta = {"file_id": file_id, "tenant": tenant, "case_id": case_id, "request_id": request_id, "filename": safe_name(filename),
                "mime": mime, "size": len(data), "sha256": sha, "uploader": uploader,
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with self._con() as con:
            con.execute("INSERT INTO files VALUES (:file_id,:tenant,:case_id,:request_id,:filename,:mime,:size,:sha256,:uploader,:created)", meta)
        return meta

    def meta(self, tenant: str, case_id: str, file_id: str) -> Dict[str, Any]:
        with self._con() as con:
            row = con.execute("SELECT * FROM files WHERE file_id=? AND tenant=? AND case_id=?", (file_id, tenant, case_id)).fetchone()
        if not row:
            raise LookupError("file not found")
        return dict(row)

    def read(self, tenant: str, case_id: str, file_id: str) -> tuple:
        m = self.meta(tenant, case_id, file_id)
        path = self.root / hashlib.sha256(tenant.encode()).hexdigest()[:16] / f"{file_id}.bin"
        blob = path.read_bytes()
        try:
            data = self.aead.decrypt(blob[:12], blob[12:], self._aad(tenant, case_id, file_id))
        except Exception as error:
            raise VaultError("Stored file failed authentication (tampered or moved)") from error
        if hashlib.sha256(data).hexdigest() != m["sha256"]:
            raise VaultError("Stored file does not match its recorded SHA-256")
        return m, data

    def delete_case(self, tenant: str, case_id: str) -> int:
        with self._con() as con:
            rows = con.execute("SELECT file_id FROM files WHERE tenant=? AND case_id=?", (tenant, case_id)).fetchall()
            for r in rows:
                (self.root / hashlib.sha256(tenant.encode()).hexdigest()[:16] / f"{r['file_id']}.bin").unlink(missing_ok=True)
            con.execute("DELETE FROM files WHERE tenant=? AND case_id=?", (tenant, case_id))
        return len(rows)
