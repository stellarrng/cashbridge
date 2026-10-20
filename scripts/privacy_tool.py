"""Operator CLI for the data lifecycle (see core/privacy_lifecycle.py for the rules).

    python scripts/privacy_tool.py inventory
    python scripts/privacy_tool.py export --tenant TEN-BDT-001 --out export.json
    python scripts/privacy_tool.py purge --retention-days 90 [--dry-run]

Run on the server with the same environment as the app (CASHBRIDGE_RUNTIME_DIR etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import runtime_mode  # noqa: E402
from config.settings import BASE_DIR  # noqa: E402
from core import privacy_lifecycle as pl  # noqa: E402


def paths():
    runtime = runtime_mode.runtime_dir(BASE_DIR)
    ws = Path(os.environ.get("CASHBRIDGE_WORKSPACE_DB", "") or runtime / "workspace.sqlite3")
    auto = Path(os.environ.get("CASHBRIDGE_AUTOMATION_DB", "") or runtime / "automation_jobs.sqlite3")
    return runtime, ws, auto


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory")
    ex = sub.add_parser("export")
    ex.add_argument("--tenant", required=True)
    ex.add_argument("--out", required=True)
    pu = sub.add_parser("purge")
    pu.add_argument("--retention-days", type=int, default=int(os.environ.get("CASHBRIDGE_RETENTION_DAYS", pl.DEFAULT_RETENTION_DAYS)))
    pu.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    runtime, ws, auto = paths()
    if args.cmd == "inventory":
        print(json.dumps(pl.inventory(runtime, ws, auto), indent=2))
    elif args.cmd == "export":
        Path(args.out).write_text(json.dumps(pl.export_tenant(args.tenant, runtime, ws), indent=2, ensure_ascii=False), encoding="utf-8")
        print(args.out)
    else:
        print(json.dumps(pl.purge(runtime, ws, auto, args.retention_days, dry_run=args.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
