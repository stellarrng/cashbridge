"""Deploy the consortium contracts to an EVM testnet (for example Sepolia) or a permissioned EVM chain.

STATUS: written and checked offline (``--dry-run`` against the in-process EVM), NOT run against a public network:
the build sandbox has no route to an RPC node. Nothing in the app depends on it.

    CB_RPC_URL=https://...  CB_DEPLOYER_KEY=0x...  python scripts/deploy_chain_testnet.py \
        --member 0xLenderA:"Lender A" --member 0xLenderB:"Lender B" --publisher 0xSmeOperator

    python scripts/deploy_chain_testnet.py --dry-run     # same steps on the in-process EVM

The deployer becomes the consortium admin. Keep its key in a hardware wallet or KMS; never commit it.
Writes the addresses to data/execution_evidence/chain_deployment.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BUILD = ROOT / "chain" / "build"


def _w3(dry_run: bool):
    from web3 import Web3
    if dry_run:
        from eth_tester import EthereumTester, PyEVMBackend
        from web3.providers.eth_tester import EthereumTesterProvider
        w3 = Web3(EthereumTesterProvider(EthereumTester(PyEVMBackend())))
        return w3, None, w3.eth.accounts[0]
    url, key = os.environ.get("CB_RPC_URL"), os.environ.get("CB_DEPLOYER_KEY")
    if not url or not key:
        raise SystemExit("set CB_RPC_URL and CB_DEPLOYER_KEY (or use --dry-run)")
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))
    account = w3.eth.account.from_key(key)
    return w3, account, account.address


def _send(w3, account, sender, fn):
    if account is None:
        return w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
    tx = fn.build_transaction({"from": sender, "nonce": w3.eth.get_transaction_count(sender), "chainId": w3.eth.chain_id})
    signed = account.sign_transaction(tx)
    return w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction), timeout=300)


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--member", action="append", default=[], help="address:name of a consortium lender")
    ap.add_argument("--publisher", action="append", default=[], help="address allowed to anchor audit roots")
    ap.add_argument("--dry-run", action="store_true", help="run every step on an in-process EVM instead")
    args = ap.parse_args(argv)
    w3, account, sender = _w3(args.dry_run)
    if args.dry_run and not args.member:
        args.member = [f"{w3.eth.accounts[1]}:Lender A (dry run)", f"{w3.eth.accounts[2]}:Lender B (dry run)"]
    out = {"chain_id": w3.eth.chain_id, "dry_run": args.dry_run, "admin": sender, "contracts": {}}
    for name in ("InvoiceRegistry", "AuditAnchor"):
        art = json.loads((BUILD / f"{name}.json").read_text())
        receipt = _send(w3, account, sender, w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]).constructor())
        out["contracts"][name] = {"address": receipt.contractAddress, "tx": receipt.transactionHash.hex(),
                                  "source_sha256": art["source_sha256"], "compiler": art["compiler"]}
    reg = w3.eth.contract(address=out["contracts"]["InvoiceRegistry"]["address"], abi=json.loads((BUILD / "InvoiceRegistry.json").read_text())["abi"])
    anc = w3.eth.contract(address=out["contracts"]["AuditAnchor"]["address"], abi=json.loads((BUILD / "AuditAnchor.json").read_text())["abi"])
    for spec in args.member:
        addr, _, name = spec.partition(":")
        _send(w3, account, sender, reg.functions.add_member(w3.to_checksum_address(addr), name[:64] or "lender"))
    for addr in args.publisher:
        _send(w3, account, sender, anc.functions.add_publisher(w3.to_checksum_address(addr)))
    out["members"] = args.member
    if not args.dry_run:
        path = ROOT / "data" / "execution_evidence" / "chain_deployment.json"
        path.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main()
