"""Compatibility wrapper for the original replay event-store path."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from crypto_microstructure_trader.replay.event_store import (
        FINGERPRINT_ALGORITHM,
        EventStore,
        EventStoreManifest,
        StoredEvent,
        canonical_event_bytes,
        canonical_jsonl_row,
    )
except ModuleNotFoundError as exc:
    if exc.name != "crypto_microstructure_trader":
        raise
    source_root = Path(__file__).resolve().parents[3] / "src"
    sys.path.insert(0, str(source_root))
    from crypto_microstructure_trader.replay.event_store import (
        FINGERPRINT_ALGORITHM,
        EventStore,
        EventStoreManifest,
        StoredEvent,
        canonical_event_bytes,
        canonical_jsonl_row,
    )

__all__ = [
    "FINGERPRINT_ALGORITHM",
    "EventStore",
    "EventStoreManifest",
    "StoredEvent",
    "canonical_event_bytes",
    "canonical_jsonl_row",
]
