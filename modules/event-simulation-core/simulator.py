from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    name: str
    strength: float
    timestamp: float


@dataclass(frozen=True)
class Decision:
    action: str
    score: float
    reason: str


class EventScorer:
    def score(self, event: Event) -> Decision:
        normalized = max(0.0, min(1.0, event.strength))
        action = "accept" if normalized >= 0.72 else "observe"
        return Decision(action=action, score=normalized, reason=event.name)


if __name__ == "__main__":
    demo = Event(name="sample_event", strength=0.8, timestamp=1.0)
    print(EventScorer().score(demo))
