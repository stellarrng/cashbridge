# pragma version 0.4.3
"""
@title Cross-lender invoice financing register (permissioned)
@notice Lenders record that they finance an invoice, keyed by a COMMITMENT, never by invoice data.
        commitment = HMAC-SHA256(consortium key, canonical invoice fields) is computed off-chain by members;
        without the key the chain reveals nothing about seller, buyer, number or amount.
        A second lender registering the same commitment while it is active is refused: duplicate financing
        of one receivable across lenders is caught at the moment of funding.
"""

struct Record:
    lender: address
    registered_at: uint256
    released_at: uint256
    active: bool
    pack_ref: bytes32      # hash of the funding pack the lender verified (binds the record to the evidence)

event MemberAdded:
    member: indexed(address)
    name: String[64]

event MemberRemoved:
    member: indexed(address)

event Registered:
    commitment: indexed(bytes32)
    lender: indexed(address)
    pack_ref: bytes32

event DuplicateAttempt:
    commitment: indexed(bytes32)
    lender: indexed(address)
    holder: address

event Released:
    commitment: indexed(bytes32)
    lender: indexed(address)

admin: public(address)
members: public(HashMap[address, bool])
member_name: public(HashMap[address, String[64]])
records: public(HashMap[bytes32, Record])
registrations: public(uint256)
duplicates_refused: public(uint256)


@deploy
def __init__():
    self.admin = msg.sender


@external
def add_member(member: address, name: String[64]):
    assert msg.sender == self.admin, "only the consortium admin"
    assert member != empty(address), "zero address"
    self.members[member] = True
    self.member_name[member] = name
    log MemberAdded(member=member, name=name)


@external
def remove_member(member: address):
    assert msg.sender == self.admin, "only the consortium admin"
    self.members[member] = False
    log MemberRemoved(member=member)


@external
def register(commitment: bytes32, pack_ref: bytes32) -> bool:
    """
    @notice Record financing of the invoice behind `commitment`. Returns False (and logs the attempt)
            when another registration is active; the caller must not fund.
    """
    assert self.members[msg.sender], "not a consortium lender"
    assert commitment != empty(bytes32), "empty commitment"
    current: Record = self.records[commitment]
    if current.active:
        self.duplicates_refused += 1
        log DuplicateAttempt(commitment=commitment, lender=msg.sender, holder=current.lender)
        return False
    self.records[commitment] = Record(lender=msg.sender, registered_at=block.timestamp, released_at=0, active=True, pack_ref=pack_ref)
    self.registrations += 1
    log Registered(commitment=commitment, lender=msg.sender, pack_ref=pack_ref)
    return True


@external
def release(commitment: bytes32):
    """@notice The financing lender frees the invoice (repaid or not funded); only it can."""
    current: Record = self.records[commitment]
    assert current.active, "not registered"
    assert current.lender == msg.sender, "only the registering lender"
    self.records[commitment].active = False
    self.records[commitment].released_at = block.timestamp
    log Released(commitment=commitment, lender=msg.sender)


@view
@external
def status(commitment: bytes32) -> (bool, address, uint256):
    r: Record = self.records[commitment]
    return (r.active, r.lender, r.registered_at)
