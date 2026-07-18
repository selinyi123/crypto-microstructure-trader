"""One-pass deterministic comparison for replay event sequences."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import zip_longest

from .event_store import StoredEvent, canonical_jsonl_row


@dataclass(frozen=True)
class ReplayValidationResult:
    deterministic: bool
    first_fingerprint: str
    second_fingerprint: str
    event_count: int
    reason: str
    first_event_count: int | None = None
    second_event_count: int | None = None
    first_mismatch_index: int | None = None

    def __post_init__(self) -> None:
        # Preserve compatibility with callers that still construct the original
        # five-field result while exposing explicit counts to newer consumers.
        if self.first_event_count is None:
            object.__setattr__(self, "first_event_count", self.event_count)
        if self.second_event_count is None:
            object.__setattr__(self, "second_event_count", self.event_count)

    @property
    def first_count(self) -> int:
        return self.first_event_count  # type: ignore[return-value]

    @property
    def second_count(self) -> int:
        return self.second_event_count  # type: ignore[return-value]


class ReplayValidator:
    def compare(
        self,
        first: Iterable[StoredEvent],
        second: Iterable[StoredEvent],
    ) -> ReplayValidationResult:
        """Compare two iterables without materializing either sequence.

        Equality is defined by canonical bytes, exactly matching fingerprint
        semantics.  This intentionally distinguishes JSON ``1`` from ``1.0``
        inside metadata even though Python's normal equality considers them
        equal.  The two inputs may be reusable containers or independent
        one-shot iterators, but they must not resolve to the same one-shot
        iterator because that would consume alternating events.
        """

        first_iterator = iter(first)
        second_iterator = iter(second)
        if first_iterator is second_iterator:
            raise ValueError("first and second must resolve to independent iterators")

        first_digest = hashlib.sha256()
        second_digest = hashlib.sha256()
        first_event_count = 0
        second_event_count = 0
        first_mismatch_index: int | None = None
        length_mismatch_index: int | None = None
        missing = object()

        for index, (first_event, second_event) in enumerate(
            zip_longest(first_iterator, second_iterator, fillvalue=missing)
        ):
            first_row: bytes | None = None
            second_row: bytes | None = None

            if first_event is not missing:
                first_row = canonical_jsonl_row(first_event)  # type: ignore[arg-type]
                first_digest.update(first_row)
                first_event_count += 1
            if second_event is not missing:
                second_row = canonical_jsonl_row(second_event)  # type: ignore[arg-type]
                second_digest.update(second_row)
                second_event_count += 1

            if first_mismatch_index is None and first_row != second_row:
                first_mismatch_index = index
            if length_mismatch_index is None and (first_event is missing) != (
                second_event is missing
            ):
                length_mismatch_index = index

        deterministic = first_mismatch_index is None
        if deterministic:
            reason = "deterministic"
        elif length_mismatch_index == first_mismatch_index:
            reason = (
                f"event sequence length changed at index {length_mismatch_index}: "
                f"first={first_event_count}, second={second_event_count}"
            )
        elif length_mismatch_index is not None:
            reason = (
                f"event changed at index {first_mismatch_index}; sequence length also changed "
                f"at index {length_mismatch_index}: first={first_event_count}, "
                f"second={second_event_count}"
            )
        else:
            reason = f"event changed at index {first_mismatch_index}"

        return ReplayValidationResult(
            deterministic=deterministic,
            first_fingerprint=first_digest.hexdigest(),
            second_fingerprint=second_digest.hexdigest(),
            event_count=first_event_count,
            reason=reason,
            first_event_count=first_event_count,
            second_event_count=second_event_count,
            first_mismatch_index=first_mismatch_index,
        )
