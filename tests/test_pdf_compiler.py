"""Verifiable Funding Pack PDF (Step 5.3)."""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.coordinator import Coordinator
from api.main import create_app
from core.pdf_compiler import bundle_sha256, printed_hashes
from data import seed_sandbox
from scripts.run_demo_story import StoryClock
from ui.backend_real import RealBackend


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("pdf_inputs")
    seed_sandbox.write_all(folder)
    return folder


def prepared(inputs, tmp_path):
    c = Coordinator(inputs_dir=inputs, evidence_dir=tmp_path / "e", cases_dir=tmp_path / "c", clock=StoryClock())
    c.weekly_run(auto_prepare=True)
    return c


def test_pdf_exists_is_a_pdf_and_is_labelled_synthetic(inputs, tmp_path):
    c = prepared(inputs, tmp_path)
    path = c.pack_pdf_file
    assert path.exists() and path.stat().st_size > 5_000 and path.read_bytes().startswith(b"%PDF")
    text = path.read_bytes()
    assert text.count(b"Synthetic demo data") >= 5  # footer on every page
    assert c.pack["pdf_path"] == f"packs/{c.pack['pack_id']}.pdf"


def test_printed_bundle_hash_equals_the_recomputed_hash(inputs, tmp_path):
    c = prepared(inputs, tmp_path)
    metrics = {m["key"]: m["value"] for m in c.pack["locked_metrics"]}
    recomputed = bundle_sha256(c.pack["document_hashes"], metrics)
    assert recomputed == c.pack["bundle_sha256"] == c._bundle_sha
    printed = printed_hashes(c.pack_pdf_file)
    assert recomputed in printed
    for digest in c.pack["document_hashes"].values():
        assert digest in printed
    assert c.pack["action_hash"] in printed


def test_document_hashes_can_be_recomputed_from_the_source_records(inputs, tmp_path):
    c = prepared(inputs, tmp_path)
    invoice = c.nominee
    canonical = json.dumps(invoice.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    assert hashlib.sha256(canonical.encode()).hexdigest() == c.pack["document_hashes"]["invoice"]


def test_changing_any_locked_figure_changes_the_bundle_hash(inputs, tmp_path):
    c = prepared(inputs, tmp_path)
    metrics = {m["key"]: m["value"] for m in c.pack["locked_metrics"]}
    tampered = {**metrics, "advance_usd": metrics["advance_usd"] + 1}
    assert bundle_sha256(c.pack["document_hashes"], tampered) != c.pack["bundle_sha256"]


def test_pdf_contains_the_letter_metrics_match_result_and_formulas(inputs, tmp_path):
    raw = prepared(inputs, tmp_path).pack_pdf_file.read_bytes()
    for needle in (b"Verifiable", b"Cover letter", b"Locked metrics", b"3-way match result: ELIGIBLE", b"recompute me",
                   b"CCC = DIO + DSO - DPO = 35 + 75 - 28 = 82", b"APR = total cost / net funds", b"No entry for this invoice key",
                   b"USD 48,000.00", b"tamper-evident"):
        assert needle in raw, needle
    assert b"WeBank Factoring" not in raw and b"immutable" not in raw


def test_pdf_bytes_are_identical_for_identical_packs(inputs, tmp_path):
    a = prepared(inputs, tmp_path / "a").pack_pdf_file.read_bytes()
    b = prepared(inputs, tmp_path / "b").pack_pdf_file.read_bytes()
    assert a == b


def test_after_submission_the_pdf_carries_the_registry_block_and_lender_reference(inputs, tmp_path):
    c = prepared(inputs, tmp_path)
    before = c.pack_pdf_file.read_bytes()
    c.request_approval()
    assert c.approve(c.otp.current_code())["ok"]
    after = c.pack_pdf_file.read_bytes()
    assert after != before
    assert c.pack["lender_ref"].encode() in after and c.pack["registry_block"]["block_hash"].encode() in after
    assert b"Registered in block 0" in after
    assert c.pack["bundle_sha256"] in printed_hashes(c.pack_pdf_file)  # the bundle hash does not change on submission


def test_unprepared_case_has_no_pdf(inputs, tmp_path):
    c = Coordinator(inputs_dir=inputs, evidence_dir=tmp_path / "e", cases_dir=tmp_path / "c", clock=StoryClock())
    c.weekly_run()
    assert c.pack_pdf_file is None


def test_api_serves_the_pdf_only_when_a_pack_exists(tmp_path):
    backend = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    client = TestClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    assert client.get("/api/pack/pdf").status_code == 404
    client.post("/api/choose_option", json={"option_id": "factoring_inv1030"})
    client.post("/api/prepare_pack")
    response = client.get("/api/pack/pdf")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF") and "PACK-" in response.headers["content-disposition"]


def test_story_writes_the_pack_pdf_into_the_evidence_folder(tmp_path):
    from scripts import run_demo_story

    run_demo_story.run(tmp_path, log=lambda _t: None)
    pdfs = list((tmp_path / "packs").glob("PACK-*.pdf"))
    assert len(pdfs) == 1 and b"Registered in block 0" in pdfs[0].read_bytes()
