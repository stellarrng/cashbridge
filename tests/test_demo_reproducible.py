"""T03: the three-role demo through the HTTP API is reproducible and every pack figure is traceable.

Two independent servers (fresh runtime folders, same seed and simulated clock) driven through the
same clicks must produce the same pack id, locked metrics, bundle hash, cover letter, PDF bytes and
lender verification. Every number in the cover letter must be one of the locked metrics.
"""

import hashlib
import re
from decimal import Decimal

from api.main import create_app
from scripts.run_demo_story import StoryClock
from tests.authed import RoleClient
from ui.backend_real import RealBackend


def run_demo(tmp, monkeypatch):
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp / "ws.db"))
    monkeypatch.delenv("CASHBRIDGE_REQUIRE_DATA_GATE", raising=False)
    backend = RealBackend(runtime_dir=tmp / "runtime", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp / "no-ui"))
    run = client.post("/api/autopilot/run", json={"execute": True}).json()
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    released = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()
    pack_id = released["snapshot"]["pack"]["pack_id"]
    case = client.get(f"/api/bank/cases/{pack_id}").json()
    verify = client.post(f"/api/bank/cases/{pack_id}/verify").json()
    pdf = client.get(f"/api/bank/cases/{pack_id}/pdf").content
    return {"decision": run["decision"], "pack_id": pack_id, "bundle": case["bundle_sha256"], "metrics": case["locked_metrics"],
            "letter": case["letter_text"], "doc_hashes": case["document_hashes"], "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "checks": [(c["check"], c["ok"]) for c in verify["checks"]], "evidence_counts": run.get("evidence_counts")}


def test_two_fresh_servers_produce_the_same_pack(tmp_path, monkeypatch):
    a = run_demo(tmp_path / "a", monkeypatch)
    b = run_demo(tmp_path / "b", monkeypatch)
    assert a == b
    assert a["decision"] == "AWAITING_DIRECTOR_APPROVAL"
    assert all(ok is not False for _, ok in a["checks"])


def test_every_number_in_the_cover_letter_is_a_locked_metric(tmp_path, monkeypatch):
    d = run_demo(tmp_path, monkeypatch)
    locked = set()
    for m in d["metrics"]:
        v = Decimal(str(m["value"]))
        locked |= {v.normalize(), v.quantize(Decimal("0.01")).normalize(), v.quantize(Decimal("0.1")).normalize(), v.to_integral_value()}
    letter = re.sub(r"(INV|PACK|fc|run)-[\w-]+|SHA-256|\d+-week|\d{4}-\d{2}-\d{2}", "", d["letter"])  # identifiers, not figures
    figures = [Decimal(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", letter)]
    stray = [f for f in figures if f.normalize() not in locked]
    assert stray == [], f"figures without a locked source: {stray}"
