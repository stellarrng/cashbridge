"""Consortium ledger on an in-process EVM: cross-lender invoice register + audit-log anchoring.

What runs here is real EVM bytecode (Vyper 0.4.3, compiled into chain/build) executed by py-evm through eth-tester:
the same contract would deploy unchanged to an Ethereum testnet or a permissioned EVM chain (see
scripts/deploy_chain_testnet.py, which is written but was not run: this sandbox has no route to a blockchain node).
What is SIMULATED: the consortium. "Lender B" and "Lender C" are accounts in this process, not other banks.

Privacy: no invoice data goes on chain. The register is keyed by
    commitment = HMAC-SHA256(consortium key, "cb-invoice-v1|seller tax id|buyer id|invoice no|amount in minor units|currency|issue date")
Members share the key off chain; without it the commitment cannot be brute-forced from guessable fields. Anyone who
holds the key can test a guess, so the key is a consortium secret (in production: an HSM, rotated by the admin).

Persistence: an in-process chain disappears with the process, so every state-changing transaction is journalled
(runtime/chain_journal.jsonl) and replayed at start. A public or permissioned chain would make this unnecessary.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from chain import merkle

BUILD = Path(__file__).parent / "build"
ROLES = {"admin": 0, "CashBridge MOCK Lender": 1, "Simulated Lender B": 2, "Simulated Lender C": 3, "SME audit publisher": 4}
LENDERS = ("CashBridge MOCK Lender", "Simulated Lender B", "Simulated Lender C")


class ChainUnavailable(RuntimeError):
    pass


def available() -> bool:
    try:
        import eth_tester  # noqa: F401
        import web3  # noqa: F401
        return True
    except ImportError:
        return False


def consortium_key(runtime: Optional[Path], env: Optional[dict] = None) -> bytes:
    source = os.environ if env is None else env
    raw = source.get("CASHBRIDGE_CONSORTIUM_KEY", "").strip()
    if raw:
        key = base64.b64decode(raw)
        if len(key) < 32:
            raise ChainUnavailable("CASHBRIDGE_CONSORTIUM_KEY must be at least 32 bytes, base64-encoded")
        return key
    from config import runtime_mode
    if runtime_mode.is_production(source):
        raise ChainUnavailable("CASHBRIDGE_CONSORTIUM_KEY is required in production")
    if runtime is None:
        return hashlib.sha256(b"cashbridge-demo-consortium-key").digest()
    path = Path(runtime) / "consortium.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(base64.b64encode(secrets.token_bytes(32)))
    return base64.b64decode(path.read_bytes())


def canonical_invoice(seller_tax_id: str, buyer_id: str, invoice_no: str, minor_units: int, currency: str, issue_date: str) -> str:
    """Every member must build the same string from the same invoice: amount in integer minor units of the invoice
    currency (cents, or yen for JPY), upper-cased fields with single spaces, ISO issue date."""
    if isinstance(minor_units, bool) or not isinstance(minor_units, int) or minor_units <= 0:
        raise ValueError("amount must be a positive integer number of minor units")
    cents = minor_units
    norm = lambda s: " ".join(str(s).upper().split())  # noqa: E731  case and spacing must not create a "new" invoice
    return "|".join(["cb-invoice-v1", norm(seller_tax_id), norm(buyer_id), norm(invoice_no), str(cents), norm(currency), str(issue_date)[:10]])


class ChainLedger:
    def __init__(self, runtime: Optional[Path] = None, key: Optional[bytes] = None) -> None:
        if not available():
            raise ChainUnavailable("web3 / eth-tester not installed (pip install -r requirements-chain.txt)")
        from eth_tester import EthereumTester, PyEVMBackend
        from web3 import Web3
        from web3.providers.eth_tester import EthereumTesterProvider
        self._lock = threading.RLock()
        self.runtime = Path(runtime) if runtime else None
        self.key = key if key is not None else consortium_key(self.runtime)
        self.tester = EthereumTester(PyEVMBackend())
        self.w3 = Web3(EthereumTesterProvider(self.tester))
        accts = self.w3.eth.accounts
        self.addr = {role: accts[i] for role, i in ROLES.items()}
        self.name_of = {a: r for r, a in self.addr.items()}
        self.registry = self._deploy("InvoiceRegistry")
        self.anchor_c = self._deploy("AuditAnchor")
        for name in LENDERS:
            self._tx(self.registry.functions.add_member(self.addr[name], name), "admin")
        self._tx(self.anchor_c.functions.add_publisher(self.addr["SME audit publisher"]), "admin")
        self.journal = (self.runtime / "chain_journal.jsonl") if self.runtime else None
        self._replaying = False
        self._replay()

    # ------------------------------------------------------------------ plumbing
    def _deploy(self, name: str):
        art = json.loads((BUILD / f"{name}.json").read_text())
        factory = self.w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
        receipt = self.w3.eth.wait_for_transaction_receipt(factory.constructor().transact({"from": self.addr["admin"]}))
        contract = self.w3.eth.contract(address=receipt.contractAddress, abi=art["abi"])
        contract.build = {"compiler": art["compiler"], "source_sha256": art["source_sha256"], "address": receipt.contractAddress}
        return contract

    def _tx(self, fn, role: str) -> Dict[str, Any]:
        receipt = self.w3.eth.wait_for_transaction_receipt(fn.transact({"from": self.addr[role]}))
        if receipt.status != 1:
            raise ChainUnavailable("transaction reverted")
        return {"tx": receipt.transactionHash.hex(), "block": receipt.blockNumber, "gas_used": receipt.gasUsed}

    def _log(self, op: Dict[str, Any]) -> None:
        if self.journal and not self._replaying:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with self.journal.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(op, sort_keys=True) + "\n")

    def _replay(self) -> None:
        if not self.journal or not self.journal.exists():
            return
        self._replaying = True
        try:
            for line in self.journal.read_text(encoding="utf-8").splitlines():
                op = json.loads(line)
                if op["op"] == "register":
                    self.register(op["lender"], op["commitment"], op["pack_ref"])
                elif op["op"] == "release":
                    self.release(op["lender"], op["commitment"])
                elif op["op"] == "anchor":
                    self._anchor_raw(op["root"], op["entries"], op["last"])
        finally:
            self._replaying = False

    # ------------------------------------------------------------------ invoice register
    def commitment(self, seller_tax_id: str, buyer_id: str, invoice_no: str, minor_units: int, currency: str, issue_date: str) -> str:
        msg = canonical_invoice(seller_tax_id, buyer_id, invoice_no, minor_units, currency, issue_date).encode()
        return hmac.new(self.key, msg, hashlib.sha256).hexdigest()

    def status(self, commitment: str) -> Dict[str, Any]:
        active, lender, at = self.registry.functions.status(bytes.fromhex(commitment)).call()
        return {"active": active, "holder": self.name_of.get(lender) if active else None, "registered_at": at if active else None}

    def register(self, lender: str, commitment: str, pack_ref: str) -> Dict[str, Any]:
        """Record financing. registered=False means another lender holds an active registration: do not fund."""
        if lender not in LENDERS:
            raise ValueError("unknown lender")
        with self._lock:
            fn = self.registry.functions.register(bytes.fromhex(commitment), bytes.fromhex(pack_ref[:64].ljust(64, "0")))
            ok = fn.call({"from": self.addr[lender]})
            before = self.status(commitment)
            receipt = self._tx(fn, lender)
            self._log({"op": "register", "lender": lender, "commitment": commitment, "pack_ref": pack_ref})  # refused attempts too
            return {"registered": bool(ok), "lender": lender, "holder": lender if ok else before["holder"], **receipt}

    def release(self, lender: str, commitment: str) -> Dict[str, Any]:
        with self._lock:
            receipt = self._tx(self.registry.functions.release(bytes.fromhex(commitment)), lender)
            self._log({"op": "release", "lender": lender, "commitment": commitment})
            return receipt

    # ------------------------------------------------------------------ audit anchoring
    def _anchor_raw(self, root_hex: str, entries: int, last_hex: str) -> Dict[str, Any]:
        receipt = self._tx(self.anchor_c.functions.anchor(bytes.fromhex(root_hex), entries, bytes.fromhex(last_hex)), "SME audit publisher")
        self._log({"op": "anchor", "root": root_hex, "entries": entries, "last": last_hex})
        return receipt

    def anchor(self, line_hashes: Sequence[str]) -> Dict[str, Any]:
        if not line_hashes:
            raise ValueError("nothing to anchor")
        with self._lock:
            r = merkle.root(line_hashes)
            receipt = self._anchor_raw(r, len(line_hashes), line_hashes[-1])
            return {"index": self.anchor_c.functions.count().call() - 1, "root": r, "entries": len(line_hashes), **receipt}

    def anchors(self) -> List[Dict[str, Any]]:
        out = []
        for i in range(self.anchor_c.functions.count().call()):
            root_b, entries, last, at, publisher = self.anchor_c.functions.anchors(i).call()
            out.append({"index": i, "root": root_b.hex(), "entries": entries, "last_entry_hash": last.hex(), "anchored_at": at,
                        "publisher": self.name_of.get(publisher, publisher)})
        return out

    def verify_log(self, line_hashes: Sequence[str]) -> Dict[str, Any]:
        """Does the local audit log still reproduce every on-chain anchor? (a rewrite or truncation fails)"""
        results = []
        for a in self.anchors():
            n = a["entries"]
            ok = len(line_hashes) >= n and merkle.root(line_hashes[:n]) == a["root"] and line_hashes[n - 1] == a["last_entry_hash"]
            results.append({**a, "reproduced": ok})
        return {"anchors": results, "all_reproduced": all(r["reproduced"] for r in results), "log_entries": len(line_hashes)}

    def inclusion(self, line_hashes: Sequence[str], index: int) -> Dict[str, Any]:
        """Proof that entry ``index`` is covered by the latest anchor that includes it."""
        for a in reversed(self.anchors()):
            if index < a["entries"]:
                path = merkle.proof(line_hashes[:a["entries"]], index)
                return {"entry": index, "line_sha256": line_hashes[index], "anchor_index": a["index"], "root": a["root"], "path": path,
                        "verified": merkle.verify_proof(line_hashes[index], path, a["root"])}
        raise LookupError("no anchor covers that entry yet")

    # ------------------------------------------------------------------ description
    def info(self) -> Dict[str, Any]:
        return {
            "network": "in-process EVM (py-evm via eth-tester), chain id %d" % self.w3.eth.chain_id,
            "block": self.w3.eth.block_number, "simulated_consortium": True,
            "contracts": {"InvoiceRegistry": self.registry.build, "AuditAnchor": self.anchor_c.build},
            "members": list(LENDERS), "registrations": self.registry.functions.registrations().call(),
            "duplicates_refused": self.registry.functions.duplicates_refused().call(),
            "anchors": self.anchor_c.functions.count().call(),
            "on_chain_data": "commitments (HMAC-SHA256), pack hashes, Merkle roots, timestamps; no invoice fields, names or amounts",
        }
