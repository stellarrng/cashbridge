"""The real backend honours the UI contract (Step 3.5)."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.export_ui_snapshot import export
from scripts.run_demo_story import StoryClock
from security.audit_log import AuditLog
from ui.backend_real import RealBackend

CONTRACT = Path(__file__).resolve().parent.parent / "docs" / "UI_CONTRACT.md"


def sample_snapshot():
    text = CONTRACT.read_text(encoding="utf-8")
    return json.loads(re.search(r"```json\n(.*?)```", text, re.S).group(1))


FREE_FORM = ("assumptions", "cost_breakdown")  # contents differ per option type; only the object is required


def problems(sample, real, path="$"):
    """Every place where ``real`` lacks a key of ``sample`` or has an incompatible type."""
    if sample is None or real is None:  # null is allowed wherever a value may be absent
        return []
    if isinstance(sample, bool):
        return [] if isinstance(real, bool) else [f"{path}: expected bool"]
    if isinstance(sample, (int, float)):
        return [] if isinstance(real, (int, float)) and not isinstance(real, bool) else [f"{path}: expected number"]
    if isinstance(sample, str):
        return [] if isinstance(real, str) else [f"{path}: expected string, got {type(real).__name__}"]
    if isinstance(sample, dict):
        if not isinstance(real, dict):
            return [f"{path}: expected object"]
        if path.endswith(FREE_FORM):
            return []
        found = []
        for key, value in sample.items():
            if key not in real:
                found.append(f"{path}.{key}: missing")
            else:
                found += problems(value, real[key], f"{path}.{key}")
        return found
    if isinstance(sample, list):
        if not isinstance(real, list):
            return [f"{path}: expected list"]
        found = []
        if sample and real:
            for index, item in enumerate(real):
                found += problems(sample[0], item, f"{path}[{index}]")
        return found
    return []


@pytest.fixture
def backend(tmp_path):
    return RealBackend(runtime_dir=tmp_path, clock=StoryClock())


def test_real_snapshot_has_every_contract_key_with_compatible_types(backend):
    assert problems(sample_snapshot(), backend.get_snapshot()) == []


def test_snapshot_is_json_serialisable(backend):
    assert json.loads(json.dumps(backend.get_snapshot()))["meta"]["synthetic"] is True


def test_snapshot_carries_the_real_story_numbers(backend):
    snap = backend.get_snapshot()
    assert snap["meta"]["mode"] == "offline-demo" and snap["meta"]["case_state"] == "INVOICE_VERIFIED"
    assert snap["kpis"]["ccc"]["ccc"] == 82.0
    assert snap["kpis"]["first_shortfall_week"] == 7 and 40000 <= snap["kpis"]["shortfall_usd"] <= 47000
    assert snap["kpis"]["blocked_fraud_count"] == 1
    assert snap["kpis"]["cash_today_vnd"] == int(snap["kpis"]["cash_today_usd"] * 26000)
    assert [o["id"] for o in snap["funding_options"]][:3] == ["factoring_inv1030", "bridge_loan", "early_discount"]
    assert {a["type"] for a in snap["alerts"]} == {"BEC", "INJECTION"}
    wire = snap["reconciliation"]["featured_wire"]
    assert wire["gap"] == 35 and wire["invoice_total"] - wire["received"] == 35
    assert [i["id"] for i in wire["invoices"]] == ["INV-1021", "INV-1022", "INV-1024"]
    assert snap["buyer_risk"] == []
    assert snap["evidence"]["eval"]["passed"] == snap["evidence"]["eval"]["total"] >= 15


def test_every_week_row_adds_up(backend):
    for row in backend.get_snapshot()["forecast"]["weeks"]:
        assert round(row["opening"] + row["inflows"] - row["outflows"], 2) == round(row["closing"], 2)


def test_pii_inspector_shows_the_masked_bec_email(backend):
    pii = backend.get_snapshot()["pii_inspector"]
    assert "GB29" in pii["before"] and "GB29" not in pii["after"] and "[ACCT_1]" in pii["after"]
    assert "nothing was sent" in pii["note"]


def test_simulate_returns_forecast_kpis_and_delta(backend):
    out = backend.simulate({"dso_change_days": 15, "deposit_pct": 30, "tariff_shared_pct": 0, "fx_change_pct": 0})
    assert set(out) == {"forecast", "kpis", "delta"}
    assert set(out["delta"]) == {
        "first_shortfall_week_before", "first_shortfall_week_after", "min_closing_before_usd", "min_closing_after_usd",
    }
    assert out["delta"]["min_closing_after_usd"] < out["delta"]["min_closing_before_usd"]
    assert len(out["forecast"]["weeks"]) == 13
    with pytest.raises(ValueError):
        backend.simulate({"dso_change_days": 99})


def test_full_click_through(backend):
    snap = backend.choose_option("factoring_inv1030")
    assert snap["selected_option_id"] == "factoring_inv1030" and snap["meta"]["last_error"] is None
    snap = backend.prepare_pack()
    assert snap["pack"]["status"] == "AWAITING_APPROVAL" and snap["pack"]["number_check"]["ok"]
    assert snap["pack"]["pdf_path"] == f"packs/{snap['pack']['pack_id']}.pdf"
    challenge = backend.request_otp()
    assert set(challenge) == {"action_hash", "expires_at", "instructions"}
    assert challenge["action_hash"] == snap["pack"]["action_hash"]
    assert backend.tamper_draft()["ok"] is False
    bad = backend.approve("000000" if backend.coord.otp.current_code() != "000000" else "111111")
    assert bad["ok"] is False and bad["error"] == "invalid_code" and bad["snapshot"]["meta"]["case_state"] == "AWAITING_APPROVAL"
    good = backend.approve(backend.coord.otp.current_code())
    assert good["ok"] and good["snapshot"]["meta"]["case_state"] == "SUBMITTED"
    assert good["snapshot"]["pack"]["lender_ref"].startswith("MOCK-")
    assert len(good["snapshot"]["evidence"]["registry_blocks"]) == 1
    again = backend.retry_double_financing()
    assert again["blocked"] and again["error"] == "DoubleFinancingBlocked"
    assert backend.verify_chain()["ok"]


def test_refusals_are_reported_in_meta_not_raised(backend):
    snap = backend.choose_option("overdraft")
    assert "not available" in snap["meta"]["last_error"]
    backend.choose_option("early_discount")
    assert "no lender pack" in backend.prepare_pack()["meta"]["last_error"]
    assert backend.choose_option("bridge_loan")["meta"]["last_error"] is None


def test_tamper_demo_breaks_a_temporary_copy_only(backend):
    before = backend.coord.audit_path.read_bytes()
    out = backend.tamper_demo()
    assert out["ok"] is False and out["broken_seq"] >= 1 and out["note"] == "temporary copy only"
    assert backend.coord.audit_path.read_bytes() == before
    assert backend.verify_chain()["ok"]


def test_reset_returns_a_fresh_snapshot(backend):
    backend.choose_option("factoring_inv1030")
    backend.prepare_pack()
    snap = backend.reset_demo()
    assert snap["meta"]["case_state"] == "INVOICE_VERIFIED" and snap["pack"]["status"] == "NOT_STARTED"
    assert snap["selected_option_id"] is None and snap["evidence"]["lines_checked"] == len(AuditLog(backend.coord.audit_path).tail(10_000))


def test_ask_cfo_returns_a_cited_message(backend):
    reply = backend.ask_cfo("When will I run out of cash?")
    assert reply["role"] == "assistant" and reply["citations"] and reply["mode"] == "offline-demo"
    assert len(backend.get_snapshot()["chat"]["history"]) == 3


def test_tier_monitor_shows_the_latest_decisions(backend):
    backend.choose_option("factoring_inv1030")
    backend.prepare_pack()
    backend.request_otp()
    monitor = backend.get_snapshot()["tier_monitor"]
    assert len(monitor) == 10 and monitor[-1]["tool"] == "submit_pack" and monitor[-1]["decision"] == "AWAITING_APPROVAL"


def test_export_script_writes_the_real_snapshot(tmp_path):
    first = export(tmp_path / "a.json")
    second = export(tmp_path / "b.json")
    assert first.read_bytes() == second.read_bytes()
    snap = json.loads(first.read_text())
    assert snap["kpis"]["first_shortfall_week"] == 7 and problems(sample_snapshot(), snap) == []


def test_a_new_backend_starts_a_fresh_session_even_if_old_evidence_exists(tmp_path):
    first = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    first.choose_option("factoring_inv1030")
    first.prepare_pack()
    assert first.approve(first.coord.otp.current_code())["ok"] if first.request_otp() else False
    assert first.get_snapshot()["evidence"]["registry_blocks"]
    second = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    snap = second.get_snapshot()
    assert snap["evidence"]["registry_blocks"] == [] and snap["meta"]["case_state"] == "INVOICE_VERIFIED"
    assert snap["funding_options"][0]["id"] == "factoring_inv1030"
