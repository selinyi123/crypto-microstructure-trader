from __future__ import annotations

import hashlib
import importlib
import json
import math
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import MappingProxyType

import pytest

from crypto_microstructure_trader import EventStore, EventStoreManifest, StoredEvent


def thaw(value):
    """Convert recursively frozen metadata to ordinary containers for assertions."""

    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


@pytest.mark.parametrize("field", ["symbol", "event_type", "action", "reason"])
@pytest.mark.parametrize("value", ["", " ", "\t\n", None, 7, "\ud800"])
def test_stored_event_rejects_invalid_required_text(stored_event_factory, field, value) -> None:
    with pytest.raises((TypeError, ValueError)):
        stored_event_factory(**{field: value})


@pytest.mark.parametrize("timestamp", [-1, 1.5, True, False, None, "1", math.inf, math.nan])
def test_stored_event_rejects_invalid_timestamp(stored_event_factory, timestamp) -> None:
    with pytest.raises((TypeError, ValueError)):
        stored_event_factory(timestamp=timestamp)


def test_stored_event_accepts_int64_timestamp_boundaries(stored_event_factory) -> None:
    assert stored_event_factory(timestamp=0).timestamp == 0
    assert stored_event_factory(timestamp=(1 << 63) - 1).timestamp == (1 << 63) - 1


def test_stored_event_rejects_timestamp_above_int64_range(stored_event_factory) -> None:
    with pytest.raises(ValueError, match="timestamp must be between"):
        stored_event_factory(timestamp=1 << 63)


@pytest.mark.parametrize("field", ["strength", "confidence"])
@pytest.mark.parametrize(
    "value", [-0.001, 1.001, math.nan, math.inf, -math.inf, True, False, None, "0.5"]
)
def test_stored_event_rejects_invalid_unit_interval(stored_event_factory, field, value) -> None:
    with pytest.raises((TypeError, ValueError)):
        stored_event_factory(**{field: value})


@pytest.mark.parametrize("field", ["level_price", "invalidation_price"])
@pytest.mark.parametrize("value", [0, -0.0, -1, math.nan, math.inf, -math.inf, True, False, "1.0"])
def test_stored_event_rejects_invalid_optional_price(stored_event_factory, field, value) -> None:
    with pytest.raises((TypeError, ValueError)):
        stored_event_factory(**{field: value})


@pytest.mark.parametrize("field", ["level_price", "invalidation_price"])
def test_stored_event_accepts_none_optional_price(stored_event_factory, field) -> None:
    assert getattr(stored_event_factory(**{field: None}), field) is None


def test_stored_event_accepts_unit_interval_boundaries(stored_event_factory) -> None:
    event = stored_event_factory(strength=0, confidence=1)

    assert event.strength == 0
    assert event.confidence == 1


def test_stored_event_recursively_freezes_metadata(stored_event_factory) -> None:
    source = {"nested": {"values": [1, {"ok": True}]}, "nothing": None}
    event = stored_event_factory(metadata=source)
    source["nested"]["values"].append(2)

    assert isinstance(event.metadata, MappingProxyType)
    assert isinstance(event.metadata["nested"], MappingProxyType)
    assert isinstance(event.metadata["nested"]["values"], tuple)
    assert thaw(event.metadata) == {
        "nested": {"values": [1, {"ok": True}]},
        "nothing": None,
    }
    with pytest.raises(TypeError):
        event.metadata["new"] = "blocked"  # type: ignore[index]


def test_stored_event_accepts_already_frozen_metadata(stored_event_factory) -> None:
    metadata = MappingProxyType({"nested": MappingProxyType({"items": (1, 2)})})

    event = stored_event_factory(metadata=metadata)

    assert thaw(event.metadata) == {"nested": {"items": [1, 2]}}


def test_stored_event_copies_mutable_metadata(stored_event_factory) -> None:
    source = {"items": [1, 2]}
    event = stored_event_factory(metadata=source)
    source["items"][0] = 99

    assert event.metadata["items"] == (1, 2)


@pytest.mark.parametrize(
    "metadata",
    [
        {1: "non-string key"},
        {"bad": {1, 2}},
        {"bad": b"bytes"},
        {"bad": object()},
        {"bad": math.nan},
        {"bad": math.inf},
        {"bad": -math.inf},
        {"\ud800": "surrogate key"},
        {"bad": "\udfff"},
        ["not", "a", "mapping"],
        None,
    ],
)
def test_stored_event_rejects_non_json_metadata(stored_event_factory, metadata) -> None:
    with pytest.raises((TypeError, ValueError)):
        stored_event_factory(metadata=metadata)


def test_stored_event_rejects_direct_metadata_cycle(stored_event_factory) -> None:
    metadata: dict[str, object] = {}
    metadata["self"] = metadata

    with pytest.raises(ValueError, match="cycl"):
        stored_event_factory(metadata=metadata)


def test_stored_event_rejects_indirect_metadata_cycle(stored_event_factory) -> None:
    first: dict[str, object] = {}
    second: list[object] = [first]
    first["second"] = second

    with pytest.raises(ValueError, match="cycl"):
        stored_event_factory(metadata=first)


def test_stored_event_allows_shared_noncyclic_metadata(stored_event_factory) -> None:
    shared = {"value": 1}

    event = stored_event_factory(metadata={"a": shared, "b": shared})

    assert thaw(event.metadata) == {"a": {"value": 1}, "b": {"value": 1}}


def test_write_read_round_trip(tmp_path: Path, stored_event_factory) -> None:
    path = tmp_path / "nested" / "events.jsonl"
    events = [
        stored_event_factory(metadata={"文字": "你好", "emoji": "🚦"}),
        stored_event_factory(timestamp=2, level_price=None, invalidation_price=None),
    ]

    EventStore(path).write(iter(events))

    loaded = EventStore(path).read()
    assert loaded == events
    assert thaw(loaded[0].metadata) == {"文字": "你好", "emoji": "🚦"}


def test_write_returns_matching_manifest(tmp_path: Path, stored_event_factory) -> None:
    path = tmp_path / "events.jsonl"
    events = [stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)]
    store = EventStore(path)

    returned = store.write(events)

    assert returned == store.manifest()
    assert returned.event_count == 2
    assert returned.fingerprint == EventStore.fingerprint(events)


def test_empty_write_returns_empty_manifest(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    store = EventStore(path)

    returned = store.write([])

    assert path.read_bytes() == b""
    assert returned == store.manifest()
    assert returned == EventStoreManifest(0, hashlib.sha256(b"").hexdigest())


def test_write_emits_one_compact_canonical_json_object_per_line(
    tmp_path: Path, stored_event_factory
) -> None:
    path = tmp_path / "events.jsonl"
    EventStore(path).write([stored_event_factory(metadata={"z": 1, "a": 2})])

    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert raw.count("\n") == 1
    assert '"action":"observe"' in raw
    assert '"metadata":{"a":2,"z":1}' in raw
    assert "你好" not in raw or "\\u" not in raw


def test_write_rejects_non_stored_event_without_replacing_file(
    tmp_path: Path, stored_event_factory
) -> None:
    path = tmp_path / "events.jsonl"
    store = EventStore(path)
    original = stored_event_factory(reason="original")
    store.write([original])

    with pytest.raises(TypeError):
        store.write([object()])  # type: ignore[list-item]

    assert store.read() == [original]


def test_generator_failure_preserves_existing_file_and_removes_temporary_file(
    tmp_path: Path, stored_event_factory
) -> None:
    path = tmp_path / "events.jsonl"
    store = EventStore(path)
    original = stored_event_factory(reason="original")
    store.write([original])
    before = set(tmp_path.iterdir())

    def failing_events() -> Iterator[StoredEvent]:
        yield stored_event_factory(reason="not committed")
        raise RuntimeError("synthetic generator failure")

    with pytest.raises(RuntimeError, match="synthetic generator failure"):
        store.write(failing_events())

    assert store.read() == [original]
    assert set(tmp_path.iterdir()) == before


def test_replace_failure_preserves_existing_file_and_removes_temporary_file(
    tmp_path: Path, stored_event_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_store_module = importlib.import_module("crypto_microstructure_trader.replay.event_store")
    path = tmp_path / "events.jsonl"
    store = EventStore(path)
    original = stored_event_factory(reason="original")
    store.write([original])
    before = set(tmp_path.iterdir())

    def fail_replace(source, target) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(event_store_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic replace failure"):
        store.write([stored_event_factory(reason="replacement")])

    assert store.read() == [original]
    assert set(tmp_path.iterdir()) == before


def test_missing_store_reads_as_empty_for_legacy_compatibility(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "missing.jsonl")

    assert store.read() == []
    assert list(store.iter_read()) == []


def test_missing_store_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        EventStore(tmp_path / "missing.jsonl").manifest()


@pytest.mark.parametrize("raw", ["\n", " \n", "\t\r\n"])
def test_blank_jsonl_line_is_invalid(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        EventStore(path).read()


def test_blank_line_between_valid_events_is_invalid(tmp_path: Path, stored_event_factory) -> None:
    path = tmp_path / "events.jsonl"
    store = EventStore(path)
    store.write([stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)])
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(f"{lines[0]}\n\n{lines[1]}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        store.read()


@pytest.mark.parametrize(
    "raw",
    [
        "not json\n",
        "[]\n",
        "null\n",
        '{"symbol":"only"}\n',
        '{"symbol":"a","symbol":"b"}\n',
    ],
)
def test_malformed_jsonl_is_rejected_with_line_number(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        EventStore(path).read()


def test_invalid_raw_utf8_has_contextual_error(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"\xff\n")

    with pytest.raises(ValueError, match="invalid event store line 1"):
        EventStore(path).read()


def test_deeply_nested_json_has_contextual_error(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    nested_metadata = "null"
    for _ in range(2_000):
        nested_metadata = f'{{"nested":{nested_metadata}}}'
    path.write_text(
        '{"symbol":"BTC-USDT","timestamp":1,"event_type":"signal",'
        '"action":"observe","strength":0.5,"confidence":0.5,"reason":"test",'
        f'"level_price":null,"invalidation_price":null,"metadata":{nested_metadata}}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="line 1.*nesting depth"):
        EventStore(path).read()


def test_escaped_surrogate_has_contextual_error(tmp_path: Path, stored_event_factory) -> None:
    path = tmp_path / "events.jsonl"
    payload = stored_event_factory().to_dict()
    payload["reason"] = "\ud800"
    path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid event store line 1"):
        EventStore(path).read()


def test_unknown_json_field_is_rejected(tmp_path: Path, stored_event_factory) -> None:
    path = tmp_path / "events.jsonl"
    EventStore(path).write([stored_event_factory()])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unknown"] = True
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        EventStore(path).read()


def test_iter_read_is_lazy(tmp_path: Path, stored_event_factory) -> None:
    path = tmp_path / "events.jsonl"
    EventStore(path).write([stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)])
    iterator = EventStore(path).iter_read()

    assert not isinstance(iterator, list)
    assert next(iterator).timestamp == 1
    assert next(iterator).timestamp == 2
    with pytest.raises(StopIteration):
        next(iterator)


def test_fingerprint_empty_sequence_uses_empty_sha256() -> None:
    assert EventStore.fingerprint([]) == hashlib.sha256(b"").hexdigest()


def test_fingerprint_is_stable_across_round_trip(tmp_path: Path, stored_event_factory) -> None:
    events = [stored_event_factory(timestamp=1), stored_event_factory(timestamp=2)]
    path = tmp_path / "events.jsonl"
    store = EventStore(path)
    store.write(events)

    assert EventStore.fingerprint(iter(events)) == EventStore.fingerprint(store.iter_read())


def test_fingerprint_is_independent_of_metadata_insertion_order(stored_event_factory) -> None:
    first = stored_event_factory(metadata={"a": 1, "b": 2})
    second = stored_event_factory(metadata={"b": 2, "a": 1})

    assert EventStore.fingerprint([first]) == EventStore.fingerprint([second])


def test_fingerprint_changes_with_order(stored_event_factory) -> None:
    first = stored_event_factory(timestamp=1)
    second = stored_event_factory(timestamp=2)

    assert EventStore.fingerprint([first, second]) != EventStore.fingerprint([second, first])


def test_fingerprint_rejects_wrong_item_type() -> None:
    with pytest.raises(TypeError):
        EventStore.fingerprint([object()])  # type: ignore[list-item]


def test_manifest_reports_streamed_count_and_fingerprint(
    tmp_path: Path, stored_event_factory
) -> None:
    events = [stored_event_factory(timestamp=index) for index in range(5)]
    path = tmp_path / "events.jsonl"
    store = EventStore(path)
    store.write(events)

    manifest = store.manifest()

    assert manifest == EventStoreManifest(
        event_count=5,
        fingerprint=EventStore.fingerprint(events),
        fingerprint_algorithm="sha256-jsonl-v1",
    )


def test_manifest_is_frozen() -> None:
    manifest = EventStoreManifest(0, hashlib.sha256(b"").hexdigest())

    with pytest.raises((AttributeError, TypeError)):
        manifest.event_count = 1  # type: ignore[misc]


@pytest.mark.parametrize("event_count", [-1, 1.5, True, False, None, "1"])
def test_manifest_rejects_invalid_event_count(event_count) -> None:
    with pytest.raises((TypeError, ValueError)):
        EventStoreManifest(event_count, hashlib.sha256(b"").hexdigest())


@pytest.mark.parametrize("field", ["fingerprint", "fingerprint_algorithm"])
@pytest.mark.parametrize("value", ["", " ", "\t\n", "\ud800", None, 1])
def test_manifest_rejects_invalid_text(field, value) -> None:
    values = {
        "event_count": 0,
        "fingerprint": hashlib.sha256(b"").hexdigest(),
        "fingerprint_algorithm": "sha256-jsonl-v1",
    }
    values[field] = value

    with pytest.raises((TypeError, ValueError)):
        EventStoreManifest(**values)


def test_event_store_accepts_string_path(tmp_path: Path, stored_event_factory) -> None:
    path = tmp_path / "events.jsonl"
    store = EventStore(str(path))
    store.write([stored_event_factory()])

    assert len(store.read()) == 1


def test_event_store_rejects_directory_as_input(tmp_path: Path) -> None:
    with pytest.raises((IsADirectoryError, OSError, ValueError)):
        EventStore(tmp_path).read()


def test_metadata_is_a_mapping_after_read(tmp_path: Path, stored_event_factory) -> None:
    path = tmp_path / "events.jsonl"
    EventStore(path).write([stored_event_factory()])

    assert isinstance(EventStore(path).read()[0].metadata, Mapping)
