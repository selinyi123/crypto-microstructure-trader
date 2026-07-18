"""Strict, deterministic JSON Lines persistence for replay events."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from numbers import Integral, Real
from pathlib import Path
from types import MappingProxyType
from typing import Any

FINGERPRINT_ALGORITHM = "sha256-jsonl-v1"
_MAX_TIMESTAMP = (1 << 63) - 1


def _validated_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty or whitespace")
    _validate_unicode_scalar_string(value, field_name)
    return value


def _validate_unicode_scalar_string(value: str, field_name: str) -> None:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field_name} must contain only Unicode scalar values") from exc


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


def _validated_unit_interval(value: object, field_name: str) -> float:
    number = _validated_finite_number(value, field_name)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1 inclusive")
    return number


def _validated_optional_positive(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    number = _validated_finite_number(value, field_name)
    if number <= 0:
        raise ValueError(f"{field_name} must be positive when provided")
    return number


def _freeze_json(value: object, field_name: str, active_containers: set[int]) -> Any:
    """Validate JSON data and return a recursively immutable defensive copy."""

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        _validate_unicode_scalar_string(value, field_name)
        return value
    if isinstance(value, int):
        normalized_integer = int(value)
        try:
            json.dumps(normalized_integer, allow_nan=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{field_name} contains an integer that cannot be encoded") from exc
        return normalized_integer
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must not contain non-finite numbers")
        return float(value)

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active_containers:
            raise ValueError(f"{field_name} must not contain reference cycles")
        active_containers.add(identity)
        try:
            frozen: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError(f"{field_name} object keys must be strings")
                _validate_unicode_scalar_string(key, f"{field_name} key")
                frozen[key] = _freeze_json(
                    item,
                    f"{field_name}[{key!r}]",
                    active_containers,
                )
            return MappingProxyType(frozen)
        finally:
            active_containers.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active_containers:
            raise ValueError(f"{field_name} must not contain reference cycles")
        active_containers.add(identity)
        try:
            return tuple(
                _freeze_json(item, f"{field_name}[{index}]", active_containers)
                for index, item in enumerate(value)
            )
        finally:
            active_containers.remove(identity)

    raise TypeError(f"{field_name} contains non-JSON value of type {type(value).__name__}")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class StoredEvent:
    """A strictly validated event suitable for deterministic persistence."""

    symbol: str
    timestamp: int
    event_type: str
    action: str
    strength: float
    confidence: float
    reason: str
    level_price: float | None = None
    invalidation_price: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        symbol = _validated_text(self.symbol, "symbol")
        event_type = _validated_text(self.event_type, "event_type")
        action = _validated_text(self.action, "action")
        reason = _validated_text(self.reason, "reason")

        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, Integral):
            raise TypeError("timestamp must be a non-negative integer")
        timestamp = int(self.timestamp)
        # A signed 64-bit bound keeps snapshots portable across common database,
        # columnar-data, and replay-tool timestamp representations while retaining
        # the existing non-negative timestamp contract.
        if not 0 <= timestamp <= _MAX_TIMESTAMP:
            raise ValueError(f"timestamp must be between 0 and {_MAX_TIMESTAMP} inclusive")

        strength = _validated_unit_interval(self.strength, "strength")
        confidence = _validated_unit_interval(self.confidence, "confidence")
        level_price = _validated_optional_positive(self.level_price, "level_price")
        invalidation_price = _validated_optional_positive(
            self.invalidation_price, "invalidation_price"
        )
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a JSON object")
        try:
            metadata = _freeze_json(self.metadata, "metadata", set())
        except RecursionError as exc:
            raise ValueError("metadata exceeds the supported nesting depth") from exc

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "strength", strength)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "level_price", level_price)
        object.__setattr__(self, "invalidation_price", invalidation_price)
        object.__setattr__(self, "metadata", metadata)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible representation of this event."""

        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "action": self.action,
            "strength": self.strength,
            "confidence": self.confidence,
            "reason": self.reason,
            "level_price": self.level_price,
            "invalidation_price": self.invalidation_price,
            "metadata": _thaw_json(self.metadata),
        }


@dataclass(frozen=True)
class EventStoreManifest:
    event_count: int
    fingerprint: str
    fingerprint_algorithm: str = FINGERPRINT_ALGORITHM

    def __post_init__(self) -> None:
        if isinstance(self.event_count, bool) or not isinstance(self.event_count, Integral):
            raise TypeError("event_count must be a non-negative integer")
        if self.event_count < 0:
            raise ValueError("event_count must be non-negative")
        fingerprint = _validated_text(self.fingerprint, "fingerprint")
        fingerprint_algorithm = _validated_text(self.fingerprint_algorithm, "fingerprint_algorithm")
        object.__setattr__(self, "event_count", int(self.event_count))
        object.__setattr__(self, "fingerprint", fingerprint)
        object.__setattr__(self, "fingerprint_algorithm", fingerprint_algorithm)


def canonical_event_bytes(event: StoredEvent) -> bytes:
    """Encode one event using the canonical representation used for hashes."""

    if not isinstance(event, StoredEvent):
        raise TypeError("event store entries must be StoredEvent instances")
    payload = json.dumps(
        event.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    # StoredEvent has already rejected non-scalar surrogate code points.  Keep
    # strict encoding here as a final invariant rather than using replacement.
    return payload.encode("utf-8", errors="strict")


def canonical_jsonl_row(event: StoredEvent) -> bytes:
    """Return the exact canonical bytes hashed and written for one JSONL row."""

    return canonical_event_bytes(event) + b"\n"


class _DuplicateKeyError(ValueError):
    pass


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON number {token!r} is not permitted")


def _decode_event(raw_line: bytes, line_number: int) -> StoredEvent:
    if not raw_line.strip():
        raise ValueError(f"invalid event store line {line_number}: blank lines are not permitted")
    try:
        decoded = raw_line.decode("utf-8", errors="strict")
        record = json.loads(
            decoded,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(record, dict):
            raise TypeError("event row must be a JSON object")
        return StoredEvent(**record)
    except RecursionError as exc:
        raise ValueError(
            f"invalid event store line {line_number}: JSON exceeds the supported nesting depth"
        ) from exc
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid event store line {line_number}: {exc}") from exc


def _sync_parent_directory(parent: Path) -> None:
    """Best-effort directory fsync after replacement.

    Directory descriptors are unavailable on some supported platforms.  The
    file itself is always flushed and fsynced before replacement; only this
    extra durability barrier is best effort.
    """

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(parent, flags)
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)


class EventStore:
    """Persist a complete event snapshot as strict canonical JSON Lines."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, events: Iterable[StoredEvent]) -> EventStoreManifest:
        """Atomically replace the snapshot with ``events``.

        The temporary file is created beside the destination so ``os.replace``
        stays on the same filesystem.  If validation, iteration, writing, or
        replacement fails, the previous snapshot is left untouched.
        """

        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        temporary_path = Path(temporary_name)
        descriptor_open = True
        digest = hashlib.sha256()
        event_count = 0
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor_open = False
                for event in events:
                    row = canonical_jsonl_row(event)
                    handle.write(row)
                    digest.update(row)
                    event_count += 1
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except BaseException:
            if descriptor_open:
                with suppress(OSError):
                    os.close(descriptor)
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
            raise
        _sync_parent_directory(self.path.parent)
        return EventStoreManifest(event_count=event_count, fingerprint=digest.hexdigest())

    def _iter_read(self, *, missing_ok: bool) -> Iterator[StoredEvent]:
        try:
            handle = self.path.open("rb")
        except FileNotFoundError:
            if missing_ok:
                return
            raise

        with handle:
            for line_number, raw_line in enumerate(handle, start=1):
                yield _decode_event(raw_line, line_number)

    def iter_read(self) -> Iterator[StoredEvent]:
        """Stream events; a missing path behaves as an empty legacy store."""

        yield from self._iter_read(missing_ok=True)

    def read(self) -> list[StoredEvent]:
        """Read all events; retained as a convenience and compatibility API."""

        return list(self.iter_read())

    @staticmethod
    def fingerprint(events: Iterable[StoredEvent]) -> str:
        """Hash canonical JSONL bytes in a single streaming pass."""

        digest = hashlib.sha256()
        for event in events:
            digest.update(canonical_jsonl_row(event))
        return digest.hexdigest()

    def manifest(self) -> EventStoreManifest:
        """Validate and describe an existing snapshot.

        Unlike ``read()``, this operation treats a missing snapshot as an
        operational failure, so absence cannot masquerade as a valid empty run.
        """

        digest = hashlib.sha256()
        event_count = 0
        try:
            iterator = self._iter_read(missing_ok=False)
            for event in iterator:
                digest.update(canonical_jsonl_row(event))
                event_count += 1
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"event store snapshot does not exist: {self.path}") from exc
        return EventStoreManifest(event_count=event_count, fingerprint=digest.hexdigest())
