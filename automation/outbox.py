"""Transactional outbox + provider idempotency for anything that would leave CashBridge.

Problem: a worker that calls an external provider (send an email, post a payment instruction) and
then crashes before recording "sent" will, on retry, call the provider again. With at-least-once
queues that is a double payment or a duplicate dunning letter.

Pattern used here:
1. The human approval and the *intent* to deliver are written in ONE SQLite transaction
   (:func:`stage_for_approved_job`): either both commit or neither does.
2. :func:`dispatch` sends each pending effect with ``idempotency_key = effect_id`` (a stable
   SHA-256 of job id + effect kind). A crash after the provider accepted but before we mark it
   sent leads to a resend with the SAME key, and the provider returns the original receipt.
3. Only providers that declare ``supports_idempotency_keys`` are accepted, and in this MVP only
   the :class:`MockProvider` is allowed (``is_mock``). Real providers need a contract test and
   provider-side idempotency review first; :func:`dispatch` refuses them.

Nothing here contacts a real bank, payment rail or mailbox.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Protocol

DELIVERABLE_KINDS = {"collections_draft": "deliver_collection_reminder", "support_reply_draft": "deliver_support_reply",
                     "schedule_reminder": "create_local_reminder"}
MAX_DISPATCH_ATTEMPTS = 5

SCHEMA = """CREATE TABLE IF NOT EXISTS outbox (
    effect_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, effect TEXT NOT NULL, payload TEXT NOT NULL,
    approved_by TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    receipt TEXT, last_error TEXT, created TEXT NOT NULL, sent_at TEXT)"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def effect_id(job_id: str, effect: str) -> str:
    return hashlib.sha256(f"{job_id}|{effect}".encode()).hexdigest()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA)


def stage_for_approved_job(conn: sqlite3.Connection, job_id: str, kind: str, result: Dict[str, Any],
                           approved_by: str) -> Optional[str]:
    """Called inside the approval transaction. Returns the effect id, or None for kinds with no delivery."""
    effect = DELIVERABLE_KINDS.get(kind)
    if effect is None:
        return None
    ensure_schema(conn)
    eid = effect_id(job_id, effect)
    # Only the reviewed draft fields travel; never the raw source payload.
    body = {k: result[k] for k in ("draft", "subject", "ticket_id", "assignee_id", "due_at", "amount_cents") if k in result}
    conn.execute("INSERT OR IGNORE INTO outbox (effect_id,job_id,effect,payload,approved_by,state,created) VALUES (?,?,?,?,?,?,?)",
                 (eid, job_id, effect, json.dumps(body, ensure_ascii=False), approved_by, "pending", _now()))
    return eid


class Provider(Protocol):
    is_mock: bool
    supports_idempotency_keys: bool

    def send(self, effect: str, payload: Dict[str, Any], idempotency_key: str) -> str: ...


class MockProvider:
    """Stands in for an email / bank API. Honours idempotency keys like Stripe-style APIs do.

    ``fail_after_accept`` simulates the dangerous case: the provider performs the effect, then the
    connection drops before the caller learns the receipt.
    """

    is_mock = True
    supports_idempotency_keys = True

    def __init__(self) -> None:
        self.receipts: Dict[str, str] = {}
        self.performed: List[str] = []  # one entry per REAL side effect
        self.fail_after_accept = 0
        self.fail_before_accept = 0
        self._lock = threading.Lock()

    def send(self, effect: str, payload: Dict[str, Any], idempotency_key: str) -> str:
        with self._lock:
            if self.fail_before_accept:
                self.fail_before_accept -= 1
                raise ConnectionError("provider unavailable")
            if idempotency_key in self.receipts:
                return self.receipts[idempotency_key]  # replay: same receipt, no second effect
            receipt = "MOCK-" + idempotency_key[:12]
            self.receipts[idempotency_key] = receipt
            self.performed.append(idempotency_key)
            if self.fail_after_accept:
                self.fail_after_accept -= 1
                raise TimeoutError("connection lost after the provider accepted")
            return receipt


class ProviderNotAllowed(RuntimeError):
    pass


def dispatch(path: str, provider: Provider, limit: int = 20) -> List[Dict[str, Any]]:
    """Deliver pending effects. Safe to run concurrently and to re-run after a crash."""
    if not getattr(provider, "supports_idempotency_keys", False):
        raise ProviderNotAllowed("provider must honour idempotency keys")
    if not getattr(provider, "is_mock", False):
        raise ProviderNotAllowed("only the MOCK provider is enabled in this MVP; real providers need a contract test first")
    out: List[Dict[str, Any]] = []
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        conn.commit()
        rows = conn.execute("SELECT * FROM outbox WHERE state='pending' ORDER BY created LIMIT ?", (limit,)).fetchall()
        for row in rows:
            try:
                receipt = provider.send(row["effect"], json.loads(row["payload"]), idempotency_key=row["effect_id"])
            except (ConnectionError, TimeoutError, OSError) as error:
                attempts = row["attempts"] + 1
                state = "pending" if attempts < MAX_DISPATCH_ATTEMPTS else "dead_letter"
                conn.execute("UPDATE outbox SET attempts=?, state=?, last_error=? WHERE effect_id=? AND state='pending'",
                             (attempts, state, type(error).__name__, row["effect_id"]))
                conn.commit()
                out.append({"effect_id": row["effect_id"], "state": state, "error": type(error).__name__})
                continue
            conn.execute("UPDATE outbox SET state='sent', receipt=?, sent_at=?, attempts=attempts+1 WHERE effect_id=? AND state='pending'",
                         (receipt, _now(), row["effect_id"]))
            conn.commit()
            out.append({"effect_id": row["effect_id"], "state": "sent", "receipt": receipt})
    finally:
        conn.close()
    return out


def list_effects(path: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        return [dict(r) for r in conn.execute("SELECT effect_id,job_id,effect,state,attempts,receipt,approved_by FROM outbox ORDER BY created")]
    finally:
        conn.close()
