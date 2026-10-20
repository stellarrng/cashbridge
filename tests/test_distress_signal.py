"""Financial-distress screening hint (Polish bankruptcy data) and the SBA loan-default harness."""

import csv
import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from core.distress_signal import ledger_features, score
from eval import external_distress_validation as dv
from eval import external_sba_validation as sba
from schemas.forecast_schemas import LedgerSnapshot

ROOT = Path(__file__).resolve().parents[1]
ARFF = """% comment
@relation test
@attribute Attr1 numeric
@attribute Attr2 numeric
@attribute class {0,1}
@data
0.1,?,0
-0.5,2.0,1
"""


def test_arff_parser_reads_missing_values_and_labels(tmp_path):
    p = tmp_path / "x.arff"
    p.write_text(ARFF)
    cols, X, y = dv.load_arff(p)
    assert cols == ["Attr1", "Attr2"] and np.isnan(X[0, 1]) and y.tolist() == [0, 1]


def test_preprocessing_is_fitted_on_training_rows_only():
    train = np.array([[1.0], [2.0], [3.0], [np.nan]])
    prep = dv.Prep().fit(train)
    assert prep.med[0] == 2.0
    out = prep.transform(np.array([[1e9]]))  # an outlier in the test row is clipped to the training range
    assert out[0, 0] == pytest.approx(prep.transform(np.array([[prep.hi[0]]]))[0, 0])


def test_folds_are_stratified_and_disjoint():
    y = np.array([0] * 90 + [1] * 10)
    folds = dv._folds(y, 5, 1)
    assert sorted(np.concatenate(folds).tolist()) == list(range(100))
    assert all(y[f].sum() == 2 for f in folds)


def test_ledger_features_use_the_dataset_definitions():
    led = LedgerSnapshot(period_days=365, revenue_usd=Decimal("1000"), cogs_usd=Decimal("700"), avg_inventory_usd=Decimal("70"),
                         avg_receivables_usd=Decimal("100"), avg_payables_usd=Decimal("50"))
    f = ledger_features(led)
    assert f["Attr44"] == pytest.approx(36.5) and f["Attr47"] == pytest.approx(36.5) and f["Attr56"] == pytest.approx(0.3)


@pytest.mark.skipif(not (ROOT / "data" / "models" / "distress_signal.json").exists(), reason="model not built")
def test_score_is_labelled_and_flags_extrapolation():
    from data import loader
    led = LedgerSnapshot(**loader.company()["ledger"])
    s = score(led)
    assert 0 < s["p_distress_1y"] < 1 and s["credit_decision"] is False and s["out_of_domain"] is True
    assert s["outside_training_range"] == [] and len(s["limitations"]) == 3
    weird = led.model_copy(update={"avg_receivables_usd": led.revenue_usd * 5})  # DSO far beyond anything in training
    assert "Attr44" in score(weird)["outside_training_range"]


def test_api_serves_the_signal_to_the_sme_only(tmp_path, monkeypatch):
    from api.main import create_app
    from tests.authed import RoleClient
    from ui.backend_real import RealBackend
    monkeypatch.setenv("CASHBRIDGE_RUNTIME_DIR", str(tmp_path / "rt"))
    client = RoleClient(create_app(lambda: RealBackend(runtime_dir=tmp_path / "runtime"), dist_dir=tmp_path / "no-ui"))
    r = client.get("/api/analytics/distress-signal", headers=client.header("sme.lan"))
    assert r.status_code == 200 and r.json()["credit_decision"] is False
    assert client.get("/api/analytics/distress-signal", headers=client.header("bank.lihua")).status_code == 403


@pytest.mark.skipif(not (ROOT / "reports" / "external_distress_validation.json").exists(), reason="report not generated")
def test_external_results_are_ordered_as_reported():
    res = json.loads((ROOT / "reports" / "external_distress_validation.json").read_text())
    for h in res["horizons"]:
        m = h["metrics"]
        assert m["base"]["roc_auc"] < m["A_cashbridge"]["roc_auc"] < m["D_all_trees"]["roc_auc"]
        assert m["altman_z2"]["roc_auc"] < m["D_all_trees"]["roc_auc"]
        assert h["missingness_check"]["auc_trees_with_missingness_hidden"] > 0.9


# --------------------------------------------------------------------------- SBA harness (structure only, generated rows)
def _sba_fixture(path: Path, n: int = 600) -> None:
    rng = np.random.default_rng(0)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ApprovalFY", "Term", "NoEmp", "NewExist", "UrbanRural", "RevLineCr", "LowDoc", "FranchiseCode", "NAICS",
                    "GrAppv", "SBA_Appv", "MIS_Status", "ChgOffPrinGr", "BalanceGross", "ChgOffDate"])
        for i in range(n):
            bad = rng.random() < 0.2
            w.writerow([1995 + i % 12, 60 if bad else 240, 5, "2" if bad else "1", "1", "N", "N", "1", "722110",
                        "$50,000.00 ", "$25,000.00 ", "CHGOFF" if bad else "P I F", "$12,000.00 " if bad else "$0.00 ", "$0.00 ",
                        "1-Jan-05" if bad else ""])


def test_sba_harness_runs_and_its_leakage_screen_catches_post_outcome_columns(tmp_path, monkeypatch):
    f = tmp_path / "SBAnational.csv"
    _sba_fixture(f)
    monkeypatch.setattr(sba, "REPORTS", tmp_path / "reports")
    res = sba.run(f)
    flagged = {x["feature"] for x in res["leakage_screen_on_train"]}
    assert {"ChgOffPrinGr", "ChgOffDate_present"} <= flagged
    assert "ChgOffPrinGr" not in res["features"] and res["test"]["loans"] > 0
    assert sba.write(res).exists()


def test_sba_harness_without_the_file_invents_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sba, "REPORTS", tmp_path / "reports")
    assert sba.main([str(tmp_path / "missing.csv")]) == 0
    assert "NOT evaluated" in capsys.readouterr().out and not (tmp_path / "reports").exists()
