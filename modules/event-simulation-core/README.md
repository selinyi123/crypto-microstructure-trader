# Legacy event-simulation-core path

This directory is retained for compatibility with the initial repository layout. Its Python files
delegate to the supported package under `src/crypto_microstructure_trader`; they are not a second
implementation.

New code should install the repository and import from `crypto_microstructure_trader`:

```python
from crypto_microstructure_trader import Event, EventScorer
```

The package is an offline pre-alpha research core. It does not provide market replay execution,
an order book, queue or fill simulation, backtesting, paper trading, credentials, or live exchange
actions.
