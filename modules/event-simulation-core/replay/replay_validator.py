"""Compatibility wrapper for the original replay-validator path."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from crypto_microstructure_trader.replay.replay_validator import (
        ReplayValidationResult,
        ReplayValidator,
    )
except ModuleNotFoundError as exc:
    if exc.name != "crypto_microstructure_trader":
        raise
    source_root = Path(__file__).resolve().parents[3] / "src"
    sys.path.insert(0, str(source_root))
    from crypto_microstructure_trader.replay.replay_validator import (
        ReplayValidationResult,
        ReplayValidator,
    )

__all__ = ["ReplayValidationResult", "ReplayValidator"]
