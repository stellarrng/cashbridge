"""Data lifecycle for a CashBridge installation: inventory, export and retention purge (Audit 3).

Stores and what happens to them (defaults; override with CASHBRIDGE_RETENTION_DAYS):

  store                            personal data?                         retention
  -------------------------------  -------------------------------------  ---------------------------------------------
  audit log (evidence/*.jsonl)     user ids and reasons; payloads HASHED  kept (tamper-evident record; legal hold)
  audit archives (evidence/archive) same as audit log                     newest 20 kept; older than retention removed
  case file + pack PDF (cases/)    company data, preparer/approver ids    kept with the lending record
  workspace requests / messages /  free text written by users             kept with the case record
    evidence requests
  evidence vault (vault/)          uploaded documents, AES-256-GCM        deleted when the Director withdraws the pack;
                                   encrypted; uploader id                 otherwise kept with the case record
  notifications                    short texts                            deleted after retention (default 90 days)
  automation job payloads          support tickets and refunds may hold   payload REDACTED (hash kept) after retention
                                   customer text                          for non-accounting kinds in a final state
  sealed accounting evidence       ledger / bank / invoice rows           kept (accounting-record retention)
  browser                          session token (sessionStorage),        cleared on sign-out / tab close; preferences
                                   display preferences (localStorage)     stay on the device

Consent: the Director's OTP release is the consent to share one exact pack with one lender; it can be
withdrawn before the lender decides (POST /api/withdraw_release). Statutory retention periods differ by
country and record type: confirm them with counsel before production; the defaults here are conservative.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PII_JOB_KINDS = ("support_triage", "support_reply_draft", "refund_review", "employee_task_plan", "schedule_reminder", "collections_draft")
FINAL_JOB_STATES = ("completed", "failed", "approved", "dead_letter", "reviewed_accepted", "reviewed_rejected",
                    "reviewed_accepted_with_exceptions", "needs_review")
DEFAULT_RETENTION_DAYS = 90
ARCHIVE_RETENTION_DAYS = 365


def _rows(db: Path, sql: str, args: tuple = ()) -> List[Dict[str, Any]]:
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    except sqlite3.OperationalError:  # table not created yet
        return []
    finally:
        con.close()


def _count(db: Path, table: str) -> Optional[int]:
    r = _rows(db, f"SELECT COUNT(*) AS n FROM {table}")  # table names are constants below, never user input
    return r[0]["n"] if r else None


def inventory(runtime: Path, workspace_db: Path, automation_db: Path) -> List[Dict[str, Any]]:
    evidence = runtime / "evidence"
    audit = evidence / "sandbox_operation_logs.jsonl"
    archives = sorted(p for p in (evidence / "archive").glob("*") if p.is_dir()) if (evidence / "archive").exists() else []
    return [
        {"store": "audit log", "path": str(audit), "records": audit.read_text().count("\n") if audit.exists() else 0,
         "personal_data": "user ids and reasons; payloads stored as SHA-256 only", "retention": "kept (legal hold)"},
        {"store": "audit archives", "path": str(evidence / "archive"), "records": len(archives),
         "personal_data": "as audit log", "retention": f"newest 20, and none older than {ARCHIVE_RETENTION_DAYS} days"},
        {"store": "case files", "path": str(runtime / "cases"), "records": len(list((runtime / "cases").glob("*.json"))) if (runtime / "cases").exists() else 0,
         "personal_data": "preparer/approver ids, company and buyer names", "retention": "kept with the lending record"},
        *[{"store": f"workspace.{t}", "path": str(workspace_db), "records": _count(workspace_db, t),
           "personal_data": "free text written by users", "retention": "kept with the case record" if t != "notifications"
           else f"deleted after {DEFAULT_RETENTION_DAYS} days"}
          for t in ("requests", "messages", "evidence_requests", "notifications")],
        {"store": "evidence vault", "path": str(runtime / "vault"), "records": _count(runtime / "vault" / "vault.sqlite3", "files"),
         "personal_data": "uploaded documents (encrypted at rest, AES-256-GCM), uploader id",
         "retention": "deleted on consent withdrawal; otherwise kept with the case record"},
        {"store": "automation.jobs", "path": str(automation_db), "records": _count(automation_db, "jobs"),
         "personal_data": "support/refund payloads may contain customer text",
         "retention": f"payload redacted after {DEFAULT_RETENTION_DAYS} days for {', '.join(PII_JOB_KINDS)}"},
        {"store": "automation.audit_seals", "path": str(automation_db), "records": _count(automation_db, "audit_seals"),
         "personal_data": "accounting rows", "retention": "kept (accounting-record retention)"},
    ]


def export_tenant(tenant: str, runtime: Path, workspace_db: Path) -> Dict[str, Any]:
    """Everything this installation holds for one organisation, as one JSON document (portability / access request)."""
    case_files = {p.name: json.loads(p.read_text()) for p in sorted((runtime / "cases").glob("*.json"))} if (runtime / "cases").exists() else {}
    audit = runtime / "evidence" / "sandbox_operation_logs.jsonl"
    return {
        "tenant": tenant, "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workspace": {
            "requests": _rows(workspace_db, "SELECT * FROM requests WHERE tenant=?", (tenant,)),
            "request_activity": _rows(workspace_db, "SELECT a.* FROM activities a JOIN requests r ON r.id=a.request_id WHERE r.tenant=?", (tenant,)),
            "messages": _rows(workspace_db, "SELECT * FROM messages WHERE tenant=?", (tenant,)),
            "evidence_requests": _rows(workspace_db, "SELECT * FROM evidence_requests WHERE tenant=?", (tenant,)),
            "evidence_activity": _rows(workspace_db, "SELECT a.* FROM evidence_activity a JOIN evidence_requests e ON e.id=a.request_id WHERE e.tenant=?", (tenant,)),
            "notifications": _rows(workspace_db, "SELECT * FROM notifications WHERE tenant=?", (tenant,)),
        },
        "evidence_files": _rows(runtime / "vault" / "vault.sqlite3", "SELECT file_id,case_id,request_id,filename,mime,size,sha256,uploader,created "
                                "FROM files WHERE tenant=?", (tenant,)),
        "case_files": case_files,
        "audit_log": [json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else [],
        "note": "Audit payloads are SHA-256 digests; the originals were never stored in the log. Evidence files are listed "
                "by metadata; their bytes are available decrypted through the case's /file endpoint.",
    }


def purge(runtime: Path, workspace_db: Path, automation_db: Path, retention_days: int = DEFAULT_RETENTION_DAYS,
          now: Optional[datetime] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Apply the retention rules. Never touches the audit log, case files, sealed accounting evidence or open cases."""
    if not isinstance(retention_days, int) or retention_days < 1:
        raise ValueError("retention_days must be a positive integer")
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).isoformat()
    report: Dict[str, Any] = {"cutoff": cutoff, "dry_run": dry_run, "notifications_deleted": 0, "job_payloads_redacted": 0,
                              "archives_removed": []}
    if workspace_db.exists():
        con = sqlite3.connect(workspace_db)
        try:
            n = con.execute("SELECT COUNT(*) FROM notifications WHERE time < ?", (cutoff,)).fetchone()[0]
            report["notifications_deleted"] = n
            if not dry_run:
                con.execute("DELETE FROM notifications WHERE time < ?", (cutoff,))
                con.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            con.close()
    if automation_db.exists():
        con = sqlite3.connect(automation_db)
        try:
            marks = ",".join("?" * len(PII_JOB_KINDS))
            states = ",".join("?" * len(FINAL_JOB_STATES))
            rows = con.execute(f"SELECT id,payload FROM jobs WHERE created < ? AND kind IN ({marks}) AND state IN ({states}) "
                               "AND payload NOT LIKE '{\"redacted\": true%'", (cutoff, *PII_JOB_KINDS, *FINAL_JOB_STATES)).fetchall()
            report["job_payloads_redacted"] = len(rows)
            if not dry_run:
                for job_id, payload in rows:
                    stub = json.dumps({"redacted": True, "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                                       "redacted_at": now.isoformat(timespec="seconds")})
                    con.execute("UPDATE jobs SET payload=? WHERE id=?", (stub, job_id))
                con.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            con.close()
    archive_root = runtime / "evidence" / "archive"
    if archive_root.exists():
        limit = (now - timedelta(days=ARCHIVE_RETENTION_DAYS)).strftime("%Y%m%dT%H%M%S")
        for folder in sorted(p for p in archive_root.iterdir() if p.is_dir()):
            if folder.name[:15] < limit:
                report["archives_removed"].append(folder.name)
                if not dry_run:
                    shutil.rmtree(folder, ignore_errors=True)
    return report
