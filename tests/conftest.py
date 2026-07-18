from __future__ import annotations

from typing import Any

import pytest

from crypto_microstructure_trader import StoredEvent


@pytest.fixture
def stored_event_factory():
    def make(**overrides: Any) -> StoredEvent:
        values: dict[str, Any] = {
            "symbol": "BTC-USDT",
            "timestamp": 1_700_000_000_000,
            "event_type": "synthetic_signal",
            "action": "observe",
            "strength": 0.65,
            "confidence": 0.8,
            "reason": "synthetic fixture",
            "level_price": 35_000.0,
            "invalidation_price": 34_800.0,
            "metadata": {"sequence": 1, "source": "test"},
        }
        values.update(overrides)
        return StoredEvent(**values)

    return make
