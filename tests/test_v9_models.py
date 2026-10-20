"""v9 research-backed models: censoring-aware payment timing, conformal intervals, behavioural cross-check."""

from datetime import date, timedelta

import numpy as np
import pytest

from core import conformal as cf
from core.payment_timing import EARLY_DAYS, Observation, PaymentTimingModel, observations_at, v8_rule_receipts

D0 = date(2026, 1, 1)


def test_kaplan_meier_matches_hand_calculation_with_censoring():
    # due D0 for all; paid 0, 0, 2 days late; one unpaid at the origin (D0 + 1): censored after day 1
    obs = [Observation("A", D0, D0), Observation("A", D0, D0), Observation("A", D0, D0 + timedelta(days=2)), Observation("A", D0, None)]
    m = PaymentTimingModel(obs, D0 + timedelta(days=1), prior_strength=0)
    h = m.pool_hazard
    assert h[EARLY_DAYS + 0] == pytest.approx(2 / 4)       # 4 at risk on day 0, 2 paid
    assert h[EARLY_DAYS + 1] == pytest.approx(0 / 2)       # 2 at risk on day 1 (the censored one included), none paid
    assert h[EARLY_DAYS + 2] == pytest.approx(1 / 1)       # censored one has left the risk set
    f = m.pmf("A")
    assert f.sum() == pytest.approx(1.0) and f[EARLY_DAYS] == pytest.approx(0.5)


def test_point_in_time_training_never_sees_future_payments():
    rows = [("A", D0, D0 + timedelta(days=30))]
    obs = observations_at(D0 + timedelta(days=10), rows)
    assert obs[0].paid is None  # paid after the origin: censored, not an event
    assert observations_at(D0 - timedelta(days=EARLY_DAYS + 1), rows) == []  # too far before due: no information


def test_conditioning_on_being_unpaid_moves_mass_later():
    obs = [Observation("A", D0, D0 + timedelta(days=d)) for d in (-5, 0, 0, 3, 10, 30)]
    m = PaymentTimingModel(obs, D0 + timedelta(days=60), prior_strength=0)
    f_all, f_late = m.pmf("A"), m.pmf("A", unpaid_through=5)
    assert f_late[: EARLY_DAYS + 6].sum() == 0 and f_late.sum() == pytest.approx(1.0)
    mean = lambda f: sum(i * p for i, p in enumerate(f))  # noqa: E731
    assert mean(f_late) > mean(f_all)


def test_weekly_receipts_conserve_the_amount():
    obs = [Observation("A", D0, D0 + timedelta(days=d)) for d in range(-10, 40, 3)]
    m = PaymentTimingModel(obs, D0 + timedelta(days=90), prior_strength=0)
    inside, after = m.weekly_receipts([("A", D0 + timedelta(days=20), 1000.0), ("B", D0 + timedelta(days=50), 500.0)], D0, 13)
    assert inside.sum() + after == pytest.approx(1500.0)


def test_v8_rule_reproduces_the_engine_split():
    out = v8_rule_receipts([("A", D0 + timedelta(days=14), 100.0, 0.75)], D0, 13)
    assert out[2] == 75.0 and out[6] == 25.0 and out.sum() == 100.0


def test_split_conformal_quantile_and_aci_update():
    assert cf.conformal_quantile(list(range(1, 10)), 0.2) == 8  # ceil(10*0.8)=8th smallest
    assert cf.conformal_quantile([1.0], 0.2) == float("inf")
    a = cf.ACI(alpha=0.2, gamma=0.1)
    a.update(covered=False, score=1.0)
    assert a.alpha_t == pytest.approx(0.2 + 0.1 * (0.2 - 1))  # alpha_{t+1} = alpha_t + gamma (alpha - err_t)
    a.update(covered=True, score=1.0)
    assert a.alpha_t == pytest.approx(0.12 + 0.1 * 0.2)


def test_aci_reaches_target_coverage_under_drift():
    rng = np.random.default_rng(3)
    aci = cf.ACI(alpha=0.2, gamma=0.05)
    hits = []
    for t in range(3000):
        scale = 1 + 2 * (t > 1500)  # the error distribution triples halfway
        e = abs(rng.normal(0, scale))
        w = aci.half_width()
        if len(aci.scores) > 20:
            hits.append(e <= w)
        aci.update(e <= w, e)
    assert abs(np.mean(hits) - 0.8) < 0.03


def test_backtest_on_own_history_beats_or_matches_the_v8_rule():
    from eval.forecast_backtest import backtest, load_cashbridge
    r = backtest(load_cashbridge(), "own", warmup_weeks=16, mc=50)
    assert r["methods"]["km_pooled"]["wape"] <= r["methods"]["v8_rule"]["wape"]  # the model the product uses
    assert 0.7 <= r["intervals"]["split_conformal"] <= 0.9


def test_receipts_outlook_and_behaviour_cross_check(tmp_path):
    from scripts.run_demo_story import StoryClock
    from ui.backend_real import RealBackend
    b = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    o = b.receipts_outlook()
    assert len(o["v9_expected_receipts"]) == 13 and all(x is not None for x in o["v9_band_80"])
    assert all(lo <= e <= hi for (lo, hi), e in zip(o["v9_band_80"], o["v9_expected_receipts"]))
    x = b._behaviour_score(b.coord.nominee)
    assert 0.02 <= x["p_on_time"] <= 0.98 and x["not_a_credit_decision"] and "v8_p_on_time" in x


def test_external_results_when_data_available():
    from scripts.fetch_external_data import DATASETS, path
    if not path("ar_ibm_sample.csv").exists():
        pytest.skip("external data not downloaded (python scripts/fetch_external_data.py)")
    from eval.external_buyer_validation import run
    r = run()
    unseen = r["splits"][1]["metrics"]
    assert unseen["M2_behavioural_v9"]["roc_auc"] > 0.8 > unseen["M1_cashbridge_v8"]["roc_auc"]
    assert any(f["feature"] == "days_to_settle" for f in r["splits"][0]["leakage_screen_on_train"])
