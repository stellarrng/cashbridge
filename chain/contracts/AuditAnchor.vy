# pragma version 0.4.3
"""
@title Audit-log anchor
@notice Publishes the Merkle root of an installation's hash-chained audit log at a point in time.
        Afterwards the operator cannot rewrite or drop past entries without the recomputed root
        disagreeing with a root that third parties (lenders) can read on chain. Only roots are stored.
"""

struct Anchor:
    root: bytes32
    entries: uint256
    last_entry_hash: bytes32
    anchored_at: uint256
    publisher: address

event Anchored:
    index: indexed(uint256)
    root: bytes32
    entries: uint256

publishers: public(HashMap[address, bool])
admin: public(address)
anchors: public(HashMap[uint256, Anchor])
count: public(uint256)


@deploy
def __init__():
    self.admin = msg.sender
    self.publishers[msg.sender] = True


@external
def add_publisher(who: address):
    assert msg.sender == self.admin, "only admin"
    self.publishers[who] = True


@external
def anchor(root: bytes32, entries: uint256, last_entry_hash: bytes32) -> uint256:
    assert self.publishers[msg.sender], "not a publisher"
    assert root != empty(bytes32), "empty root"
    if self.count > 0:
        # The log only grows: an anchor may never cover fewer entries than the previous one.
        assert entries >= self.anchors[self.count - 1].entries, "audit log shrank"
    index: uint256 = self.count
    self.anchors[index] = Anchor(root=root, entries=entries, last_entry_hash=last_entry_hash, anchored_at=block.timestamp, publisher=msg.sender)
    self.count = index + 1
    log Anchored(index=index, root=root, entries=entries)
    return index
