"""T04: the Data Reliability Gate fails closed on EVERY financing route, tested through the API.

Routes covered: /api/prepare_pack, POST /packs, /api/autopilot/run (execute), /api/approve,
/packs/{id}/approve and the lender's APPROVE_FUNDING decision. A manifest cannot vouch for itself:
``verified_by`` text, forged or edited attestations and the plain ID list in production all fail.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from api.main import create_app
from core import financing_gate, source_attestation
from scripts.run_demo_story import StoryClock
from tests.authed import RoleClient
from ui.backend_real import RealBackend

KEY = "k" * 40
TODAY = date.today()


def source(typ, sid, age_days=1, sha=None, claims_verified=False):
    row = {"type": typ, "source_id": sid, "as_of": (TODAY - timedelta(days=age_days)).isoformat()}
    if sha:
        row["content_sha256"] = sha
    if claims_verified:  # what a malicious or careless preparer might write
        row.update(verified_by="external_auditor", verified_at="2026-10-01T00:00:00Z", verified=True)
    return row


def good_manifest():
    return {"sources": [source("bank_statement", "BANK-1", sha="a" * 64), source("receivables_aging", "AR-1", sha="b" * 64),
                        source("ledger", "GL-1", sha="c" * 64)],
            "ledger_entries": [{"reference": "INV-1", "amount": "1200.00"}, {"reference": "INV-2", "amount": "80.50"}],
            "bank_entries": [{"reference": "INV-1", "amount": "1200.00"}, {"reference": "INV-2", "amount": "80.50"}]}


def attest_all(manifest, key=KEY, **override):
    out = []
    for s in manifest["sources"]:
        rec = {"source_id": s["source_id"], "type": s["type"], "as_of": s["as_of"], "content_sha256": s.get("content_sha256"),
               "verifier": "audit.desk@lender", "verified_at": "2026-10-19T09:00:00+00:00"}
        rec.update(override)
        out.append(source_attestation.sign(rec, key))
    return out


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Write manifest/attestation files and point the server env at them."""
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    for k in ("CASHBRIDGE_REQUIRE_DATA_GATE", "CASHBRIDGE_QUALITY_MANIFEST_PATH", "CASHBRIDGE_SOURCE_ATTESTATIONS_PATH",
              "CASHBRIDGE_ATTESTATION_KEY", "CASHBRIDGE_VERIFIED_SOURCE_IDS"):
        monkeypatch.delenv(k, raising=False)

    def configure(manifest=None, attestations=None, on=True, key=KEY, legacy_ids=None):
        if on:
            monkeypatch.setenv("CASHBRIDGE_REQUIRE_DATA_GATE", "1")
        else:
            monkeypatch.delenv("CASHBRIDGE_REQUIRE_DATA_GATE", raising=False)
        if manifest is not None:
            path = tmp_path / "manifest.json"
            path.write_text(json.dumps(manifest))
            monkeypatch.setenv("CASHBRIDGE_QUALITY_MANIFEST_PATH", str(path))
        if attestations is not None:
            path = tmp_path / "attest.json"
            path.write_text(json.dumps(attestations))
            monkeypatch.setenv("CASHBRIDGE_SOURCE_ATTESTATIONS_PATH", str(path))
            monkeypatch.setenv("CASHBRIDGE_ATTESTATION_KEY", key)
        if legacy_ids is not None:
            monkeypatch.setenv("CASHBRIDGE_VERIFIED_SOURCE_IDS", legacy_ids)
    return configure


@pytest.fixture
def api(tmp_path):
    backend = RealBackend(runtime_dir=tmp_path / "runtime", clock=StoryClock())
    return RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "no-ui")), backend


def blocked(response, code=None):
    assert response.status_code == 409, (response.status_code, response.text)
    if code:
        assert code in response.json()["detail"], response.json()["detail"]
    return True


SME_ROUTES = [("POST", "/api/prepare_pack", None), ("POST", "/packs", {"option_id": "factoring_inv1030"}),
              ("POST", "/api/autopilot/run", {"execute": True})]


@pytest.mark.parametrize("method,path,body", SME_ROUTES)
def test_no_manifest_blocks_every_preparation_route(env, api, method, path, body):
    client, _ = api
    env()
    if path == "/api/prepare_pack":
        assert client.post("/api/choose_option", json={"option_id": "factoring_inv1030"}).status_code == 200
    blocked(client.request(method, path, json=body or {}), "manifest")


@pytest.mark.parametrize("mutate,code", [
    (lambda m: m["sources"].pop(0), "MISSING_SOURCE"),
    (lambda m: m["sources"][0].update(as_of=(TODAY - timedelta(days=200)).isoformat()), "STALE_SOURCE"),
    (lambda m: m["sources"][0].update(as_of=(TODAY + timedelta(days=3)).isoformat()), "FUTURE_DATE"),
    (lambda m: m["bank_entries"][1].update(amount="80.00"), "RECONCILIATION_MISMATCH"),
    (lambda m: m["bank_entries"].pop(), "RECONCILIATION_MISMATCH"),
])
def test_missing_stale_future_and_mismatched_data_block_preparation(env, api, mutate, code):
    client, _ = api
    manifest = good_manifest()
    atts = attest_all(manifest)
    mutate(manifest)
    env(manifest, atts)
    blocked(client.post("/packs", json={"option_id": "factoring_inv1030"}), code)


def test_self_declared_verification_is_not_accepted(env, api):
    client, _ = api
    manifest = good_manifest()
    manifest["sources"] = [{**s, "verified_by": "external_auditor", "verified": True, "verified_at": "2026-10-01"} for s in manifest["sources"]]
    env(manifest)  # no attestations at all
    blocked(client.post("/packs", json={"option_id": "factoring_inv1030"}), "UNVERIFIED_SOURCE")


@pytest.mark.parametrize("tamper,expect_reason", [
    (lambda atts, m: atts.__setitem__(0, {**atts[0], "sig": "0" * 64}), "bad_signature"),
    (lambda atts, m: atts.__setitem__(0, {**atts[0], "verifier": "someone.else"}), "bad_signature"),
    (lambda atts, m: m["sources"][0].update(as_of=(TODAY - timedelta(days=2)).isoformat()), "changed_after_attestation"),
    (lambda atts, m: m["sources"][0].update(content_sha256="f" * 64), "changed_after_attestation"),
])
def test_forged_or_outdated_attestations_do_not_count(env, api, tamper, expect_reason):
    client, _ = api
    manifest = good_manifest()
    atts = attest_all(manifest)
    tamper(atts, manifest)
    env(manifest, atts)
    blocked(client.post("/packs", json={"option_id": "factoring_inv1030"}), "UNVERIFIED_SOURCE")
    state = financing_gate.evaluate()
    assert any(expect_reason in r["reason"] for r in state["rejected_attestations"]), state["rejected_attestations"]


def test_attestation_signed_with_another_key_and_expired_attestation_fail(env, api):
    client, _ = api
    manifest = good_manifest()
    env(manifest, attest_all(manifest, key="z" * 40))
    blocked(client.post("/packs", json={"option_id": "factoring_inv1030"}), "UNVERIFIED_SOURCE")
    env(manifest, attest_all(manifest, expires_on=(TODAY - timedelta(days=1)).isoformat()))
    blocked(client.post("/packs", json={"option_id": "factoring_inv1030"}), "UNVERIFIED_SOURCE")
    assert all(r["reason"] == "attestation_expired" for r in financing_gate.evaluate()["rejected_attestations"])


def test_unreadable_attestation_file_or_short_key_fails_closed(env, api, tmp_path, monkeypatch):
    client, _ = api
    manifest = good_manifest()
    env(manifest, attest_all(manifest))
    (tmp_path / "attest.json").write_text("{not json")
    blocked(client.post("/packs", json={"option_id": "factoring_inv1030"}), "attestations")
    env(manifest, attest_all(manifest))
    monkeypatch.setenv("CASHBRIDGE_ATTESTATION_KEY", "short")
    blocked(client.post("/packs", json={"option_id": "factoring_inv1030"}), "attestations")
    monkeypatch.setenv("CASHBRIDGE_QUALITY_MANIFEST_PATH", str(tmp_path / "does-not-exist.json"))
    blocked(client.post("/packs", json={"option_id": "factoring_inv1030"}), "invalid or inaccessible")


def test_fully_verified_data_allows_the_whole_flow(env, api):
    client, backend = api
    manifest = good_manifest()
    env(manifest, attest_all(manifest))
    state = client.get("/api/workspace/data-gate").json()
    assert state["enabled"] and state["gate"] == "READY_FOR_DRAFT" and state["allows_financing"]
    assert state["external_authenticity_verified"] is False
    assert client.post("/api/choose_option", json={"option_id": "factoring_inv1030"}).status_code == 200
    assert client.post("/api/prepare_pack").status_code == 200
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    approved = client.post("/api/approve", json={"code": backend.coord.otp.current_code()})
    assert approved.status_code == 200 and approved.json()["ok"], approved.text
    pack_id = approved.json()["snapshot"]["pack"]["pack_id"]
    assert client.post(f"/api/bank/cases/{pack_id}/verify").status_code == 200
    assert client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "APPROVE_FUNDING"}).status_code == 200


def test_approval_and_lender_funding_are_blocked_if_data_goes_bad_after_preparation(env, api):
    client, backend = api
    env(on=False)
    assert client.post("/api/choose_option", json={"option_id": "factoring_inv1030"}).status_code == 200
    assert client.post("/api/prepare_pack").status_code == 200
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    code = backend.coord.otp.current_code()
    bad = good_manifest()
    bad["bank_entries"][0]["amount"] = "1.00"
    env(bad, attest_all(bad))
    blocked(client.post("/api/approve", json={"code": code}), "RECONCILIATION_MISMATCH")
    pack_id = backend.coord.pack["pack_id"]
    blocked(client.post(f"/packs/{pack_id}/approve", json={"code": code}), "RECONCILIATION_MISMATCH")
    assert backend.coord.state.value == "AWAITING_APPROVAL"  # nothing moved
    env(on=False)
    assert client.post("/api/approve", json={"code": code}).json()["ok"]
    env(bad, attest_all(bad))
    assert client.post(f"/api/bank/cases/{pack_id}/verify").status_code == 200
    blocked(client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "APPROVE_FUNDING"}))
    # Asking for information or declining is not a financing action and stays possible.
    ok = client.post(f"/api/bank/cases/{pack_id}/decision", json={"decision": "REQUEST_INFO", "note": "Bank feed mismatch on INV-1"})
    assert ok.status_code == 200


def test_gate_refusals_are_in_the_audit_chain_and_plan_only_still_works(env, api):
    from security.audit_log import verify_chain
    client, backend = api
    env()
    blocked(client.post("/api/autopilot/run", json={"execute": True}))
    assert client.post("/api/autopilot/run", json={"execute": False}).status_code == 200
    text = backend.coord.audit_path.read_text()
    assert '"data_reliability_gate"' in text and "autopilot_execute" in text
    assert verify_chain(backend.coord.audit_path)[0] is True


def test_production_always_enforces_the_gate_and_ignores_the_plain_id_list():
    manifest_env = {"CASHBRIDGE_ENV": "production", "CASHBRIDGE_REQUIRE_DATA_GATE": "0"}
    assert financing_gate.enabled(manifest_env) is True
    assert financing_gate.enabled({"CASHBRIDGE_REQUIRE_DATA_GATE": "0"}) is False
    with pytest.raises(financing_gate.GateBlocked):
        financing_gate.check("prepare_pack", manifest_env)


def test_production_ignores_legacy_verified_id_list(tmp_path):
    manifest = good_manifest()
    path = tmp_path / "m.json"
    path.write_text(json.dumps(manifest))
    ids = ",".join(s["source_id"] for s in manifest["sources"])
    demo = {"CASHBRIDGE_REQUIRE_DATA_GATE": "1", "CASHBRIDGE_QUALITY_MANIFEST_PATH": str(path), "CASHBRIDGE_VERIFIED_SOURCE_IDS": ids}
    assert financing_gate.evaluate(demo)["gate"] == "READY_FOR_DRAFT"
    prod = {**demo, "CASHBRIDGE_ENV": "production"}
    assert financing_gate.evaluate(prod)["gate"] == "REVIEW_REQUIRED"
    att = tmp_path / "a.json"
    att.write_text(json.dumps(attest_all(manifest)))
    prod.update(CASHBRIDGE_SOURCE_ATTESTATIONS_PATH=str(att), CASHBRIDGE_ATTESTATION_KEY=KEY)
    assert financing_gate.evaluate(prod)["gate"] == "READY_FOR_DRAFT"


def test_attestation_cli_round_trip(tmp_path, monkeypatch):
    from scripts import attest_source
    manifest = good_manifest()
    mpath, out = tmp_path / "m.json", tmp_path / "att.json"
    mpath.write_text(json.dumps(manifest))
    monkeypatch.setenv("CASHBRIDGE_ATTESTATION_KEY", KEY)
    for s in manifest["sources"]:
        assert attest_source.main(["--manifest", str(mpath), "--source-id", s["source_id"], "--verifier", "desk", "--out", str(out)]) == 0
    ids, rejected = source_attestation.verified_source_ids(manifest["sources"], json.loads(out.read_text()), KEY, TODAY)
    assert ids == {"BANK-1", "AR-1", "GL-1"} and rejected == []
