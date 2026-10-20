"""Lender adapter layer (v9): one neutral quote format, any number of providers behind it.

    CASHBRIDGE_LENDER_ADAPTER=mock          (default) quotes computed from the MOCK catalogue: source_type "simulated"
    CASHBRIDGE_LENDER_ADAPTER=sandbox_http  a provider's HTTP sandbox: source_type "provider_issued", environment "sandbox"
        CASHBRIDGE_LENDER_BASE_URL       https://... (http only for localhost)
        CASHBRIDGE_LENDER_API_KEY        bearer token for the provider
        CASHBRIDGE_LENDER_WEBHOOK_SECRET shared secret for signed status callbacks
        CASHBRIDGE_LENDER_TIMEOUT_S      per-request timeout (default 5)

Rules every adapter follows (and the contract tests check):
* A quote is data with an expiry. An expired quote cannot be accepted; the SME asks for a new one.
* Requests carry an Idempotency-Key derived from the pack's bundle hash, so a retry after a timeout is the
  same request, never a second application. One retry is made on timeout, with the same key.
* Provider responses are validated; a malformed or mismatched response is refused, never "repaired".
* Webhooks must carry a valid HMAC-SHA256 signature over "timestamp.body", be at most 5 minutes old and
  are processed once (duplicates by event id are acknowledged and ignored). Status moves only forward.
* A simulated quote is never shown as a lender offer: source_type is part of every quote and of the UI label.
No real lender API is called by this repository; the sandbox adapter is exercised against a mock transport.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

QUOTE_STATES = ("OPEN", "ACCEPTED", "DECLINED", "EXPIRED", "WITHDRAWN", "FUNDED")
_FORWARD = {"OPEN": {"ACCEPTED", "DECLINED", "EXPIRED", "WITHDRAWN"}, "ACCEPTED": {"FUNDED", "WITHDRAWN", "DECLINED"},
            "DECLINED": set(), "EXPIRED": set(), "WITHDRAWN": set(), "FUNDED": set()}
WEBHOOK_TOLERANCE_S = 300
AMOUNT_TOLERANCE_USD = Decimal("0.01")


class LenderUnavailable(ConnectionError):
    """Provider timed out or is unreachable (after the one idempotent retry)."""


class LenderResponseError(ValueError):
    """Provider answered with something we must not use."""


def _cents(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class QuoteRequest:
    pack_id: str
    bundle_sha256: str
    product: str  # "factoring" | "loan"
    invoice_no: str
    invoice_usd: Decimal
    requested_usd: Decimal
    days: int
    drawdown_date: date

    def idempotency_key(self, action: str) -> str:
        return hashlib.sha256(f"{action}|{self.pack_id}|{self.bundle_sha256}|{self.product}|{self.requested_usd}".encode()).hexdigest()[:32]


@dataclass
class Quote:
    provider_id: str
    quote_id: str
    product: str
    principal_usd: Decimal
    fees_usd: Decimal
    interest_usd: Decimal
    rate_pa_pct: Decimal
    drawdown_date: date
    expires_at: datetime
    source_type: str  # "simulated" | "provider_issued"
    environment: str  # "mock" | "sandbox" | "live"
    status: str = "OPEN"
    pack_id: str = ""
    raw_sha256: str = ""
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.source_type not in ("simulated", "provider_issued"):
            raise ValueError("source_type must be simulated or provider_issued")
        if self.status not in QUOTE_STATES:
            raise ValueError(f"unknown quote status {self.status}")
        if self.principal_usd <= 0 or self.fees_usd < 0 or self.interest_usd < 0:
            raise ValueError("quote amounts out of range")

    @property
    def total_cost_usd(self) -> Decimal:
        return self.fees_usd + self.interest_usd

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return (now or datetime.now(timezone.utc)) >= self.expires_at

    def label(self) -> str:
        if self.source_type == "simulated":
            return "SIMULATED quote from the MOCK catalogue - not a lender offer"
        return f"Quote issued by {self.provider_id} ({self.environment.upper()})" + ("" if self.environment == "live" else " - test environment, not a binding offer")

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
            elif isinstance(v, (date, datetime)):
                d[k] = v.isoformat()
        d.update(total_cost_usd=str(self.total_cost_usd), label=self.label())
        return d


# --------------------------------------------------------------------------- adapters
class MockLenderAdapter:
    """Quotes from the MOCK catalogue terms; never presented as an offer."""

    provider_id = "partner-factor-mock"
    environment = "mock"

    def __init__(self, catalog: Any, validity: timedelta = timedelta(hours=24), clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.catalog, self.validity, self.clock = catalog, validity, clock

    def request_quote(self, req: QuoteRequest) -> Quote:
        if req.product == "factoring":
            t = self.catalog.factoring
            principal = _cents(req.invoice_usd * Decimal(str(t.advance_pct)) / 100)
            fees = _cents(req.invoice_usd * Decimal(str(t.fee_pct_of_invoice)) / 100)
            rate = Decimal(str(t.interest_pa_pct))
        elif req.product == "loan":
            t = self.catalog.bridge_loan
            principal = _cents(t.amount_usd)
            fees = _cents(principal * Decimal(str(t.upfront_fee_pct)) / 100)
            rate = Decimal(str(t.interest_pa_pct))
        else:
            raise ValueError(f"no mock terms for product {req.product}")
        interest = _cents(principal * rate / 100 * req.days / 365)
        body = {"product": req.product, "principal": str(principal), "fees": str(fees), "interest": str(interest), "pack": req.pack_id}
        qid = "MQ-" + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10].upper()
        now = self.clock()
        return Quote(self.provider_id, qid, req.product, principal, fees, interest, rate, req.drawdown_date, now + self.validity,
                     "simulated", "mock", pack_id=req.pack_id, raw_sha256=hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
                     received_at=now)

    def submit(self, pack_payload: Dict[str, Any]) -> str:
        from api import lender_connector_mock
        return lender_connector_mock.submit(pack_payload)


class SandboxHttpAdapter:
    """A provider's HTTP API (sandbox). The transport is injectable so contract tests never touch a network."""

    environment = "sandbox"

    def __init__(self, base_url: str, api_key: str, provider_id: str = "sandbox-lender", timeout_s: float = 5.0,
                 transport: Any = None, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        import httpx
        if not (base_url.startswith("https://") or base_url.startswith(("http://localhost", "http://127.0.0.1"))):
            raise ValueError("CASHBRIDGE_LENDER_BASE_URL must use https")
        if not api_key:
            raise ValueError("CASHBRIDGE_LENDER_API_KEY is required for the sandbox adapter")
        self.provider_id, self.clock = provider_id, clock
        self._httpx = httpx
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport,
                                   headers={"Authorization": f"Bearer {api_key}", "User-Agent": "CashBridge/9"})

    def _post(self, path: str, body: Dict[str, Any], key: str) -> Dict[str, Any]:
        last: Optional[Exception] = None
        for _ in range(2):  # one retry, same Idempotency-Key: the provider must treat it as the same request
            try:
                r = self.client.post(path, json=body, headers={"Idempotency-Key": key})
            except (self._httpx.TimeoutException, self._httpx.TransportError) as exc:
                last = exc
                continue
            if r.status_code >= 500:
                last = LenderUnavailable(f"provider returned {r.status_code}")
                continue
            if r.status_code >= 400:
                raise LenderResponseError(f"provider refused the request ({r.status_code})")
            try:
                data = r.json()
            except ValueError as exc:
                raise LenderResponseError("provider response is not JSON") from exc
            if not isinstance(data, dict):
                raise LenderResponseError("provider response is not an object")
            return data
        raise LenderUnavailable(f"provider unavailable ({type(last).__name__})") from last

    def request_quote(self, req: QuoteRequest) -> Quote:
        body = {"product": req.product, "reference": req.pack_id, "invoice_no": req.invoice_no, "invoice_amount_usd": str(req.invoice_usd),
                "requested_amount_usd": str(req.requested_usd), "tenor_days": req.days, "drawdown_date": req.drawdown_date.isoformat()}
        data = self._post("/v1/quotes", body, req.idempotency_key("quote"))
        try:
            q = Quote(self.provider_id, str(data["quote_id"]), str(data["product"]), _cents(data["principal_usd"]), _cents(data["fees_usd"]),
                      _cents(data["interest_usd"]), Decimal(str(data["rate_pa_pct"])), date.fromisoformat(data["drawdown_date"]),
                      datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")), "provider_issued", self.environment,
                      status=str(data.get("status", "OPEN")).upper(), pack_id=req.pack_id,
                      raw_sha256=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(), received_at=self.clock())
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise LenderResponseError(f"provider quote is malformed ({type(exc).__name__}: {exc})") from exc
        if q.product != req.product:
            raise LenderResponseError("provider quoted a different product")
        if q.principal_usd - req.requested_usd > AMOUNT_TOLERANCE_USD:
            raise LenderResponseError("provider quoted more than was requested")
        if q.expires_at.tzinfo is None or q.is_expired(self.clock()):
            raise LenderResponseError("provider quote is already expired or has no time zone")
        return q

    def submit(self, pack_payload: Dict[str, Any]) -> str:
        key = hashlib.sha256(f"submit|{pack_payload['pack_id']}|{pack_payload['bundle_sha256']}".encode()).hexdigest()[:32]
        data = self._post("/v1/applications", {k: pack_payload[k] for k in ("pack_id", "invoice_no", "option_id", "bundle_sha256", "amount_usd")}, key)
        ref = data.get("application_id")
        if not isinstance(ref, str) or not 3 <= len(ref) <= 80:
            raise LenderResponseError("provider did not return an application id")
        return ref


def adapter_from_env(catalog: Any, env: Optional[Mapping[str, str]] = None, transport: Any = None):
    import os
    source = os.environ if env is None else env
    kind = source.get("CASHBRIDGE_LENDER_ADAPTER", "mock").strip().lower() or "mock"
    if kind == "mock":
        return MockLenderAdapter(catalog)
    if kind == "sandbox_http":
        return SandboxHttpAdapter(source.get("CASHBRIDGE_LENDER_BASE_URL", ""), source.get("CASHBRIDGE_LENDER_API_KEY", ""),
                                  provider_id=source.get("CASHBRIDGE_LENDER_PROVIDER_ID", "sandbox-lender"),
                                  timeout_s=float(source.get("CASHBRIDGE_LENDER_TIMEOUT_S", "5")), transport=transport)
    raise ValueError(f"CASHBRIDGE_LENDER_ADAPTER={kind!r} is not recognised (mock | sandbox_http)")


# --------------------------------------------------------------------------- quote book + webhooks
def sign_webhook(secret: str, body: bytes, ts: int) -> str:
    return "t=%d,v1=%s" % (ts, hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest())


class QuoteBook:
    """Persisted quotes and processed webhook events (SQLite, shared by all worker processes)."""

    def __init__(self, path: str | Path, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.path, self.clock = str(path), clock
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.executescript("""CREATE TABLE IF NOT EXISTS quotes (quote_id TEXT PRIMARY KEY, provider_id TEXT NOT NULL, pack_id TEXT NOT NULL,
                  body TEXT NOT NULL, status TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS webhook_events (event_id TEXT PRIMARY KEY, provider_id TEXT NOT NULL, received TEXT NOT NULL,
                  outcome TEXT NOT NULL);""")

    def _con(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def save(self, q: Quote) -> Dict[str, Any]:
        with self._con() as con:
            con.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?) ON CONFLICT(quote_id) DO UPDATE SET body=excluded.body, updated=excluded.updated",
                        (q.quote_id, q.provider_id, q.pack_id, json.dumps(q.as_dict()), q.status, self.clock().isoformat()))
        return self.get(q.quote_id)

    def get(self, quote_id: str) -> Dict[str, Any]:
        with self._con() as con:
            row = con.execute("SELECT * FROM quotes WHERE quote_id=?", (quote_id,)).fetchone()
        if row is None:
            raise LookupError("unknown quote")
        d = json.loads(row["body"])
        status = row["status"]
        if status == "OPEN" and datetime.fromisoformat(d["expires_at"]) <= self.clock():
            status = "EXPIRED"
        return {**d, "status": status}

    def list(self, pack_id: str) -> List[Dict[str, Any]]:
        with self._con() as con:
            ids = [r["quote_id"] for r in con.execute("SELECT quote_id FROM quotes WHERE pack_id=? ORDER BY updated", (pack_id,))]
        return [self.get(i) for i in ids]

    def transition(self, quote_id: str, new: str) -> Dict[str, Any]:
        new = new.upper()
        current = self.get(quote_id)
        if new == "ACCEPTED" and current["status"] == "EXPIRED":
            raise ValueError("Quote has expired; request a new quote")
        if new not in _FORWARD.get(current["status"], set()):
            raise ValueError(f"Quote is {current['status']}; it cannot become {new}")
        with self._con() as con:
            con.execute("UPDATE quotes SET status=?, updated=? WHERE quote_id=?", (new, self.clock().isoformat(), quote_id))
        return self.get(quote_id)

    def accept(self, quote_id: str) -> Dict[str, Any]:
        return self.transition(quote_id, "ACCEPTED")

    def receive_webhook(self, secret: str, body: bytes, signature: str, provider_id: str) -> Dict[str, Any]:
        """Verify, deduplicate and apply one provider status callback. Raises PermissionError for a bad signature."""
        if not secret:
            raise PermissionError("webhooks are not configured")
        try:
            parts = dict(p.split("=", 1) for p in signature.split(","))
            ts = int(parts["t"])
            given = parts["v1"]
        except (ValueError, KeyError):
            raise PermissionError("malformed signature header") from None
        expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, given):
            raise PermissionError("bad signature")
        if abs(self.clock().timestamp() - ts) > WEBHOOK_TOLERANCE_S:
            raise PermissionError("stale webhook (replay window exceeded)")
        try:
            event = json.loads(body)
            event_id, quote_id, status = str(event["event_id"]), str(event["quote_id"]), str(event["status"]).upper()
        except (ValueError, KeyError, TypeError):
            raise ValueError("malformed webhook body") from None
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM webhook_events WHERE event_id=?", (event_id,)).fetchone():
                return {"event_id": event_id, "duplicate": True, "applied": False}
            con.execute("INSERT INTO webhook_events VALUES (?,?,?,?)", (event_id, provider_id, self.clock().isoformat(), "received"))
        try:
            q = self.get(quote_id)
            if q["provider_id"] != provider_id:
                raise ValueError("quote belongs to another provider")
            result = {"event_id": event_id, "duplicate": False, "applied": True, "quote": self.transition(quote_id, status)}
            outcome = f"applied {status}"
        except (LookupError, ValueError) as exc:
            result = {"event_id": event_id, "duplicate": False, "applied": False, "reason": str(exc)}
            outcome = f"ignored: {exc}"
        with self._con() as con:
            con.execute("UPDATE webhook_events SET outcome=? WHERE event_id=?", (outcome[:200], event_id))
        return result


def default_book_path() -> Path:
    """One quote book per installation, shared by the API workers and the webhook receiver."""
    import os
    from config import runtime_mode
    configured = os.environ.get("CASHBRIDGE_LENDER_QUOTES_DB", "").strip()
    return Path(configured) if configured else runtime_mode.runtime_dir(Path(__file__).resolve().parents[1]) / "lender_quotes.sqlite3"


def now_ts() -> int:
    return int(time.time())
