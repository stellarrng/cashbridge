"""Versioned sandbox planning changes, appeals and bank/SME case correspondence.

SQLite transactions, server-trusted identity and append-only activity. Never edits the
ledger, loan approval or external systems. Shared case must already be submitted to a lender.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import uuid
from core.data_reliability import money

FIELDS = frozenset({'marketing_usd', 'working_capital_usd', 'green_investment_usd'})

def now(): return datetime.now(timezone.utc).isoformat()

class WorkspaceStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as con:
            con.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS assumptions (tenant TEXT NOT NULL, field TEXT NOT NULL, value TEXT NOT NULL,
              version INTEGER NOT NULL, PRIMARY KEY (tenant,field));
            CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, case_id TEXT NOT NULL,
              kind TEXT NOT NULL, field TEXT, proposed TEXT, old_value TEXT, base_version INTEGER,
              reason TEXT NOT NULL, status TEXT NOT NULL, actor TEXT NOT NULL, reviewer TEXT,
              created TEXT NOT NULL, reviewed_at TEXT);
            CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, time TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, case_id TEXT NOT NULL,
              actor TEXT NOT NULL, actor_role TEXT NOT NULL, message TEXT NOT NULL, kind TEXT NOT NULL,
              created TEXT NOT NULL);
            ''')
    def db(self):
        con = sqlite3.connect(self.path, timeout=15, isolation_level='IMMEDIATE')
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=15000')
        return con
    def assumptions(self, tenant):
        with self.db() as con:
            return {r['field']:{'value':float(r['value']),'version':r['version']}
                for r in con.execute('SELECT * FROM assumptions WHERE tenant=?',(tenant,)).fetchall()}
    def propose(self, tenant, case_id, actor, field, value, reason):
        if field not in FIELDS: raise ValueError('Field not editable in financing scenario')
        if not 8 <= len(reason.strip()) <= 500: raise ValueError('A meaningful reason (8–500 characters) is required')
        val=money(value)
        if val<0: raise ValueError('Scenario amount cannot be negative')
        rid=str(uuid.uuid4())
        with self.db() as con:
            current=con.execute('SELECT value,version FROM assumptions WHERE tenant=? AND field=?',(tenant,field)).fetchone()
            old=current['value'] if current else None
            ver=current['version'] if current else 0
            con.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (rid,tenant,case_id,'planning_change',field,str(val),old,ver,reason.strip(),'pending',actor,None,now(),None))
            self._log(con,rid,actor,'proposed',f'{field}: {old or "not set"} -> {val}')
        return {'id':rid,'status':'pending','field':field,'proposed_value':float(val), 'current_value':float(old) if old is not None else None}
    def appeal(self, tenant, case_id, actor, reason, evidence_ref):
        if not 12 <= len(reason.strip()) <= 500: raise ValueError('Explain the concern (12–500 characters)')
        if not 3 <= len(evidence_ref.strip()) <= 150: raise ValueError('Evidence reference required')
        rid=str(uuid.uuid4())
        with self.db() as con:
            con.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (rid,tenant,case_id,'evidence_appeal',None,evidence_ref.strip(),None,None,
                reason.strip(),'pending',actor,None,now(),None))
            self._log(con,rid,actor,'appealed','New evidence reference submitted')
        return {'id':rid,'status':'pending','action':'review_requested'}
    def _log(self, con, request_id, actor, action, detail):
        con.execute('INSERT INTO activities (request_id,actor,action,detail,time) VALUES (?,?,?,?,?)',
                    (request_id,actor,action,detail,now()))
    def review(self, tenant, request_id, reviewer, approve, note):
        if not 3<=len(note.strip())<=500: raise ValueError('Review reason required (3–500 characters)')
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')  # serialise compare/version-check and state transition
            row=con.execute('SELECT * FROM requests WHERE tenant=? AND id=?',(tenant,request_id)).fetchone()
            if not row: raise ValueError('Request not found')
            if row['status']!='pending': raise ValueError('Request already decided')
            if row['actor']==reviewer: raise ValueError('Cannot approve your own proposal')
            status='approved' if approve else 'rejected'
            if row['kind']=='planning_change' and approve:
                cur=con.execute('SELECT version FROM assumptions WHERE tenant=? AND field=?',(tenant,row['field'])).fetchone()
                if (cur['version'] if cur else 0)!=row['base_version']:
                    raise ValueError('Stale proposal: underlying assumption changed. Create a fresh proposal')
                con.execute('''INSERT INTO assumptions (tenant,field,value,version) VALUES (?,?,?,1)
                  ON CONFLICT(tenant,field) DO UPDATE SET value=excluded.value,version=assumptions.version+1''',
                  (tenant,row['field'],row['proposed']))
            con.execute('UPDATE requests SET status=?, reviewer=?, reviewed_at=? WHERE id=?',(status,reviewer,now(),request_id))
            self._log(con,request_id,reviewer,status,note.strip())
            return {'id':request_id,'status':status,'applied_to':'scenario_assumptions_only' if row['kind']=='planning_change' and approve else 'none', 'external_action_performed':False}
    def list_requests(self, tenant, case_id):
        with self.db() as con:
            rows=con.execute('SELECT * FROM requests WHERE tenant=? AND case_id=? ORDER BY created DESC LIMIT 100',(tenant,case_id)).fetchall()
            return [{**dict(r),'activities':[dict(x) for x in con.execute('SELECT actor,action,detail,time FROM activities WHERE request_id=? ORDER BY id',(r['id'],))]} for r in rows]
    def post_message(self, tenant, case_id, actor, role, kind, message):
        if kind not in ('question','evidence_request','response'): raise ValueError('Unsupported message kind')
        if not 4<=len(message.strip())<=1000 or any(ord(ch)<32 and ch not in '\n\t' for ch in message):
            raise ValueError('Message must contain 4–1000 printable characters')
        mid=str(uuid.uuid4())
        with self.db() as con:
            con.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)',
                (mid,tenant,case_id,actor,role,message.strip(),kind,now()))
        return {'id':mid,'kind':kind,'created':now(),'external_message_sent':False}
    def list_messages(self, tenant, case_id):
        with self.db() as con:
            return [dict(r) for r in con.execute('SELECT * FROM messages WHERE tenant=? AND case_id=? ORDER BY created LIMIT 200',(tenant,case_id))]


# ----------------------------------------------------------------------------- lender evidence requests (v8)
EVIDENCE_STATES = ('open', 'submitted', 'accepted', 'rejected', 'revoked', 'expired')
OPEN_STATES = ('open', 'submitted', 'rejected')  # still blocking a funding decision
MAX_EVIDENCE_REQUESTS_PER_CASE = 50
MAX_SUBMISSIONS = 5


def _hex64(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


class EvidenceDesk:
    """Lender asks, SME answers with a content-bound document, lender accepts or rejects with a reason.

    open -> submitted -> accepted | rejected -> (resubmit) submitted ...; the lender may revoke an
    open request; past its due date an unresolved request expires. Every transition is an append-only
    activity row and is also returned so the API can write it to the hash-chained audit log. A funding
    approval is blocked while any request is open, submitted or rejected (see ``blocking``).
    Nothing here sends email or changes the ledger.
    """

    def __init__(self, path, clock=None):
        self.path = str(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS evidence_requests (id TEXT PRIMARY KEY, tenant TEXT NOT NULL,
              case_id TEXT NOT NULL, item TEXT NOT NULL, detail TEXT NOT NULL, status TEXT NOT NULL, requested_by TEXT NOT NULL,
              created TEXT NOT NULL, due TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0, evidence_ref TEXT, evidence_sha256 TEXT,
              submitted_by TEXT, decided_by TEXT, decision_reason TEXT, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence_activity (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,
              actor TEXT NOT NULL, role TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, time TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
              audience TEXT NOT NULL, case_id TEXT NOT NULL, request_id TEXT, text TEXT NOT NULL, time TEXT NOT NULL);''')
            cols = {r[1] for r in con.execute('PRAGMA table_info(evidence_requests)')}
            for col, kind in (('evidence_file_id', 'TEXT'), ('viewed_version', 'INTEGER'), ('viewed_by', 'TEXT')):
                if col not in cols:  # additive migration from v8
                    con.execute(f'ALTER TABLE evidence_requests ADD COLUMN {col} {kind}')

    def db(self):
        con = sqlite3.connect(self.path, timeout=15, isolation_level='IMMEDIATE')
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=15000')
        return con

    def _now(self):
        return self._clock().isoformat()

    @staticmethod
    def _text(value, lo, hi, what):
        if not isinstance(value, str) or not lo <= len(value.strip()) <= hi or any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError(f'{what} must be {lo}-{hi} printable characters')
        return value.strip()

    def _log(self, con, rid, actor, role, action, detail):
        con.execute('INSERT INTO evidence_activity (request_id,actor,role,action,detail,time) VALUES (?,?,?,?,?,?)',
                    (rid, actor, role, action, detail, self._now()))

    def _notify(self, con, tenant, audience, case_id, rid, text):
        con.execute('INSERT INTO notifications (tenant,audience,case_id,request_id,text,time) VALUES (?,?,?,?,?,?)',
                    (tenant, audience, case_id, rid, text[:300], self._now()))

    def _expire(self, con, tenant, case_id):
        now = self._now()
        rows = con.execute("SELECT id FROM evidence_requests WHERE tenant=? AND case_id=? AND status IN ('open','submitted','rejected') AND due<?",
                           (tenant, case_id, now)).fetchall()
        for r in rows:
            con.execute("UPDATE evidence_requests SET status='expired', updated=? WHERE id=?", (now, r['id']))
            self._log(con, r['id'], 'system', 'system', 'expired', 'Due date passed without an accepted document')
            self._notify(con, tenant, 'bank', case_id, r['id'], 'An evidence request expired without an accepted document')
            self._notify(con, tenant, 'sme', case_id, r['id'], 'An evidence request expired; ask the lender to reopen it if still needed')

    def _get(self, con, tenant, case_id, rid):
        row = con.execute('SELECT * FROM evidence_requests WHERE tenant=? AND case_id=? AND id=?', (tenant, case_id, rid)).fetchone()
        if not row:
            raise LookupError('evidence request not found')
        return row

    def open(self, tenant, case_id, actor, item, detail, due_days=7):
        item = self._text(item, 3, 120, 'Item')
        detail = self._text(detail, 4, 1000, 'Detail')
        if not isinstance(due_days, int) or isinstance(due_days, bool) or not 1 <= due_days <= 60:
            raise ValueError('Due in 1-60 days')
        from datetime import timedelta
        rid = 'EVR-' + uuid.uuid4().hex[:10].upper()
        now = self._clock()
        with self.db() as con:
            n = con.execute('SELECT COUNT(*) FROM evidence_requests WHERE tenant=? AND case_id=?', (tenant, case_id)).fetchone()[0]
            if n >= MAX_EVIDENCE_REQUESTS_PER_CASE:
                raise ValueError('Too many evidence requests on this case')
            con.execute('INSERT INTO evidence_requests (id,tenant,case_id,item,detail,status,requested_by,created,due,updated) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (rid, tenant, case_id, item, detail, 'open', actor, now.isoformat(), (now + timedelta(days=due_days)).isoformat(), now.isoformat()))
            self._log(con, rid, actor, 'bank_reviewer', 'opened', f'{item} (due in {due_days} days)')
            self._notify(con, tenant, 'sme', case_id, rid, f'Lender requests: {item}')
        return self.get(tenant, case_id, rid)

    def submit(self, tenant, case_id, rid, actor, evidence_ref, sha256, note='', file_id=None):
        ref = self._text(evidence_ref, 3, 150, 'Evidence reference')
        sha = (sha256 or '').strip().lower()
        if not _hex64(sha):
            raise ValueError('SHA-256 of the document is required (64 hex characters) so the lender can check the file it receives')
        note = self._text(note, 0, 500, 'Note') if note else ''
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            self._expire(con, tenant, case_id)
            row = self._get(con, tenant, case_id, rid)
            if row['status'] not in ('open', 'rejected'):
                raise ValueError(f"Request is {row['status']}; nothing to submit")
            if row['version'] >= MAX_SUBMISSIONS:
                raise ValueError('Submission limit reached; ask the lender to open a new request')
            con.execute("UPDATE evidence_requests SET status='submitted', version=version+1, evidence_ref=?, evidence_sha256=?, submitted_by=?, "
                        "updated=?, evidence_file_id=?, viewed_version=NULL, viewed_by=NULL WHERE id=?",
                        (ref, sha, actor, self._now(), file_id, rid))
            self._log(con, rid, actor, 'sme_accountant', 'submitted', f'v{row["version"] + 1}: {ref} sha256 {sha[:12]}…'
                      + (' · uploaded to the encrypted vault' if file_id else ' · file sent outside CashBridge') + (f' · {note}' if note else ''))
            self._notify(con, tenant, 'bank', case_id, rid, f'SME submitted {ref} for: {row["item"]}')
        return self.get(tenant, case_id, rid)

    def review(self, tenant, case_id, rid, actor, accept, reason, expected_version=None, received_sha256=None):
        """Accepting requires the lender to show it holds the same bytes: the SHA-256 of the file it received
        (computed on the lender's device) must equal the hash the SME submitted. Rejecting needs only a reason."""
        reason = self._text(reason, 3, 500, 'Reason')
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            self._expire(con, tenant, case_id)
            row = self._get(con, tenant, case_id, rid)
            if row['status'] != 'submitted':
                raise ValueError(f"Request is {row['status']}; only a submitted document can be reviewed")
            if expected_version is not None and expected_version != row['version']:
                raise ValueError('Stale review: a newer document was submitted; reload and review that one')
            if accept:
                got = (received_sha256 or '').strip().lower()
                viewed = row['evidence_file_id'] and row['viewed_version'] == row['version'] and row['viewed_by'] == actor
                if got:
                    if got != row['evidence_sha256']:
                        raise ValueError('The file you checked does not match the document the SME submitted (SHA-256 differs)')
                elif row['evidence_file_id']:
                    if not viewed:
                        raise ValueError('Open the uploaded document (this version) before accepting it')
                else:
                    raise ValueError('To accept, check the file you received: its SHA-256 is required')
            status = 'accepted' if accept else 'rejected'
            con.execute('UPDATE evidence_requests SET status=?, decided_by=?, decision_reason=?, updated=? WHERE id=?',
                        (status, actor, reason, self._now(), rid))
            self._log(con, rid, actor, 'bank_reviewer', status, f'v{row["version"]}: {reason}' + (' · file hash matched' if accept else ''))
            self._notify(con, tenant, 'sme', case_id, rid, f'Lender {status} {row["evidence_ref"]}: {reason}')
        return self.get(tenant, case_id, rid)

    def record_view(self, tenant, case_id, rid, actor, role):
        """The lender opened the uploaded file of the current version through CashBridge (logged; enables acceptance)."""
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            row = self._get(con, tenant, case_id, rid)
            if not row['evidence_file_id']:
                raise LookupError('no uploaded file for this request')
            if role == 'bank_reviewer':
                con.execute('UPDATE evidence_requests SET viewed_version=?, viewed_by=? WHERE id=?', (row['version'], actor, rid))
            self._log(con, rid, actor, role, 'opened', f'v{row["version"]}: {row["evidence_ref"]} (server-verified sha256 {row["evidence_sha256"][:12]}…)')
            return dict(row)

    def revoke(self, tenant, case_id, rid, actor, reason):
        reason = self._text(reason, 3, 500, 'Reason')
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            row = self._get(con, tenant, case_id, rid)
            if row['status'] in ('accepted', 'revoked', 'expired'):
                raise ValueError(f"Request is {row['status']}; it can no longer be revoked")
            con.execute("UPDATE evidence_requests SET status='revoked', decided_by=?, decision_reason=?, updated=? WHERE id=?",
                        (actor, reason, self._now(), rid))
            self._log(con, rid, actor, 'bank_reviewer', 'revoked', reason)
            self._notify(con, tenant, 'sme', case_id, rid, f'Lender withdrew the request for {row["item"]}: {reason}')
        return self.get(tenant, case_id, rid)

    def get(self, tenant, case_id, rid):
        with self.db() as con:
            row = self._get(con, tenant, case_id, rid)
            acts = [dict(a) for a in con.execute('SELECT actor,role,action,detail,time FROM evidence_activity WHERE request_id=? ORDER BY id', (rid,))]
            return {**dict(row), 'timeline': acts}

    def list(self, tenant, case_id):
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            self._expire(con, tenant, case_id)
            rows = con.execute('SELECT * FROM evidence_requests WHERE tenant=? AND case_id=? ORDER BY created', (tenant, case_id)).fetchall()
            items = [{**dict(r), 'timeline': [dict(a) for a in con.execute(
                'SELECT actor,role,action,detail,time FROM evidence_activity WHERE request_id=? ORDER BY id', (r['id'],))]} for r in rows]
        counts = {s: sum(1 for i in items if i['status'] == s) for s in EVIDENCE_STATES}
        blocking = [i['id'] for i in items if i['status'] in OPEN_STATES]
        return {'items': items, 'counts': counts, 'blocking_funding': blocking, 'ready_for_decision': not blocking}

    def blocking(self, tenant, case_id):
        return self.list(tenant, case_id)['blocking_funding']

    def notifications(self, tenant, audience, limit=30):
        with self.db() as con:
            return [dict(r) for r in con.execute('SELECT case_id,request_id,text,time FROM notifications WHERE tenant=? AND audience=? ORDER BY id DESC LIMIT ?',
                                                 (tenant, audience, max(1, min(limit, 100))))]
