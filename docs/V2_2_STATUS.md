# Legacy v2.2 status note

This file corrects the provenance note included in the original repository upload. “v2.2” was an
informal upload label, not a packaged release or evidence of two prior stable major versions.

The original note claimed “30 passed,” but the uploaded repository contained only one small test
and no configuration or report that could reproduce that number. The claim is therefore withdrawn.
Use the current test suite and CI result as the source of truth.

The legacy upload contained:

- a minimal event scorer;
- a JSONL writer/reader;
- a latency-summary helper; and
- a sequence-fingerprint comparison helper.

The supported implementation now lives under `src/crypto_microstructure_trader`. The files under
`modules/event-simulation-core` remain only as compatibility wrappers.
