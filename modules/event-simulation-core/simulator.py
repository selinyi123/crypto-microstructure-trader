"""Compatibility wrapper for the original module path.

New code should import :mod:`crypto_microstructure_trader.simulator`.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from crypto_microstructure_trader.simulator import Decision, Event, EventScorer
except ModuleNotFoundError as exc:
    if exc.name != "crypto_microstructure_trader":
        raise
    # Preserve ``python modules/event-simulation-core/simulator.py`` from a
    # source checkout where the package has not yet been installed.
    source_root = Path(__file__).resolve().parents[2] / "src"
    sys.path.insert(0, str(source_root))
    from crypto_microstructure_trader.simulator import Decision, Event, EventScorer

__all__ = ["Decision", "Event", "EventScorer"]


if __name__ == "__main__":
    demo = Event(name="sample_event", strength=0.8, timestamp=1.0)
    print(EventScorer().score(demo))
