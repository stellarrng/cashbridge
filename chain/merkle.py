"""Merkle tree over the audit log's line hashes (RFC 6962 style, SHA-256, domain-separated).

leaf = SHA-256(0x00 || line_sha256 bytes); node = SHA-256(0x01 || left || right); an odd node is promoted unchanged
(RFC 6962 split at the largest power of two below n). Domain separation stops a leaf being passed off as an inner
node (second-preimage attack). An inclusion proof lets a lender check that ONE audit event (for example "Director
approved pack X") is covered by a root anchored on chain, without receiving the rest of the log.
"""
from __future__ import annotations

import hashlib
from typing import List, Sequence, Tuple


def _h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf(line_sha256_hex: str) -> bytes:
    return _h(b"\x00" + bytes.fromhex(line_sha256_hex))


def node(left: bytes, right: bytes) -> bytes:
    return _h(b"\x01" + left + right)


def _split(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def root_of_leaves(leaves: Sequence[bytes]) -> bytes:
    n = len(leaves)
    if n == 0:
        return _h(b"")
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node(root_of_leaves(leaves[:k]), root_of_leaves(leaves[k:]))


def root(line_hashes: Sequence[str]) -> str:
    return root_of_leaves([leaf(h) for h in line_hashes]).hex()


def proof(line_hashes: Sequence[str], index: int) -> List[Tuple[str, str]]:
    """Audit path for entry ``index``: list of (side, sibling hex), side = 'L' if the sibling is on the left."""
    if not 0 <= index < len(line_hashes):
        raise IndexError("entry outside the log")
    leaves = [leaf(h) for h in line_hashes]
    path: List[Tuple[str, str]] = []

    def walk(lo: int, hi: int) -> None:
        n = hi - lo
        if n == 1:
            return
        k = _split(n)
        if index < lo + k:
            walk(lo, lo + k)
            path.append(("R", root_of_leaves(leaves[lo + k:hi]).hex()))
        else:
            walk(lo + k, hi)
            path.append(("L", root_of_leaves(leaves[lo:lo + k]).hex()))

    walk(0, len(leaves))
    return path


def verify_proof(line_sha256_hex: str, path: Sequence[Tuple[str, str]], expected_root_hex: str) -> bool:
    acc = leaf(line_sha256_hex)
    for side, sibling in path:
        s = bytes.fromhex(sibling)
        acc = node(s, acc) if side == "L" else node(acc, s)
    return acc.hex() == expected_root_hex
