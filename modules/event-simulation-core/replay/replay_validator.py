from __future__ import annotations

from dataclasses import dataclass

from .event_store import EventStore, StoredEvent


@dataclass(frozen=True)
class ReplayValidationResult:
    deterministic: bool
    first_fingerprint: str
    second_fingerprint: str
    event_count: int
    reason: str


class ReplayValidator:
    def compare(self, first: list[StoredEvent], second: list[StoredEvent]) -> ReplayValidationResult:
        f1 = EventStore.fingerprint(first)
        f2 = EventStore.fingerprint(second)
        same = f1 == f2
        return ReplayValidationResult(
            deterministic=same,
            first_fingerprint=f1,
            second_fingerprint=f2,
            event_count=len(first),
            reason='deterministic' if same else 'event sequence changed across repeated runs',
        )
