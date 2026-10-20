"""Lender adapter contract: neutral quotes, config switching, timeouts, idempotency, signed/deduplicated webhooks, expiry."""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from api.lender_adapters import (LenderResponseError, LenderUnavailable, MockLenderAdapter, QuoteBook, QuoteRequest,
                                 SandboxHttpAdapter, adapter_from_env, sign_webhook)
from data import loader

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
REQ = QuoteRequest(pack_id="PACK-1", bundle_sha256="ab" * 32, product="factoring", invoice_no="INV-1030", invoice_usd=Decimal("60000.00"),
                   requested_usd=Decimal("48000.00"), days=60, drawdown_date=date(2026, 10, 19))


def provider_quote(**over):
    q = {"quote_id": "Q-77", "product": "factoring", "principal_usd": "48000.00", "fees_usd": "700.00", "interest_usd": "600.00",
         "rate_pa_pct": "7.6", "drawdown_date": "2026-10-19", "expires_at": "2026-10-20T09:00:00Z", "status": "open"}
    q.update(over)
    return q


def sandbox(handler, **kw):
    return SandboxHttpAdapter("https://sandbox.lender.example", "k", transport=httpx.MockTransport(handler), clock=lambda: NOW, **kw)


def test_mock_quotes_reproduce_the_catalogue_and_are_labelled_simulated():
    q = MockLenderAdapter(loader.lender_catalog(), clock=lambda: NOW).request_quote(REQ)
    assert (q.principal_usd, q.fees_usd, q.interest_usd) == (Decimal("48000.00"), Decimal("720.00"), Decimal("631.23"))  # = funding page
    assert q.source_type == "simulated" and "not a lender offer" in q.label() and q.expires_at == NOW + timedelta(hours=24)
    assert MockLenderAdapter(loader.lender_catalog()).submit({"pack_id": "P", "invoice_no": "I", "option_id": "o", "bundle_sha256": "b",
                                                             "amount_usd": "1"}).startswith("MOCK-")


def test_config_switches_adapter_without_code_changes():
    cat = loader.lender_catalog()
    assert isinstance(adapter_from_env(cat, {}), MockLenderAdapter)
    env = {"CASHBRIDGE_LENDER_ADAPTER": "sandbox_http", "CASHBRIDGE_LENDER_BASE_URL": "https://sandbox.lender.example", "CASHBRIDGE_LENDER_API_KEY": "k"}
    assert isinstance(adapter_from_env(cat, env, transport=httpx.MockTransport(lambda r: httpx.Response(200))), SandboxHttpAdapter)
    with pytest.raises(ValueError):
        adapter_from_env(cat, {"CASHBRIDGE_LENDER_ADAPTER": "live_magic"})
    with pytest.raises(ValueError):
        adapter_from_env(cat, {**env, "CASHBRIDGE_LENDER_BASE_URL": "http://lender.example"})  # no plain http
    with pytest.raises(ValueError):
        adapter_from_env(cat, {**env, "CASHBRIDGE_LENDER_API_KEY": ""})


def test_provider_quote_is_parsed_into_the_neutral_schema():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=provider_quote())
    q = sandbox(handler).request_quote(REQ)
    assert q.source_type == "provider_issued" and q.environment == "sandbox" and q.status == "OPEN"
    assert q.total_cost_usd == Decimal("1300.00") and "test environment, not a binding offer" in q.label()
    body = json.loads(seen[0].content)
    assert body["requested_amount_usd"] == "48000.00" and seen[0].headers["authorization"] == "Bearer k"
    assert len(seen[0].headers["idempotency-key"]) == 32


def test_timeout_is_retried_once_with_the_same_idempotency_key_then_reported():
    keys = []

    def flaky(request):
        keys.append(request.headers["idempotency-key"])
        if len(keys) == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=provider_quote())
    assert sandbox(flaky).request_quote(REQ).quote_id == "Q-77"
    assert len(keys) == 2 and keys[0] == keys[1]  # the retry is the same request

    def down(request):
        raise httpx.ConnectTimeout("down", request=request)
    with pytest.raises(LenderUnavailable):
        sandbox(down).request_quote(REQ)
    with pytest.raises(LenderUnavailable):
        sandbox(lambda r: httpx.Response(503)).request_quote(REQ)


@pytest.mark.parametrize("bad", [
    {"principal_usd": "not-a-number"}, {"product": "loan"}, {"principal_usd": "50000.00"},
    {"expires_at": "2026-10-19T08:00:00Z"}, {"expires_at": "2026-10-20T09:00:00"}, {"fees_usd": "-1"}, {"status": "teleported"},
])
def test_malformed_or_inconsistent_provider_quotes_are_refused(bad):
    with pytest.raises(LenderResponseError):
        sandbox(lambda r: httpx.Response(200, json=provider_quote(**bad))).request_quote(REQ)


def test_non_json_and_4xx_are_refused_not_retried():
    calls = []

    def h(request):
        calls.append(1)
        return httpx.Response(422, json={"error": "bad"})
    with pytest.raises(LenderResponseError):
        sandbox(h).request_quote(REQ)
    assert len(calls) == 1
    with pytest.raises(LenderResponseError):
        sandbox(lambda r: httpx.Response(200, text="<html>")).request_quote(REQ)


def test_sandbox_submission_is_idempotent_by_bundle():
    keys = []

    def h(request):
        keys.append(request.headers["idempotency-key"])
        return httpx.Response(200, json={"application_id": "APP-" + request.headers["idempotency-key"][:6]})
    a = sandbox(h)
    payload = {"pack_id": "PACK-1", "invoice_no": "INV-1030", "option_id": "factoring_inv1030", "bundle_sha256": "ab" * 32, "amount_usd": "48000.00"}
    assert a.submit(payload) == a.submit(payload) and keys[0] == keys[1]
    with pytest.raises(LenderResponseError):
        sandbox(lambda r: httpx.Response(200, json={"application_id": 7})).submit(payload)


# --------------------------------------------------------------------------- quote book + webhooks
@pytest.fixture
def book(tmp_path):
    clock = {"now": NOW}
    b = QuoteBook(tmp_path / "q.db", clock=lambda: clock["now"])
    q = sandbox(lambda r: httpx.Response(200, json=provider_quote())).request_quote(REQ)
    b.save(q)
    return b, clock


def test_expired_quote_cannot_be_accepted(book):
    b, clock = book
    clock["now"] = NOW + timedelta(days=2)
    assert b.get("Q-77")["status"] == "EXPIRED"
    with pytest.raises(ValueError, match="expired"):
        b.accept("Q-77")


def test_status_only_moves_forward(book):
    b, _ = book
    assert b.accept("Q-77")["status"] == "ACCEPTED"
    with pytest.raises(ValueError):
        b.transition("Q-77", "OPEN")


def test_webhooks_are_verified_deduplicated_and_replay_limited(book):
    b, clock = book
    secret, ts = "whsec", int(NOW.timestamp())
    body = json.dumps({"event_id": "EV-1", "quote_id": "Q-77", "status": "accepted"}).encode()
    with pytest.raises(PermissionError):
        b.receive_webhook(secret, body, sign_webhook("wrong", body, ts), "sandbox-lender")
    with pytest.raises(PermissionError):
        b.receive_webhook(secret, body, "garbage", "sandbox-lender")
    with pytest.raises(PermissionError):
        b.receive_webhook(secret, body, sign_webhook(secret, body, ts - 3600), "sandbox-lender")  # replayed later
    with pytest.raises(PermissionError):
        b.receive_webhook("", body, sign_webhook(secret, body, ts), "sandbox-lender")
    first = b.receive_webhook(secret, body, sign_webhook(secret, body, ts), "sandbox-lender")
    assert first["applied"] and first["quote"]["status"] == "ACCEPTED"
    again = b.receive_webhook(secret, body, sign_webhook(secret, body, ts), "sandbox-lender")
    assert again == {"event_id": "EV-1", "duplicate": True, "applied": False}
    other = json.dumps({"event_id": "EV-2", "quote_id": "Q-77", "status": "funded"}).encode()
    assert b.receive_webhook(secret, other, sign_webhook(secret, other, ts), "another-lender")["applied"] is False  # not its quote
    unknown = json.dumps({"event_id": "EV-3", "quote_id": "Q-NOPE", "status": "funded"}).encode()
    assert b.receive_webhook(secret, unknown, sign_webhook(secret, unknown, ts), "sandbox-lender")["applied"] is False
    funded = json.dumps({"event_id": "EV-4", "quote_id": "Q-77", "status": "funded"}).encode()
    assert b.receive_webhook(secret, funded, sign_webhook(secret, funded, ts), "sandbox-lender")["quote"]["status"] == "FUNDED"


def test_quote_book_is_shared_across_instances(book, tmp_path):
    b, _ = book
    assert QuoteBook(tmp_path / "q.db", clock=lambda: NOW).get("Q-77")["source_type"] == "provider_issued"


def test_financing_engine_is_unchanged_by_the_adapter_layer():
    from core.funding_evaluator import FundingRequest, rank_options  # noqa: F401  the engine keeps its own contract
    import api.lender_adapters as la
    assert "funding_evaluator" not in open(la.__file__).read()
