"""Opt-in local/cloud worker: SQLite durable queue, deterministic tasks, approval gate.

Security boundary: only server-owned allowlisted task handlers execute; payload text is data,
not executable instructions. No outgoing email/payment/accounting entries. A production
implementation requires OIDC/tenant isolation, backups and provider-specific adapters.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from typing import Any
from automation.audit_evidence import reconcile_highlights, invoice_highlights, seal_evidence, verify_evidence, provenance_highlights

KINDS = ('accounting_reconcile', 'audit_invoice', 'support_triage', 'collections_draft', 'cash_alert', 'support_reply_draft', 'refund_review', 'employee_task_plan', 'executive_digest', 'schedule_reminder', 'provenance_review')
MAX_RECORDS = 300
MAX_PAYLOAD = 50_000
MAX_ATTEMPTS = 3
AUDIT_DECISIONS = ('accepted', 'accepted_with_exceptions', 'rejected')


def backoff_seconds(attempts: int) -> int:
    """Exponential backoff after the n-th failed attempt: 2, 4, 8 ... capped at 300 s."""
    return min(300, 2 ** attempts)


def _handler():
    # Looked up at call time so fault-injection tests can swap the pure handler.
    return evaluate


def _cents(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('Invalid amount')
    from decimal import Decimal, InvalidOperation
    try:
        amt = Decimal(str(value))
        if not amt.is_finite() or amt < 0 or amt.as_tuple().exponent < -2:
            raise ValueError('Amounts must be finite, nonnegative and have at most 2 decimals')
        return int(amt * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid amount') from None


def _signed_cents(value: Any) -> int:
    """Like _cents but a projected balance may be negative (that is what a cash alert is for)."""
    if isinstance(value, bool):
        raise ValueError('Invalid amount')
    text = str(value).strip()
    if text.startswith('-'):
        return -_cents(text[1:])
    return _cents(text)


def _safe(value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError('Invalid text identifier')
    return value.strip()


def _iso(value: Any) -> str:
    raw = _safe(value, 40)
    try:
        parsed = dt.datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError:
        raise ValueError('Invalid ISO datetime') from None
    if parsed.tzinfo is None: raise ValueError('Timezone required')
    return parsed.isoformat()


def evaluate(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    """Pure task processor; uses no network and makes no operational side effects."""
    if kind not in KINDS or not isinstance(data, dict):
        raise ValueError('Unsupported task kind or payload')
    if kind == 'provenance_review':
        highlighted = provenance_highlights(data.get('changes', []))
        return {'highlights': highlighted, 'review_required': bool(highlighted),
                'values_applied': False, 'evidence_state': 'unsealed_pending_review'}
    if kind == 'accounting_reconcile':
        entries = data.get('ledger', [])
        bank = data.get('bank', [])
        if not isinstance(entries, list) or not isinstance(bank, list) or len(entries) > MAX_RECORDS or len(bank) > MAX_RECORDS:
            raise ValueError('Invalid transaction lists')
        def index(rows):
            out = {}
            for r in rows:
                key = str(r.get('reference', '')).strip()
                if not key or len(key) > 100 or key in out:
                    raise ValueError('Reference missing or duplicated')
                out[key] = _cents(r.get('amount'))
            return out
        l, b = index(entries), index(bank)
        exceptions = [{'reference': k, 'issue': 'amount_mismatch' if k in b else 'missing_bank_entry', 'ledger_cents': v, 'bank_cents': b.get(k)} for k, v in l.items() if b.get(k) != v]
        exceptions.extend({'reference': k, 'issue': 'missing_ledger_entry', 'bank_cents': v} for k, v in b.items() if k not in l)
        return {'matched_count': sum(1 for k, v in l.items() if b.get(k) == v), 'exceptions': exceptions, 'review_required': bool(exceptions), 'posting_performed': False, 'highlights': reconcile_highlights(entries, bank), 'evidence_state': 'unsealed_pending_review'}
    if kind == 'audit_invoice':
        invoices = data.get('invoices', [])
        if not isinstance(invoices, list) or len(invoices) > MAX_RECORDS:
            raise ValueError('Invalid invoices')
        seen = set()
        flags = []
        for i, item in enumerate(invoices):
            number = str(item.get('invoice_number','')).strip()
            vendor = str(item.get('vendor','')).strip().casefold()
            if not number or not vendor:
                flags.append({'row': i, 'signal': 'missing_identifier'})
            key = (vendor, number.casefold())
            if key in seen:
                flags.append({'row': i, 'signal': 'potential_duplicate'})
            seen.add(key)
            _cents(item.get('amount'))
        return {'invoices_checked': len(invoices), 'risk_flags': flags, 'review_required': bool(flags), 'fraud_conclusion': 'not_determined', 'highlights': invoice_highlights(invoices), 'evidence_state': 'unsealed_pending_review'}
    if kind == 'support_triage':
        ticket = str(data.get('message',''))
        if not ticket or len(ticket) > 5000:
            raise ValueError('Ticket length out of range')
        lower = ticket.lower()
        # Classification only. Do not copy private free-form message into the output.
        urgent = any(x in lower for x in ('fraud', 'unauthorized', 'lừa đảo', 'gian lận', 'mất tiền'))
        category = 'security' if urgent else 'billing' if any(x in lower for x in ('invoice', 'billing', 'hóa đơn', 'thanh toán')) else 'general'
        return {'category': category, 'priority': 'high' if urgent else 'normal', 'recommended_queue': 'human_security' if urgent else 'customer_support', 'external_reply_sent': False, 'review_required': True}
    if kind == 'collections_draft':
        reference = str(data.get('invoice_number','')).strip()
        days = data.get('days_overdue')
        if not reference or len(reference) > 100 or not isinstance(days, int) or isinstance(days, bool) or days < 0 or days > 3650:
            raise ValueError('Invalid invoice reference or overdue days')
        amount = _cents(data.get('amount'))
        return {'draft': f'Reminder: invoice {reference} is {days} days past due. Please review the outstanding balance before responding.', 'amount_cents': amount, 'external_reply_sent': False, 'review_required': True}
    if kind == 'support_reply_draft':
        ticket_id = _safe(data.get('ticket_id'), 90)
        category = str(data.get('category', 'general')).lower()
        if category not in ('general', 'shipping', 'refund', 'billing', 'complaint'):
            raise ValueError('Unsupported support category')
        templates = {
            'general': 'Thank you for contacting us. We have received your request and will review it.',
            'shipping': 'We received your delivery question. Our support team will verify the shipping status.',
            'refund': 'We received your refund request. We will review the order and payment records before confirming eligibility.',
            'billing': 'We received your billing question. We will verify the invoice and payment information.',
            'complaint': 'Thank you for raising this concern. A support specialist will review it.'}
        # Never auto-send; do not echo untrusted content, emails or identifiers in reply body.
        return {'ticket_id':ticket_id, 'subject':'Update on your support request', 'draft':templates[category],
                'external_reply_sent':False,'review_required':True,'channel':'draft_only'}
    if kind == 'refund_review':
        order_id = _safe(data.get('order_id'), 90)
        requested = _cents(data.get('requested_amount'))
        captured = _cents(data.get('paid_amount'))
        already_refunded = _cents(data.get('already_refunded', '0'))
        currency = str(data.get('currency','USD')).upper()
        if currency not in ('USD','VND','EUR','CNY'):
            raise ValueError('Unsupported currency')
        if already_refunded > captured:
            raise ValueError('Previously refunded amount exceeds captured payment')
        flags = []
        if requested == 0: flags.append('zero_refund_requested')
        if requested + already_refunded > captured: flags.append('exceeds_unreimbursed_payment')
        if not data.get('payment_verified', False): flags.append('payment_not_verified')
        if data.get('order_status') not in ('delivered','returned','cancelled','not_fulfilled'):
            flags.append('order_status_unverified')
        if data.get('prior_refund_dispute',False): flags.append('prior_dispute_review')
        if not data.get('policy_eligible',False): flags.append('policy_eligibility_unconfirmed')
        return {'order_id':order_id,'currency':currency, 'requested_cents':requested,
                'remaining_refundable_cents':captured-already_refunded,'signals':flags,
                'provisional_status':'manual_review' if flags else 'eligible_for_human_approval',
                'fraud_conclusion':'not_determined', 'refund_executed':False, 'review_required':True}
    if kind == 'employee_task_plan':
        tasks = data.get('tasks', [])
        if not isinstance(tasks,list) or len(tasks)>60: raise ValueError('Invalid task list')
        planned = []
        for task in tasks:
            if not isinstance(task,dict): raise ValueError('Invalid task')
            title = _safe(task.get('title'),150)
            assignee = _safe(task.get('assignee_id'),80)
            deadline = _iso(task.get('due_at'))
            priority = task.get('priority','normal')
            if priority not in ('low','normal','high'): raise ValueError('Invalid priority')
            planned.append({'title':title,'assignee_id':assignee,'due_at':deadline,'priority':priority,
                            'assignment_sent':False,'calendar_event_created':False})
        return {'planned_tasks':planned,'review_required':True,'external_action_performed':False}
    if kind == 'schedule_reminder':
        due = _iso(data.get('due_at'))
        target = _safe(data.get('assignee_id'),80)
        subject = _safe(data.get('subject'),150)
        return {'assignee_id':target,'subject':subject,'due_at':due,'reminder_created_locally':True,
                'external_notification_sent':False,'review_required':True}
    if kind == 'executive_digest':
        # Aggregate numbers only. Never forward raw tickets, customer details or financial records.
        metrics = data.get('metrics',{})
        if not isinstance(metrics,dict) or len(metrics)>30: raise ValueError('Invalid metrics')
        allowed = {'pending_refunds','refunds_flagged','overdue_invoices','unmatched_transactions',
                   'high_priority_tickets','tasks_overdue','cash_alerts','pending_approvals'}
        summary={}
        for key, value in metrics.items():
            if key not in allowed or not isinstance(value,int) or isinstance(value,bool) or not 0<=value<=1000000:
                raise ValueError('Unknown or invalid aggregate metric')
            summary[key]=value
        attention={k:v for k,v in summary.items() if v>0}
        return {'aggregate_metrics':summary,'attention_needed':attention,'suggested_alert':bool(attention),
                'executive_notification_sent':False,'review_required':bool(attention)}
    balances = data.get('projected_balances', [])
    minimum = _cents(data.get('minimum_reserve'))
    if not isinstance(balances, list) or len(balances) > 52:
        raise ValueError('Invalid cash forecast')
    below = [{'period': idx + 1, 'shortfall_cents': minimum - _signed_cents(v)} for idx, v in enumerate(balances) if _signed_cents(v) < minimum]
    return {'reserve_breaches': below, 'review_required': bool(below), 'payments_performed': False}


class AutomationStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.mutex = threading.RLock()
        with self._connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                payload TEXT NOT NULL, result TEXT, created TEXT NOT NULL,
                reviewed TEXT, fingerprint TEXT NOT NULL UNIQUE)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS audit_seals (
                job_id TEXT PRIMARY KEY, seal_json TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id))''')
            # Additive migrations: upgrading an existing v6 queue retains jobs and seals.
            existing = {r[1] for r in conn.execute('PRAGMA table_info(jobs)')}
            migrations = {'attempts':'INTEGER NOT NULL DEFAULT 0',
                          'next_run':'TEXT', 'claimed_at':'TEXT',
                          'last_error':'TEXT', 'dead_at':'TEXT', 'lease':'TEXT'}
            for col, definition in migrations.items():
                if col not in existing: conn.execute(f'ALTER TABLE jobs ADD COLUMN {col} {definition}')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_job_due ON jobs(state,next_run,created)')

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=15000')
        return conn

    def enqueue(self, kind: str, payload: dict, key: str) -> dict:
        if kind not in KINDS or not isinstance(payload, dict):
            raise ValueError('Unsupported task')
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(raw.encode()) > MAX_PAYLOAD or not isinstance(key, str) or not 8 <= len(key) <= 128:
            raise ValueError('Task too large or invalid idempotency key')
        fingerprint = hashlib.sha256((kind + ':' + key).encode()).hexdigest()
        with self.mutex, self._connect() as conn:
            existing = conn.execute('SELECT id,kind,state FROM jobs WHERE fingerprint=?', (fingerprint,)).fetchone()
            if existing:
                return dict(existing)
            job_id = str(uuid.uuid4())
            conn.execute('INSERT INTO jobs (id,kind,state,payload,created,fingerprint) VALUES (?,?,?,?,?,?)',
                         (job_id,kind,'pending',raw,dt.datetime.now(dt.timezone.utc).isoformat(),fingerprint))
            return {'id': job_id, 'kind':kind, 'state':'pending'}

    def recover_stale(self, older_seconds: int = 600) -> int:
        """Recover a worker interrupted after atomic claim and before completion.

        A deterministic, locally side-effect-free handler is safe to retry. Do not use this
        technique for payments, emails, accounting posting or other external side effects.
        """
        if older_seconds < 1: raise ValueError('Invalid recovery window')
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=older_seconds)).isoformat()
        with self.mutex, self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows=conn.execute('SELECT id,attempts FROM jobs WHERE state=? AND claimed_at<?',
                              ('running',cutoff)).fetchall()
            for row in rows:
                state='dead_letter' if row['attempts'] >= MAX_ATTEMPTS else 'pending'
                # Clearing the lease means the interrupted worker can no longer write a late result.
                conn.execute('UPDATE jobs SET state=?, claimed_at=NULL, lease=NULL, last_error=?, dead_at=? WHERE id=?',
                             (state,'Stale worker claim recovered',
                              dt.datetime.now(dt.timezone.utc).isoformat() if state=='dead_letter' else None,row['id']))
            return len(rows)

    def run_pending(self, limit: int = 10) -> list[dict]:
        """Atomic multi-worker claim, bounded retry with exponential backoff and DLQ.

        Transient operational errors retry; invalid task payloads fail fast. All current
        handlers are pure and perform no external financial actions.
        """
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('Invalid batch size')
        output=[]
        for _ in range(limit):
            with self.mutex, self._connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                current=dt.datetime.now(dt.timezone.utc).isoformat()
                row=conn.execute("SELECT * FROM jobs WHERE state='pending' AND (next_run IS NULL OR next_run<=?) ORDER BY created LIMIT 1",(current,)).fetchone()
                if not row: break
                lease=str(uuid.uuid4())
                conn.execute("UPDATE jobs SET state='running',attempts=attempts+1,claimed_at=?,lease=? WHERE id=?",
                             (current,lease,row['id']))
            attempts=row['attempts']+1
            try:
                result=_handler()(row['kind'],json.loads(row['payload']))
                state='needs_review' if result['review_required'] else 'completed'
                transient=False
            except (OSError, ConnectionError, TimeoutError) as exc:
                result={'error':'Transient task execution error','type':type(exc).__name__}
                transient=True
                state='pending' if attempts<MAX_ATTEMPTS else 'dead_letter'
            except (ValueError, TypeError, KeyError) as exc:
                result={'error':str(exc),'type':type(exc).__name__}
                state='failed'
                transient=False
            except Exception as exc:
                # An unanticipated programming failure is quarantined, not retried forever.
                result={'error':'Unexpected handler failure','type':type(exc).__name__}
                state='dead_letter'
                transient=False
            retry_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=backoff_seconds(attempts))).isoformat() if transient and state=='pending' else None
            with self.mutex,self._connect() as conn:
                # Lease check: if this claim was recovered as stale and re-run, the late result is dropped.
                written=conn.execute("UPDATE jobs SET state=?,result=?,next_run=?,claimed_at=NULL,lease=NULL,last_error=?,dead_at=? "
                                     "WHERE id=? AND state='running' AND lease=?",
                    (state,json.dumps(result),retry_at,result.get('error'),
                     dt.datetime.now(dt.timezone.utc).isoformat() if state=='dead_letter' else None,row['id'],lease)).rowcount
            if not written:
                state='lease_lost'
            output.append({'id':row['id'],'kind':row['kind'],'state':state,
                           'attempts':attempts,'retry_at':retry_at if written else None,'result':result})
        return output

    def dead_letters(self, limit: int=50) -> list[dict]:
        with self._connect() as conn:
            rows=conn.execute("SELECT id,kind,state,attempts,last_error,created,dead_at FROM jobs WHERE state='dead_letter' ORDER BY dead_at DESC LIMIT ?",
                              (max(1,min(limit,100)),)).fetchall()
            return [dict(r) for r in rows]

    def redrive(self, job_id: str) -> dict:
        """Explicit operator action: same idempotency key, no new duplicate task."""
        with self.mutex,self._connect() as conn:
            row=conn.execute('SELECT state FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['state']!='dead_letter': raise ValueError('Job is not in dead-letter queue')
            conn.execute("UPDATE jobs SET state='pending',attempts=0,next_run=NULL,last_error=NULL,dead_at=NULL WHERE id=?",(job_id,))
            return {'id':job_id,'state':'pending','external_action_performed':False}

    def list_jobs(self, limit: int = 50) -> list[dict]:
        with self.mutex, self._connect() as conn:
            rows = conn.execute('SELECT id,kind,state,created,result FROM jobs ORDER BY created DESC LIMIT ?', (max(1,min(limit,100)),)).fetchall()
            return [{**dict(r), 'result':json.loads(r['result']) if r['result'] else None} for r in rows]

    def review_audit(self, job_id: str, reviewer: str, decision: str) -> dict:
        """Seal exact source+findings only after accountant/auditor explicit decision."""
        with self.mutex, self._connect() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row or row['kind'] not in ('accounting_reconcile','audit_invoice','provenance_review'):
                raise ValueError('Not an accounting/audit job')
            if decision not in AUDIT_DECISIONS:
                raise ValueError('Decision must be one of: ' + ', '.join(AUDIT_DECISIONS))
            if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100:
                raise ValueError('Reviewer required')
            if row['state'] not in ('needs_review','completed'):
                raise ValueError('Job not ready for review')
            existing = conn.execute('SELECT seal_json FROM audit_seals WHERE job_id=?',(job_id,)).fetchone()
            if existing:
                raise ValueError('Evidence already sealed; cannot overwrite')
            findings = json.loads(row['result'])
            if decision == 'accepted' and findings.get('review_required'):
                raise ValueError('Exceptions require accepted_with_exceptions or rejected')
            seal = seal_evidence(task_kind=row['kind'], source=json.loads(row['payload']),
                                 findings=findings, reviewer_id=reviewer, decision=decision)
            conn.execute('INSERT INTO audit_seals(job_id,seal_json) VALUES (?,?)',
                         (job_id, json.dumps(seal, ensure_ascii=False)))
            conn.execute('UPDATE jobs SET state=?,reviewed=? WHERE id=?',
                         ('reviewed_'+decision, reviewer, job_id))
            return {'job_id':job_id, 'sha256':seal['sha256'],
                    'decision':decision, 'verified':verify_evidence(seal),
                    'note':'SHA-256 integrity fingerprint, not encryption or digital signature'}

    def get_audit_seal(self, job_id: str) -> dict:
        with self._connect() as conn:
            row=conn.execute('SELECT seal_json FROM audit_seals WHERE job_id=?',(job_id,)).fetchone()
            if not row: raise ValueError('Audit seal not found')
            seal=json.loads(row['seal_json'])
            return {'seal':seal, 'verified':verify_evidence(seal)}

    def approve(self, job_id: str, reviewer: str) -> dict:
        """Human approval. For draft-producing kinds this stages a delivery in the transactional
        outbox (automation/outbox.py) in the SAME transaction, so approval and intent commit together."""
        if not reviewer or len(reviewer) > 100:
            raise ValueError('Reviewer required')
        from automation import outbox
        with self.mutex, self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT state,kind,result FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row or row['state'] != 'needs_review':
                raise ValueError('Job is not awaiting review')
            conn.execute('UPDATE jobs SET state=?, reviewed=? WHERE id=?', ('approved', reviewer, job_id))
            staged = outbox.stage_for_approved_job(conn, job_id, row['kind'], json.loads(row['result'] or '{}'), reviewer)
        return {'id':job_id,'state':'approved','external_action_performed':False,'outbox_effect_id':staged}
