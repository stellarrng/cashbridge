# Execution evidence

**These two files ship empty and must stay that way.**
`tests/test_packaging.py` fails the build if either is populated.

- `audit_hash_registry.json` — `[]`
- `sandbox_operation_logs.jsonl` — zero bytes

## Why empty matters

An earlier archive shipped with a pledge for `INV-2026-103` already in the
registry. A reviewer unzipping it and running `demo_walkthrough.py` hit
`DoubleFinancingError` immediately, because the invoice was already pledged —
while this file claimed the evidence started empty. Every unit test passed;
none of them looked at what was in the archive.

## Where runtime output goes

`demo_walkthrough.py` calls `config.runtime.use_fresh_run_directory()`, which
creates a timestamped directory under `data/demo_runs/` and points all audit,
registry and PDF writes at it. Each run is self-contained, repeated runs
cannot collide, and this directory is never touched.

The tests do the same thing through a per-test temp directory, so a test run
cannot mutate anything here either.

Nothing deletes evidence to make room. In a real deployment this directory
holds an operational audit trail that must accumulate; a demo that wiped it to
start cleanly would have replaced one bug with a worse one. Isolation, not
deletion.

## Reading the chain

`get_chain_head()` on either file returns the head hash. A chain verified only
against itself proves nothing to a party who does not trust the operator:
whoever controls the process can recompute every hash from genesis and produce
a valid chain. Anchor the head hash outside this system — counter-signed by
the funder, published, or written to append-only storage — if it is to mean
anything to a third party. See README §3.5.
