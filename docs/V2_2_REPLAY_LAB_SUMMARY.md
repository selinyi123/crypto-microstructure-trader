# Legacy v2.2 replay-lab summary

This document preserves and corrects the intent of the original upload. It is not a current release
specification.

## What the upload actually demonstrated

- serializing small, already-produced events to JSONL;
- hashing event sequences;
- summarizing a list of latency numbers; and
- checking whether two event sequences produced the same fingerprint.

## Withdrawn claims

The upload did not contain reproducible evidence for its “30 passed” statement. It also did not
implement market-data ingestion, market replay execution, queue-position estimation, order-book
normalization, kline filtering, dry-run/paper order execution, virtual fills, a ledger, fee
accounting, or exchange integration. Earlier wording suggesting otherwise was inaccurate.

The current v0.1.0 package improves validation, persistence, comparison, and test coverage, but it
still does not implement those missing trading-system capabilities. See the root `README.md` for
the supported scope and verification commands.
