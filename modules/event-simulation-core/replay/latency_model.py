"""Compatibility wrapper for the original replay latency-model path."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from crypto_microstructure_trader.replay.latency_model import LatencyModel, LatencyStats
except ModuleNotFoundError as exc:
    if exc.name != "crypto_microstructure_trader":
        raise
    source_root = Path(__file__).resolve().parents[3] / "src"
    sys.path.insert(0, str(source_root))
    from crypto_microstructure_trader.replay.latency_model import LatencyModel, LatencyStats

__all__ = ["LatencyModel", "LatencyStats"]
