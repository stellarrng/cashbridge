# On-chain exploration (Challenge bonus)

Two problems from the Security Self-Assessment that one company's own database cannot solve:

| Risk | Why a local database is not enough | What runs on chain |
|---|---|---|
| **05 Duplicate financing across lenders** | The SME's own invoice registry only stops the SME financing an invoice twice *through CashBridge*. A dishonest seller can pledge the same receivable to bank A and bank B; neither bank sees the other's books. | `InvoiceRegistry.vy`: a permissioned register shared by consortium lenders. A lender registers the invoice **when it funds**; a second lender registering the same invoice while it is active is refused (and the attempt is logged on chain). |
| **11 Audit compromise** | The audit log is hash-chained, so an edited line is detected, but an administrator with file access can rewrite the **whole** chain consistently and it verifies again. | `AuditAnchor.vy`: the Merkle root of the audit log is published at release and at the lender's decision. A rewritten or truncated log no longer reproduces the anchored root. The anchor can only grow ("audit log shrank" is refused). |

## Privacy: nothing about the invoice is on chain

Lenders cannot write invoice data to a shared ledger (bank secrecy, data protection). The register is keyed by a
**commitment**:

```
commitment = HMAC-SHA256(consortium key, "cb-invoice-v1|seller tax id|buyer id|invoice no|amount in minor units|currency|issue date")
```

Fields are normalised (case, spacing, integer minor units) so every member computes the same value for the same
invoice. The key is shared by members off chain; without it the commitment cannot be brute-forced from guessable
fields (a plain SHA-256 of an invoice number and amount could be). On chain there are only commitments, the hash of the
funding pack the lender verified, Merkle roots and timestamps. The test
`test_commitment_hides_invoice_data_and_normalises` searches every event log for the tax id, invoice number, buyer and
amount and finds none.

## Where it acts in the product

1. **Director releases the pack** → the audit log is anchored (Merkle root, entry count, last entry hash).
2. **Lender verifies** → two new rows in the hash re-check:
   *Not financed at another consortium lender (on-chain register)* and *Audit log reproduces every on-chain anchor*.
   The old row "Not financed at another lender: cannot be proven" is replaced by an actual check.
3. **Lender approves funding** → the invoice is registered on chain first. If another lender already holds it, the
   approval is refused with **409 "Duplicate financing refused … Funding was not recorded"** and the case stays SUBMITTED.
4. **Trust page** (both portals): block height, registrations, refused duplicates, the anchor table with "Reproduced /
   Does not match", **Anchor now** (SME), **Inclusion proof** for any audit entry (SME: proves one event is covered by
   an anchored root without disclosing the rest of the log), **Drill** (lender: a second lender tries to finance the
   same invoice and is refused on chain).

## Honest scope

| Real | Simulated / not done |
|---|---|
| Vyper 0.4.3 source compiled to EVM bytecode (`chain/build/*.json`, with source SHA-256; a test fails if the build is stale) | The chain is **in-process** (py-evm via eth-tester): it is not shared with anyone outside this server |
| Executed by py-evm, the Python reference EVM; real transactions, receipts, gas, events, reverts | "Simulated Lender B / C" are accounts in the same process, not other banks |
| Access control enforced by the contracts (non-members, non-admins, release by another lender all revert) | The consortium key is a demo key from the runtime folder (production refuses to start the module without `CASHBRIDGE_CONSORTIUM_KEY`); no HSM, no key rotation ceremony |
| Testnet deploy script `scripts/deploy_chain_testnet.py` (dry-run tested against the in-process EVM) | **Not run on Sepolia or any public network**: the build sandbox has no route to an RPC node. No address on a public explorer exists |
| A whole-log rewrite that passes the local hash-chain check is caught by the anchor (`EVID-04` in the trust scorecard) | Anchoring is only independent once the chain is run by parties other than the SME |

Why a permissioned EVM rather than a public chain: lenders need a shared, append-only record that no single member
controls, with membership (KYC'd lenders only) and no customer data. Public anchoring of the audit root (a few hundred
bytes per day) could go to a public chain in addition; the register itself belongs on a permissioned network.

## Files and tests

| File | Purpose |
|---|---|
| `chain/contracts/InvoiceRegistry.vy`, `chain/contracts/AuditAnchor.vy` | Contracts |
| `chain/build_contracts.py` → `chain/build/*.json` | Compile (`python -m chain.build_contracts`, needs `vyper==0.4.3`) |
| `chain/merkle.py` | RFC 6962-style Merkle tree (domain-separated leaves/nodes), inclusion proofs |
| `chain/ledger.py` | In-process EVM, commitments, register/release, anchors, verification, transaction journal for restarts |
| `ui/backend_real.py` (`_chain_checks`, `_register_financing`, `chain_*`), `api/main.py` `/api/chain/*` | Integration with release, verification and the funding decision |
| `frontend/src/features/audit-trust/OnChainPanel.tsx` | Trust page panel (EN / VI / 中文) |
| `tests/test_chain.py` (28) | Contract behaviour, privacy, Merkle proofs for sizes 1-17, journal replay, build freshness, the full lender flow, refusal when financed elsewhere, whole-log rewrite detection, turning the module off, deploy dry-run |
| `eval/trust_scorecard.py` | `FIN-04`, `EVID-04` (and `DOC-01` for PDF active content) |

Install: `pip install -r requirements-chain.txt` (already in `requirements-ml.txt` and the Docker image). Turn off with
`CASHBRIDGE_CHAIN=off`; without the packages the app runs and the two verification rows say "unavailable".

## References

- B. Laurie, A. Langley, E. Kasper, *Certificate Transparency*, RFC 6962 (2013), §2.1 Merkle hash trees (0x00 leaf / 0x01 node prefixes, split at the largest power of two): https://datatracker.ietf.org/doc/html/rfc6962
- Vyper 0.4 language documentation: https://docs.vyperlang.org/
- eth-tester / py-evm (in-process Ethereum test chain): https://github.com/ethereum/eth-tester
