from __future__ import annotations

from collections.abc import Iterator

import pytest

from crypto_microstructure_trader import EventStore, ReplayValidator, StoredEvent


def test_identical_sequences_are_deterministic(stored_event_factory) -> None:
    first = [stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)]
    second = [stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)]

    result = ReplayValidator().compare(first, second)

    assert result.deterministic is True
    assert result.first_fingerprint == result.second_fingerprint
    assert result.event_count == 2
    assert result.first_event_count == 2
    assert result.second_event_count == 2
    assert result.first_count == 2
    assert result.second_count == 2
    assert result.first_mismatch_index is None
    assert result.reason == "deterministic"


def test_changed_event_reports_first_mismatch(stored_event_factory) -> None:
    first = [stored_event_factory(timestamp=index) for index in range(4)]
    second = list(first)
    second[2] = stored_event_factory(timestamp=2, reason="changed")

    result = ReplayValidator().compare(iter(first), iter(second))

    assert result.deterministic is False
    assert result.first_mismatch_index == 2
    assert result.first_event_count == result.second_event_count == 4
    assert result.first_fingerprint != result.second_fingerprint
    assert result.event_count == 4


def test_shorter_second_sequence_reports_exhaustion_index(stored_event_factory) -> None:
    first = [stored_event_factory(timestamp=index) for index in range(3)]
    second = first[:2]

    result = ReplayValidator().compare(first, second)

    assert result.deterministic is False
    assert result.first_mismatch_index == 2
    assert result.first_event_count == 3
    assert result.second_event_count == 2
    assert result.event_count == 3


def test_longer_second_sequence_reports_exhaustion_index(stored_event_factory) -> None:
    first = [stored_event_factory(timestamp=index) for index in range(2)]
    second = [*first, stored_event_factory(timestamp=2)]

    result = ReplayValidator().compare(first, second)

    assert result.deterministic is False
    assert result.first_mismatch_index == 2
    assert result.first_event_count == 2
    assert result.second_event_count == 3
    assert result.event_count == 2


def test_content_and_length_changes_report_their_distinct_indexes(stored_event_factory) -> None:
    first = [stored_event_factory(timestamp=index) for index in range(3)]
    second = [stored_event_factory(timestamp=0, reason="changed"), *first[1:], first[-1]]

    result = ReplayValidator().compare(first, second)

    assert result.deterministic is False
    assert result.first_mismatch_index == 0
    assert result.first_event_count == 3
    assert result.second_event_count == 4
    assert result.reason == (
        "event changed at index 0; sequence length also changed at index 3: first=3, second=4"
    )


def test_empty_sequences_are_deterministic() -> None:
    result = ReplayValidator().compare([], [])

    assert result.deterministic is True
    assert result.first_fingerprint == EventStore.fingerprint([])
    assert result.second_fingerprint == EventStore.fingerprint([])
    assert result.event_count == 0
    assert result.first_mismatch_index is None


def test_compare_detects_canonical_difference_hidden_by_python_equality(
    stored_event_factory,
) -> None:
    integer = stored_event_factory(metadata={"numeric": 1})
    floating = stored_event_factory(metadata={"numeric": 1.0})
    assert integer == floating  # Python considers 1 and 1.0 equal inside mappings.

    result = ReplayValidator().compare([integer], [floating])

    assert result.deterministic is False
    assert result.first_mismatch_index == 0
    assert result.first_fingerprint != result.second_fingerprint


def test_compare_consumes_each_input_only_once(stored_event_factory) -> None:
    class SinglePass:
        def __init__(self, values: list[StoredEvent]) -> None:
            self.values = values
            self.iterations = 0

        def __iter__(self) -> Iterator[StoredEvent]:
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("iterable consumed more than once")
            yield from self.values

    first = SinglePass([stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)])
    second = SinglePass([stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)])

    result = ReplayValidator().compare(first, second)

    assert result.deterministic is True
    assert first.iterations == second.iterations == 1


def test_compare_rejects_aliased_one_shot_iterator(stored_event_factory) -> None:
    events = iter([stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)])

    with pytest.raises(ValueError, match="independent iterators"):
        ReplayValidator().compare(events, events)


def test_compare_allows_same_reusable_container(stored_event_factory) -> None:
    events = [stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)]

    result = ReplayValidator().compare(events, events)

    assert result.deterministic is True
    assert result.first_event_count == result.second_event_count == 2


def test_compare_rejects_non_event_items(stored_event_factory) -> None:
    with pytest.raises(TypeError):
        ReplayValidator().compare([stored_event_factory()], [object()])  # type: ignore[list-item]


def test_validation_result_is_frozen(stored_event_factory) -> None:
    result = ReplayValidator().compare([stored_event_factory()], [stored_event_factory()])

    with pytest.raises((AttributeError, TypeError)):
        result.deterministic = False  # type: ignore[misc]
