"""Invoice registry and period lock (Step 1.4)."""

import json
from datetime import datetime, timezone

import pytest

from core.invoice_registry import GENESIS_HASH, DoubleFinancingBlocked, InvoiceRegistry, invoice_key
from core.period_lock import PeriodLocks
from tests.fixtures import make_invoice


def fixed_clock():
    return datetime(2026, 10, 19, 7, 0, tzinfo=timezone.utc)


def registry(tmp_path) -> InvoiceRegistry:
    return InvoiceRegistry(tmp_path / "invoice_registry.json", clock=fixed_clock)


def test_register_then_block_double_financing(tmp_path):
    reg = registry(tmp_path)
    invoice = make_invoice("INV-1030", "60000")
    assert not reg.is_registered(invoice)
    block = reg.register(invoice, "a" * 64, "LENDER-REF-1")
    assert block["block_index"] == 0 and block["previous_block_hash"] == GENESIS_HASH
    assert reg.is_registered(invoice)
    with pytest.raises(DoubleFinancingBlocked):
        reg.register(invoice, "a" * 64, "LENDER-REF-2")


def test_same_invoice_with_different_pdf_hash_is_still_blocked(tmp_path):
    reg = registry(tmp_path)
    invoice = make_invoice("INV-1030", "60000")
    reg.register(invoice, "a" * 64, "REF-1")
    rescanned = make_invoice("INV-1030", "60000")
    with pytest.raises(DoubleFinancingBlocked):
        reg.register(rescanned, "b" * 64, "REF-2")


def test_key_is_canonical_and_ignores_formatting():
    a = make_invoice("INV-1030", "60000")
    b = make_invoice(" inv-1030 ", "60000.00")
    assert invoice_key(a) == invoice_key(b)
    assert invoice_key(a) != invoice_key(make_invoice("INV-1030", "60000.01"))
    assert invoice_key(a) != invoice_key(make_invoice("INV-1030", "60000", buyer="B-OTHER"))


def test_different_invoice_is_allowed_and_chain_verifies(tmp_path):
    reg = registry(tmp_path)
    reg.register(make_invoice("INV-1030", "60000"), "a" * 64, "R1")
    reg.register(make_invoice("INV-1031", "5000"), "b" * 64, "R2")
    assert reg.verify_chain() == (True, None)
    assert len(reg.blocks()) == 2
    assert reg.head_hash() == reg.blocks()[-1]["block_hash"]


def test_edited_block_is_detected_at_its_index(tmp_path):
    reg = registry(tmp_path)
    for n in range(3):
        reg.register(make_invoice(f"INV-20{n}", "1000"), "a" * 64, f"R{n}")
    chain = json.loads(reg.path.read_text())
    chain[1]["lender_ref"] = "EDITED"
    reg.path.write_text(json.dumps(chain))
    assert reg.verify_chain() == (False, 1)


def test_removed_block_is_detected(tmp_path):
    reg = registry(tmp_path)
    for n in range(3):
        reg.register(make_invoice(f"INV-20{n}", "1000"), "a" * 64, f"R{n}")
    chain = json.loads(reg.path.read_text())
    del chain[0]
    reg.path.write_text(json.dumps(chain))
    assert reg.verify_chain() == (False, 0)


def test_empty_registry_verifies(tmp_path):
    assert registry(tmp_path).verify_chain() == (True, None)


def test_period_lock_detects_changed_row():
    locks = PeriodLocks()
    rows = [{"txn": "TXN-1", "amount": 100}, {"txn": "TXN-2", "amount": 200}]
    record = locks.lock("2026-10", rows)
    assert record.version == 1 and locks.verify("2026-10", rows)
    assert not locks.verify("2026-10", [{"txn": "TXN-1", "amount": 101}, rows[1]])
    assert not locks.verify("2026-11", rows)


def test_period_lock_change_creates_next_version_and_same_rows_do_not():
    locks = PeriodLocks()
    rows = [{"a": 1}]
    first = locks.lock("p", rows)
    assert locks.lock("p", rows) == first
    second = locks.lock("p", [{"a": 2}])
    assert second.version == 2 and second.previous_lock_sha256 == first.lock_sha256
    assert locks.verify("p", [{"a": 2}]) and not locks.verify("p", rows)
