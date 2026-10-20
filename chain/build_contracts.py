"""Compile the Vyper contracts into chain/build/*.json (ABI, bytecode, source SHA-256, compiler version).

The build files are committed so the server needs only web3 + eth-tester at run time, not the compiler.
`tests/test_chain.py` recompiles when Vyper is installed and fails if a build is stale.

    python -m chain.build_contracts
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
CONTRACTS = ("InvoiceRegistry", "AuditAnchor")


def compile_one(name: str) -> dict:
    import vyper
    from vyper.compiler import compile_code
    src = (HERE / "contracts" / f"{name}.vy").read_text()
    out = compile_code(src, output_formats=["abi", "bytecode"])
    return {"contract": name, "compiler": f"vyper {vyper.__version__}", "source_sha256": hashlib.sha256(src.encode()).hexdigest(),
            "abi": out["abi"], "bytecode": out["bytecode"]}


def main() -> None:
    (HERE / "build").mkdir(exist_ok=True)
    for name in CONTRACTS:
        art = compile_one(name)
        (HERE / "build" / f"{name}.json").write_text(json.dumps(art, indent=1) + "\n")
        print(name, art["source_sha256"][:12], len(art["bytecode"]) // 2, "bytes")


if __name__ == "__main__":
    main()
