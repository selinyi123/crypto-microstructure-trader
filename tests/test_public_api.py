from __future__ import annotations

from importlib.metadata import version

import crypto_microstructure_trader as package


def test_version_is_consistent_with_distribution_metadata() -> None:
    assert package.__version__ == "0.1.0"
    assert version("crypto-microstructure-trader") == package.__version__


def test_expected_public_api_is_exported() -> None:
    expected = {
        "Decision",
        "Event",
        "EventScorer",
        "EventStore",
        "EventStoreManifest",
        "LatencyModel",
        "LatencyStats",
        "ReplayValidationResult",
        "ReplayValidator",
        "StoredEvent",
    }

    assert expected <= set(package.__all__)
    for name in expected:
        assert getattr(package, name) is not None


def test_public_exports_are_the_canonical_classes() -> None:
    from crypto_microstructure_trader.replay.event_store import EventStore, StoredEvent
    from crypto_microstructure_trader.replay.latency_model import LatencyModel
    from crypto_microstructure_trader.replay.replay_validator import ReplayValidator
    from crypto_microstructure_trader.simulator import EventScorer

    assert package.EventStore is EventStore
    assert package.StoredEvent is StoredEvent
    assert package.LatencyModel is LatencyModel
    assert package.ReplayValidator is ReplayValidator
    assert package.EventScorer is EventScorer
