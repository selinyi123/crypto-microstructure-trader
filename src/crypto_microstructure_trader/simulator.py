"""Small, deterministic event-scoring primitives.

This module intentionally contains no exchange or execution logic.  It is a
strictly validated research primitive that can be reused by replay tooling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real


def _validated_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty or whitespace")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field_name} must contain only Unicode scalar values") from exc
    return value


def _validated_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a real number, not {type(value).__name__}")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


@dataclass(frozen=True)
class Event:
    """A validated input to :class:`EventScorer`.

    ``strength`` may be outside ``[0, 1]`` because scoring deliberately clamps
    it.  Non-finite values are rejected instead of accidentally passing a
    threshold comparison.
    """

    name: str
    strength: float
    timestamp: float

    def __post_init__(self) -> None:
        name = _validated_text(self.name, "name")
        strength = _validated_finite_number(self.strength, "strength")
        timestamp = _validated_finite_number(self.timestamp, "timestamp")
        if timestamp < 0:
            raise ValueError("timestamp must be non-negative")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "strength", strength)
        object.__setattr__(self, "timestamp", timestamp)


@dataclass(frozen=True)
class Decision:
    action: str
    score: float
    reason: str


class EventScorer:
    """Clamp event strength and classify it against a validated threshold."""

    def __init__(self, threshold: int | float = 0.72) -> None:
        normalized_threshold = _validated_finite_number(threshold, "threshold")
        if not 0.0 <= normalized_threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1 inclusive")
        self._threshold = normalized_threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def score(self, event: Event) -> Decision:
        if not isinstance(event, Event):
            raise TypeError("event must be an Event")
        normalized = max(0.0, min(1.0, event.strength))
        action = "accept" if normalized >= self._threshold else "observe"
        return Decision(action=action, score=normalized, reason=event.name)


def _demo() -> None:
    demo = Event(name="sample_event", strength=0.8, timestamp=1.0)
    print(EventScorer().score(demo))


if __name__ == "__main__":
    _demo()
