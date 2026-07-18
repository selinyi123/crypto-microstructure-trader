# crypto-microstructure-trader

`crypto-microstructure-trader` is a **v0.1.0 pre-alpha, offline research core** for
small deterministic event-data experiments. It provides strict event validation, canonical JSONL
storage, sequence comparison, a conservative latency guard, and a command-line lab that exercises
those capabilities end to end.

This release establishes a testable foundation. It is not a trading system.

## What exists

- A validated event-scoring model with a configurable acceptance threshold.
- A strict `StoredEvent` schema with recursively immutable, JSON-compatible metadata.
- Atomic JSONL replacement and canonical SHA-256 fingerprints.
- Streaming manifest computation and one-pass, first-mismatch sequence comparison.
- Latency summaries that fail closed when samples are missing or invalid.
- A local CLI demonstration that generates synthetic data only.
- Compatibility wrappers for the original `modules/event-simulation-core` paths.

## What does not exist

There is currently **no** exchange or market-data adapter, order-book engine, historical replay
execution, queue/fill simulation, strategy backtest, paper-trading ledger, portfolio/risk system,
credential handling, or live order submission. The word “replay” in legacy filenames refers only
to comparing already-produced event sequences; it does not mean the project can replay a market.

Do not use this pre-alpha package to make or execute financial decisions.

## Requirements and installation

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) for the reproducible development path

Install the locked development environment from the repository root:

```console
uv sync --locked --extra dev
```

Run commands without activating the environment by prefixing them with `uv run`, or activate it
first. For example, on PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On a POSIX shell:

```console
source .venv/bin/activate
```

If `uv` is unavailable, an editable pip installation also works, but does not provide the same
lockfile guarantee. On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --editable ".[dev]"
```

On a POSIX shell:

```console
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --editable ".[dev]"
```

## CLI smoke workflow

The commands below assume the environment is active. If it is not, use `uv run cmt-lab` in place
of `cmt-lab`. Every subcommand is also available through
`python -m crypto_microstructure_trader`.

1. Generate three small synthetic event stores:

   ```console
   cmt-lab demo demo-output
   ```

   This creates `run-a.jsonl`, its identical copy `run-b.jsonl`, and a deliberately changed
   `run-changed.jsonl`. Existing demo files are protected; use `--force` only when you intentionally
   want to replace them. An empty, existing output directory is allowed. The command stages all
   three files before replacing targets and rolls back handled write or replacement failures. This
   is not a crash-atomic multi-file transaction: an operating-system, process, or power failure
   during final replacement may require rerunning the command with `--force`.

2. Inspect one store and its canonical fingerprint:

   ```console
   cmt-lab inspect demo-output/run-a.jsonl --json
   ```

3. Confirm identical event sequences. The command exits with status `0`:

   ```console
   cmt-lab compare demo-output/run-a.jsonl demo-output/run-b.jsonl --json
   ```

4. Detect the deliberately changed sequence. Status `1` is expected here, not a CLI failure:

   ```console
   cmt-lab compare demo-output/run-a.jsonl demo-output/run-changed.jsonl --json
   ```

5. Summarize synthetic latency samples and apply a cancellation threshold:

   ```console
   cmt-lab latency 40 60 80 --threshold 250 --json
   ```

Safe latency input exits `0`; cancellation or fail-closed input exits `1`; invalid data, runtime
errors, and protected overwrite attempts exit `2`.

## Python API example

```python
from crypto_microstructure_trader import Event, EventScorer

decision = EventScorer(threshold=0.72).score(
    Event(name="synthetic_signal", strength=0.8, timestamp=1.0)
)
assert decision.action == "accept"
```

`StoredEvent.timestamp` is a nonnegative signed 64-bit integer (`0` through `2^63 - 1`). Version
0.1.0 does not encode a time unit or clock schema in the field. The synthetic demo uses Unix epoch
milliseconds; real datasets must declare their convention externally and must not mix units.

## Development verification

```console
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
```

CI runs these checks on Linux with Python 3.11–3.14 and on Windows with Python 3.14.

## Package layout

- `src/crypto_microstructure_trader/` — supported package and CLI.
- `tests/` — behavioral, boundary, compatibility, and CLI tests.
- `modules/event-simulation-core/` — thin legacy import wrappers; new code should not import here.
- `docs/` — provenance notes for the earlier v2.2 upload.

The next credible milestone is an offline market-data adapter plus a small integration study of an
existing replay/fill engine. A custom matching or fill model should not be built until that study
shows an actual gap. See [the replay-engine evaluation](docs/REPLAY_ENGINE_EVALUATION.md) for the
candidate comparison and acceptance gates.

## Security and licensing

See [SECURITY.md](SECURITY.md) for reporting guidance. No software license has been selected yet;
the repository owner must make that legal decision before third-party reuse or distribution is
invited.
