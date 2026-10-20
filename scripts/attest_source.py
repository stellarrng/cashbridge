"""Independent verifier CLI: sign an attestation for one source in a quality manifest.

    CASHBRIDGE_ATTESTATION_KEY=... python scripts/attest_source.py \\
        --manifest manifest.json --source-id BANK-2026-10 --verifier "audit.desk@lender" \\
        --expires-on 2026-12-31 --out attestations.json

The person running this must hold the attestation key, which the SME's preparer and the browser never
see. Run it only after checking the source outside CashBridge (bank portal download, e-invoice lookup,
signed statement). Appends to ``--out`` (creates it if missing). Prints the signed record.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import source_attestation  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--verifier", required=True)
    parser.add_argument("--expires-on", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    key = os.environ.get("CASHBRIDGE_ATTESTATION_KEY", "")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    source = next((s for s in manifest.get("sources", []) if str(s.get("source_id")) == args.source_id), None)
    if source is None:
        parser.error(f"source {args.source_id!r} not in manifest")
    record = source_attestation.sign({
        "source_id": source["source_id"], "type": source["type"], "as_of": source["as_of"],
        "content_sha256": source.get("content_sha256"), "verifier": args.verifier,
        "verified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "expires_on": args.expires_on or None}, key)
    out = Path(args.out)
    existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    existing = [r for r in existing if r.get("source_id") != record["source_id"]] + [record]
    out.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
