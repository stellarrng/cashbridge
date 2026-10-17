"""Buyer risk agent (Step 6.1)."""

import copy
import json
from decimal import Decimal

import pytest

from agents.buyer_risk_agent import GRACE_DAYS, BuyerRiskAgent
from agents.cfo_assistant import CfoAssistant
from agents.coordinator import Coordinator
from config.settings import CONCENTRATION_ALERT_PCT
from core.metrics import receivable_shares_pct
from data import loader, seed_sandbox
from scripts.run_demo_story import StoryClock


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("risk_inputs")
    seed_sandbox.write_all(folder)
    return folder


@pytest.fixture(scope="module")
def history(inputs):
    return loader.read("payment_history.json", inputs)["records"]


@pytest.fixture(scope="module")
def invoices(inputs):
    return {i.invoice_no: i for i in loader.invoices(inputs)}


def coordinator(inputs, tmp_path):
    c = Coordinator(inputs_dir=inputs, evidence_dir=tmp_path / "e", cases_dir=tmp_path / "c", clock=StoryClock())
    c.weekly_run()
    return c


def test_the_model_is_reproducible(history, invoices):
    a, b = BuyerRiskAgent(history), BuyerRiskAgent(copy.deepcopy(history))
    assert a.model.describe() == b.model.describe()
    assert {n: a.p_on_time(i) for n, i in invoices.items()} == {n: b.p_on_time(i) for n, i in invoices.items()}


def test_coefficients_are_reported_and_can_be_read(history):
    description = BuyerRiskAgent(history).model.describe()
    names = [c["name"] for c in description["coefficients"]]
    assert names == ["buyer B-CN-01", "buyer B-JP-01", "buyer B-US-01", "terms_30_days", "size_vs_usual"]
    weights = {c["name"]: c["coefficient"] for c in description["coefficients"]}
    assert weights["size_vs_usual"] < -1.0  # an invoice much bigger than usual is paid later
    assert weights["buyer B-US-01"] < weights["buyer B-JP-01"]  # the US buyer pays later than the Japanese buyer
    assert description["training_rows"] == len(history) and f"{GRACE_DAYS} days" in description["on_time_definition"]


def test_probabilities_follow_invoice_size_and_buyer(history, invoices):
    agent = BuyerRiskAgent(history)
    p = {n: agent.p_on_time(i) for n, i in invoices.items()}
    assert p["INV-1037"] < 0.2 < p["INV-1026"] < p["INV-1021"]  # 2.4x usual size is very unlikely to be on time
    assert p["INV-1028"] > p["INV-1026"]  # the Japanese buyer is more reliable than the US buyer for a similar size
    assert all(0.0 <= v <= 1.0 for v in p.values())


def test_a_buyer_with_no_history_gets_the_portfolio_average_and_is_marked(history, invoices):
    agent = BuyerRiskAgent(history)
    assert not agent.has_history("B-US-02") and agent.p_on_time(invoices["INV-1031"]) == agent.p_on_time(invoices["INV-1032"])
    known = [agent.p_on_time(i) for i in invoices.values() if agent.has_history(i.buyer_id)]
    assert min(known) <= agent.p_on_time(invoices["INV-1031"]) <= max(known)


def test_average_days_late_counts_early_payments_as_zero(history):
    agent = BuyerRiskAgent(history)
    rows = [r for r in history if r["buyer_id"] == "B-US-01"]
    assert agent.average_days_late("B-US-01") == round(sum(max(0, r["days_late"]) for r in rows) / len(rows), 1)
    assert agent.average_days_late("B-US-02") is None


def test_the_main_us_buyer_triggers_the_concentration_alert(inputs, tmp_path):
    rows = {r["buyer_id"]: r for r in coordinator(inputs, tmp_path).buyer_risk_rows()}
    assert rows["B-US-01"]["concentration_alert"] and rows["B-US-01"]["share_of_receivables_pct"] > float(CONCENTRATION_ALERT_PCT)
    assert [k for k, r in rows.items() if r["concentration_alert"]] == ["B-US-01"]
    assert rows["B-US-02"]["has_history"] is False and rows["B-US-01"]["has_history"] is True


def test_shares_add_up_to_one_hundred_percent(inputs, tmp_path):
    receivables = coordinator(inputs, tmp_path).forecast_inputs.receivables
    assert abs(sum(receivable_shares_pct(receivables).values()) - Decimal(100)) <= Decimal("0.3")


def test_rows_have_the_contract_shape_and_are_sorted_by_share(inputs, tmp_path):
    rows = coordinator(inputs, tmp_path).buyer_risk_rows()
    assert set(rows[0]) >= {"buyer", "share_of_receivables_pct", "avg_days_late", "p_on_time", "concentration_alert"}
    shares = [r["share_of_receivables_pct"] for r in rows]
    assert shares == sorted(shares, reverse=True)


def test_the_forecast_uses_the_model_probabilities(inputs, tmp_path, history):
    c = coordinator(inputs, tmp_path)
    agent = BuyerRiskAgent(history)
    for receivable in c.forecast_inputs.receivables:
        invoice = next(i for i in c.all_invoices if i.invoice_no == receivable.invoice_id)
        assert receivable.p_on_time == agent.p_on_time(invoice)


def test_better_payment_history_changes_the_forecast(inputs, tmp_path, history):
    baseline = coordinator(inputs, tmp_path / "a")
    better = tmp_path / "better"
    seed_sandbox.write_all(better)
    records = json.loads((better / "payment_history.json").read_text())
    for record in records["records"]:
        record["days_late"] = -5  # every past invoice was paid early
    (better / "payment_history.json").write_text(json.dumps(records))
    improved = coordinator(better, tmp_path / "b")
    assert improved.p_on_time["INV-1026"] > baseline.p_on_time["INV-1026"]
    assert improved.forecast.shortfall_usd != baseline.forecast.shortfall_usd


def test_the_agent_reads_history_and_scores_but_cannot_write(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    lines = [json.loads(l) for l in c.audit_path.read_text().splitlines()]
    mine = [(l["tool"], l["tier"]) for l in lines if l["agent"] == "buyer_risk_agent"]
    assert mine == [("read_payment_history", "L0_READ"), ("score_buyer_risk", "L1_ANALYZE")]


def test_the_cfo_assistant_names_the_riskiest_buyer_from_the_model(inputs, tmp_path):
    c = coordinator(inputs, tmp_path)
    text = CfoAssistant(c).ask("Which buyer is most at risk of paying late?")["text"]
    assert text.startswith("Oakline Home LLC (SYNTHETIC) carries the most late-payment risk")


def test_a_history_with_only_one_outcome_falls_back_to_a_smoothed_rate(history, invoices):
    all_on_time = [{**r, "days_late": -2} for r in history]
    agent = BuyerRiskAgent(all_on_time)
    assert agent.model.classifier is None and agent.model.coefficients == {}
    assert 0.9 < agent.p_on_time(invoices["INV-1026"]) < 1.0  # high but never exactly 1
    assert "smoothed" in agent.model.describe()["method"]
    all_late = BuyerRiskAgent([{**r, "days_late": 30} for r in history])
    assert 0.0 < all_late.p_on_time(invoices["INV-1026"]) < 0.1


def test_an_empty_history_gives_a_neutral_probability(invoices):
    agent = BuyerRiskAgent([])
    assert agent.p_on_time(invoices["INV-1026"]) == 0.5 and agent.table([], {}) == []
