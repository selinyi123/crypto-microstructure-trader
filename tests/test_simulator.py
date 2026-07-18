from __future__ import annotations

import math

import pytest

from crypto_microstructure_trader import Decision, Event, EventScorer


def test_event_scorer_accepts_strength_at_default_threshold() -> None:
    decision = EventScorer().score(Event(name="sample", strength=0.72, timestamp=1.0))

    assert decision == Decision(action="accept", score=0.72, reason="sample")


def test_event_scorer_observes_strength_below_threshold() -> None:
    decision = EventScorer().score(Event(name="sample", strength=0.719, timestamp=1.0))

    assert decision.action == "observe"
    assert decision.score == 0.719


@pytest.mark.parametrize(
    ("strength", "normalized", "action"),
    [
        (-100.0, 0.0, "observe"),
        (-0.0, 0.0, "observe"),
        (0.0, 0.0, "observe"),
        (1.0, 1.0, "accept"),
        (100.0, 1.0, "accept"),
    ],
)
def test_event_scorer_clamps_finite_strength(
    strength: float, normalized: float, action: str
) -> None:
    decision = EventScorer().score(Event("bounded", strength, 0.0))

    assert decision.score == normalized
    assert decision.action == action


@pytest.mark.parametrize("threshold", [0.0, 0.25, 0.72, 1.0])
def test_event_scorer_accepts_boundary_safe_thresholds(threshold: float) -> None:
    scorer = EventScorer(threshold=threshold)

    assert scorer.threshold == threshold
    assert scorer.score(Event("boundary", threshold, 0)).action == "accept"


@pytest.mark.parametrize(
    "threshold", [-1.0, 1.0001, math.nan, math.inf, -math.inf, True, False, None, "0.72"]
)
def test_event_scorer_rejects_invalid_threshold(threshold: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        EventScorer(threshold=threshold)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["", " ", "\t\n", None, 12, "\ud800"])
def test_event_rejects_invalid_name(name: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        Event(name=name, strength=0.5, timestamp=1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "strength", [math.nan, math.inf, -math.inf, True, False, None, "0.5", complex(1, 2)]
)
def test_event_rejects_non_finite_or_non_numeric_strength(strength: object) -> None:
    with pytest.raises((TypeError, ValueError, OverflowError)):
        Event(name="bad", strength=strength, timestamp=1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "timestamp", [-0.001, math.nan, math.inf, -math.inf, True, False, None, "1.0"]
)
def test_event_rejects_invalid_timestamp(timestamp: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        Event(name="bad", strength=0.5, timestamp=timestamp)  # type: ignore[arg-type]


def test_event_allows_unicode_and_zero_timestamp() -> None:
    event = Event(name="合成信号🚦", strength=0.5, timestamp=0)

    assert event.name == "合成信号🚦"
    assert event.timestamp == 0


def test_event_is_frozen() -> None:
    event = Event(name="immutable", strength=0.5, timestamp=1)

    with pytest.raises((AttributeError, TypeError)):
        event.strength = 0.9  # type: ignore[misc]


def test_score_rejects_non_event_input() -> None:
    with pytest.raises(TypeError):
        EventScorer().score(object())  # type: ignore[arg-type]
