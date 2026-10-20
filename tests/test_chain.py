"""On-chain exploration: cross-lender invoice register and audit-log anchoring on a real (in-process) EVM."""
import json
from pathlib import Path

import pytest

pytest.importorskip("eth_tester")
pytest.importorskip("web3")

from api.main import create_app  # noqa: E402
from chain import merkle  # noqa: E402
from chain.ledger import BUILD, LENDERS, ChainLedger, canonical_invoice  # noqa: E402
from scripts.run_demo_story import StoryClock  # noqa: E402
from tests.authed import RoleClient  # noqa: E402
from ui.backend_real import RealBackend  # noqa: E402

KEY = b"k" * 32
A, B, C = LENDERS


@pytest.fixture(scope="module")
def ledger():
    return ChainLedger(key=KEY)


def _c(ledger, n="INV-1"):
    return ledger.commitment("0312345678", "BUY-01", n, 26_000_000, "USD", "2026-09-01")


def test_duplicate_financing_is_refused_across_lenders(ledger):
    c = _c(ledger, "INV-DUP")
    assert ledger.register(A, c, "ab" * 32)["registered"] is True
    second = ledger.register(B, c, "cd" * 32)
    assert second["registered"] is False and second["holder"] == A
    assert ledger.status(c)["holder"] == A  # the refused attempt changed nothing
    with pytest.raises(Exception):
        ledger.release(B, c)  # only the registering lender can release
    ledger.release(A, c)
    assert ledger.register(C, c, "ef" * 32)["registered"] is True  # after repayment the invoice can be financed again


def test_non_members_cannot_write(ledger):
    outsider = ledger.w3.eth.accounts[7]
    fn = ledger.registry.functions.register(bytes.fromhex(_c(ledger, "INV-X")), b"\0" * 32)
    with pytest.raises(Exception, match="not a consortium lender"):
        fn.transact({"from": outsider})
    with pytest.raises(Exception, match="only the consortium admin"):
        ledger.registry.functions.add_member(outsider, "rogue").transact({"from": outsider})


def test_commitment_hides_invoice_data_and_normalises(ledger):
    c = _c(ledger, "INV-7")
    assert c == ledger.commitment(" 0312345678", "buy-01", "inv-7", 26_000_000, "usd", "2026-09-01")  # same invoice, same key
    assert c != ledger.commitment("0312345678", "BUY-01", "INV-7", 26_000_001, "USD", "2026-09-01")  # one cent differs
    other_key = ChainLedger(key=b"z" * 32).commitment("0312345678", "BUY-01", "INV-7", 26_000_000, "USD", "2026-09-01")
    assert c != other_key  # without the consortium key the commitment cannot be reproduced
    ledger.register(A, c, "00" * 32)
    raw = json.dumps([dict(x) for x in ledger.w3.eth.get_logs({"fromBlock": 0})], default=str)
    for secret in ("0312345678", "INV-7", "BUY-01", "26000000", "260000"):
        assert secret not in raw  # nothing about the invoice is readable on chain
    with pytest.raises(ValueError):
        canonical_invoice("x", "y", "z", 12.5, "USD", "2026-01-01")


def test_anchor_detects_rewrite_truncation_and_supports_inclusion_proofs(ledger):
    hashes = [f"{i:064x}" for i in range(1, 12)]
    ledger.anchor(hashes[:6])
    ledger.anchor(hashes)
    assert ledger.verify_log(hashes)["all_reproduced"]
    assert not ledger.verify_log(hashes[:5])["all_reproduced"]           # truncated
    tampered = hashes[:3] + ["ff" * 32] + hashes[4:]
    assert not ledger.verify_log(tampered)["all_reproduced"]             # rewritten in the middle
    with pytest.raises(Exception, match="audit log shrank"):
        ledger.anchor(hashes[:4])
    for i in range(len(hashes)):
        p = ledger.inclusion(hashes, i)
        assert p["verified"] and merkle.verify_proof(hashes[i], p["path"], p["root"])
    p = ledger.inclusion(hashes, 2)
    assert not merkle.verify_proof("ee" * 32, p["path"], p["root"])


@pytest.mark.parametrize("n", range(1, 18))
def test_merkle_proofs_for_every_size(n):
    hs = [f"{i:064x}" for i in range(n)]
    r = merkle.root(hs)
    assert all(merkle.verify_proof(hs[i], merkle.proof(hs, i), r) for i in range(n))


def test_journal_replays_after_restart(tmp_path):
    first = ChainLedger(runtime=tmp_path, key=KEY)
    c = _c(first, "INV-J")
    first.register(A, c, "11" * 32)
    first.register(B, c, "22" * 32)
    first.anchor(["aa" * 32, "bb" * 32])
    again = ChainLedger(runtime=tmp_path, key=KEY)
    assert again.status(c)["holder"] == A and again.info()["duplicates_refused"] == 1 and len(again.anchors()) == 1


def test_committed_build_matches_the_source():
    pytest.importorskip("vyper")
    from chain.build_contracts import CONTRACTS, compile_one
    for name in CONTRACTS:
        built = json.loads((BUILD / f"{name}.json").read_text())
        fresh = compile_one(name)
        assert built["source_sha256"] == fresh["source_sha256"] and built["bytecode"] == fresh["bytecode"], f"run python -m chain.build_contracts ({name})"


# --------------------------------------------------------------------------- integrated with the lender flow
@pytest.fixture
def app(tmp_path):
    backend = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    return backend, RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))


def _release(client, backend):
    assert client.post("/api/autopilot/run", json={"execute": True}).json()["decision"] == "AWAITING_DIRECTOR_APPROVAL"
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    result = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()
    assert result["ok"], result
    return result["snapshot"]["pack"]["pack_id"]


def test_lender_flow_registers_on_chain_and_a_second_lender_is_refused(app):
    backend, client = app
    pack = _release(client, backend)
    st = client.get("/api/chain/status").json()
    assert st["available"] and st["anchors"] >= 1 and st["audit"]["all_reproduced"]  # anchored at release
    assert st["invoice"]["active"] is False
    bank = client.header("bank.lihua")
    assert client.post("/api/chain/drill", headers=bank).status_code == 409  # nothing financed yet
    checks = {c["check"]: c for c in client.post(f"/api/bank/cases/{pack}/verify").json()["checks"]}
    assert checks["Not financed at another consortium lender (on-chain register)"]["ok"] is True
    assert checks["Audit log reproduces every on-chain anchor (Merkle root)"]["ok"] is True
    assert client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING", "note": "ok"}).status_code == 200
    st = client.get("/api/chain/status", headers=client.header("bank.lihua")).json()
    assert st["invoice"]["active"] and st["invoice"]["holder"] == "CashBridge MOCK Lender"
    drill = client.post("/api/chain/drill", headers=bank).json()
    assert drill["refused"] and drill["holder"] == "CashBridge MOCK Lender" and drill["status"]["duplicates_refused"] == 1
    assert client.post("/api/chain/anchor").status_code == 200  # covers the lender's reads since the decision
    assert client.post("/api/chain/anchor").status_code == 409  # nothing new: no duplicate anchor
    proof = client.get("/api/chain/proof/0").json()
    assert proof["verified"] and proof["event"]["seq"] == 1
    assert client.post("/api/chain/drill", headers=client.header("sme.lan")).status_code == 403
    assert client.get("/api/chain/proof/0", headers=client.header("bank.lihua")).status_code == 403


def test_funding_is_refused_when_another_lender_financed_the_invoice_first(app):
    backend, client = app
    pack = _release(client, backend)
    ledger = backend._ledger()
    ledger.register("Simulated Lender B", backend._invoice_commitment(ledger), "99" * 32)  # financed elsewhere first
    verify = client.post(f"/api/bank/cases/{pack}/verify").json()
    cross = next(c for c in verify["checks"] if "another consortium lender" in c["check"])
    assert cross["ok"] is False and "Simulated Lender B" in cross["detail"]
    r = client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING", "note": "ok"})
    assert r.status_code == 409 and "Duplicate financing refused" in r.json()["detail"]
    assert backend.coord.state.value == "SUBMITTED"  # nothing was funded


def test_tampered_audit_log_fails_the_anchor_check(app):
    backend, client = app
    pack = _release(client, backend)
    path = Path(backend.coord.audit_path)
    lines = path.read_text().splitlines()
    first = json.loads(lines[0]); first["reason"] = "rewritten"
    # Rewrite the WHOLE chain consistently (an admin with file access): the local chain check passes, the anchor does not.
    from security.audit_log import _line_hash, GENESIS_HASH
    prev, out = GENESIS_HASH, []
    for i, raw in enumerate(lines):
        d = first if i == 0 else json.loads(raw)
        d["prev_line_sha256"] = prev
        d["line_sha256"] = _line_hash(d)
        prev = d["line_sha256"]
        out.append(json.dumps(d, sort_keys=True))
    path.write_text("\n".join(out) + "\n")
    checks = {c["check"]: c for c in client.post(f"/api/bank/cases/{pack}/verify").json()["checks"]}
    assert checks["Audit log hash chain intact"]["ok"] is True  # the local chain alone cannot see a full rewrite
    assert checks["Audit log reproduces every on-chain anchor (Merkle root)"]["ok"] is False  # the anchor can


def test_chain_can_be_turned_off(app, monkeypatch):
    backend, client = app
    monkeypatch.setenv("CASHBRIDGE_CHAIN", "off")
    assert client.get("/api/chain/status").json() == {"available": False, "reason": "turned off (CASHBRIDGE_CHAIN=off)"}
    assert client.post("/api/chain/anchor").status_code == 503


def test_testnet_deploy_script_dry_run():
    from scripts.deploy_chain_testnet import main
    out = main(["--dry-run"])
    assert out["dry_run"] and set(out["contracts"]) == {"InvoiceRegistry", "AuditAnchor"} and len(out["members"]) == 2


# --------------------------------------------------------------------------- fail-closed and visible failures (audit P0)
def _audit_lines(backend, tool):
    return [json.loads(x) for x in Path(backend.coord.audit_path).read_text().splitlines() if f'"{tool}"' in x]


def test_register_error_fails_closed(app, monkeypatch):
    backend, client = app
    pack = _release(client, backend)
    client.post(f"/api/bank/cases/{pack}/verify")
    ledger = backend._ledger()

    def broken(*a, **k):
        raise RuntimeError("node unreachable")
    monkeypatch.setattr(ledger, "register", broken)
    r = client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING", "note": "ok"})
    assert r.status_code == 409 and "could not be checked" in r.json()["detail"]
    assert backend.coord.state.value == "SUBMITTED"
    assert _audit_lines(backend, "cross_lender_register")[-1]["decision"] == "BLOCKED"


def test_required_mode_refuses_funding_without_the_module(app, monkeypatch):
    backend, client = app
    pack = _release(client, backend)
    client.post(f"/api/bank/cases/{pack}/verify")
    monkeypatch.setenv("CASHBRIDGE_CHAIN", "required")
    monkeypatch.setattr("chain.ledger.available", lambda: False)
    r = client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING", "note": "ok"})
    assert r.status_code == 409 and "required but unavailable" in r.json()["detail"]
    assert backend.coord.state.value == "SUBMITTED"


def test_off_mode_funds_but_records_that_the_register_was_not_checked(app, monkeypatch):
    backend, client = app
    pack = _release(client, backend)
    monkeypatch.setenv("CASHBRIDGE_CHAIN", "off")
    checks = client.post(f"/api/bank/cases/{pack}/verify").json()["checks"]
    row = next(c for c in checks if "another consortium lender" in c["check"])
    assert row["ok"] is None and "not checked" in row["detail"]
    r = client.post(f"/api/bank/cases/{pack}/decision", json={"decision": "APPROVE_FUNDING", "note": "ok"})
    assert r.status_code == 200
    assert any(h["event"] == "REGISTER_NOT_CHECKED" for h in r.json()["review"]["history"])
    assert _audit_lines(backend, "cross_lender_register")[-1]["reason"].startswith("not checked")


def test_anchor_failure_is_visible_not_silent(tmp_path, monkeypatch):
    backend = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    ledger = backend._ledger()

    def broken(*a, **k):
        raise RuntimeError("anchor tx reverted")
    monkeypatch.setattr(ledger, "anchor", broken)
    pack = _release(client, backend)  # the release itself is not blocked
    st = client.get("/api/chain/status").json()
    assert st["anchor_failures"] and st["anchor_failures"][0]["at"] == "release"
    row = next(c for c in client.post(f"/api/bank/cases/{pack}/verify").json()["checks"] if "anchor" in c["check"])
    assert row["ok"] is False and "FAILED" in row["detail"]
    assert _audit_lines(backend, "anchor_audit_root")[-1]["decision"] == "BLOCKED"


def test_manual_anchor_records_who_published_it(app):
    backend, client = app
    pack = _release(client, backend)
    assert client.post("/api/chain/anchor").status_code == 409  # already anchored at release, nothing new
    client.get(f"/api/bank/cases/{pack}")  # the lender reads the case: a new audit line
    assert client.post("/api/chain/anchor", headers=client.header("sme.minh")).status_code == 200
    line = _audit_lines(backend, "anchor_audit_root")[-1]
    assert line["decision"] == "ALLOWED" and "sme.minh" in line["reason"]
    assert client.post("/api/chain/anchor").status_code == 409  # the record of the anchor is not "new" audit content
