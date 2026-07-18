# Replay-engine evaluation

Status: accepted direction for the next isolated spike; no engine dependency is
added in v0.1.0.

## Context

The current Replay Lab validates, fingerprints, and compares event snapshots.
It does not reconstruct an order book, advance a virtual clock, submit orders,
or simulate fills. Building those components locally before evaluating mature
engines would create a large correctness burden and make optimistic fill
assumptions easy to hide.

## Candidates

| Candidate | Relevant strengths | Cost and boundary | Decision |
| --- | --- | --- | --- |
| [HftBacktest](https://github.com/nkaz001/hftbacktest) | Focused market replay, L2/L3 book reconstruction, feed/order latency, and queue-aware fill models | Requires an explicit adapter from this project's event schema and sufficiently granular historical data; an engine still cannot repair poor source data | First integration spike |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Broad event-driven backtesting and live architecture, multi-venue support, portfolio/execution components, and a Rust core | Much larger operational and domain surface than this pre-alpha core; LGPL-3.0-or-later dependency and research-to-live concerns require separate review | Defer |

HftBacktest is MIT-licensed and is the narrower way to test the missing
microstructure assumptions. NautilusTrader remains a credible later option if
the project deliberately expands from an offline research utility into a
multi-venue trading platform.

## Spike scope

The next spike must remain offline and synthetic-first:

1. Define a versioned market-event schema with venue, instrument, event kind,
   sequence, side, price, quantity, and an explicit timestamp unit.
2. Convert one fixed, synthetic L2 stream into the candidate engine without
   network access or credentials.
3. Run one no-order replay and one deterministic limit-order scenario with
   explicitly selected latency and queue models.
4. Record the input fingerprint, engine version/configuration, output
   fingerprint, fills, fees, and rejection reasons in a reproducibility
   manifest.
5. Prove repeated-run equivalence in clean processes and document every model
   assumption that cannot be inferred from the source feed.

## Acceptance gates

The adapter is not accepted merely because an example runs. It must also:

- reject mixed timestamp units, non-monotonic sequences where the venue schema
  forbids them, and incomplete book initialization;
- avoid converting missing depth or latency into zero;
- cover mapping and failure paths with synthetic fixtures committed to the
  repository;
- remain optional so the small validation CLI can run without the engine; and
- make no paper- or live-trading path reachable.

Real exchange data, a target venue, fee schedules, and redistribution rights
remain owner decisions. Until those are confirmed, synthetic data is the only
accepted integration input.
