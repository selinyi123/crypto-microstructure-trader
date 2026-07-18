# Changelog

All notable changes are recorded here. The project is pre-alpha and does not yet promise API
stability.

## 0.1.0 - 2026-07-18

### Added

- Installable `src`-layout Python package and `cmt-lab` command.
- Strict event, stored-event, metadata, and latency validation.
- Atomic canonical JSONL event storage, manifests, and SHA-256 fingerprints.
- Streaming deterministic-sequence comparison with first-mismatch reporting.
- Synthetic CLI demo, inspection, comparison, and latency workflows.
- Boundary, failure-path, compatibility, packaging, and CLI tests.
- Locked development dependencies and multi-platform CI.
- A source-backed replay-engine evaluation and acceptance gates for the next isolated spike.

### Changed

- Converted the original module files into compatibility wrappers around the supported package.
- Corrected legacy status documents so they no longer claim unverified test results or unimplemented
  replay, queue, order-book, kline, and paper-trading capabilities.

### Security

- Event-store writes use same-directory temporary files and atomic replacement so a failed write
  does not truncate an existing store.
- Invalid latency data fails closed instead of silently appearing safe.
