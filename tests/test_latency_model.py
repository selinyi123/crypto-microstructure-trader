from __future__ import annotations

import math

import pytest

from crypto_microstructure_trader import LatencyModel, LatencyStats


def test_empty_latency_summary_is_invalid() -> None:
    assert LatencyModel().summarize([]) == LatencyStats(
        count=0,
        mean_ms=0.0,
        p95_ms=0.0,
        max_ms=0.0,
        valid=False,
        invalid_count=0,
    )


def test_latency_summary_for_one_sample() -> None:
    stats = LatencyModel().summarize([12.34567])

    assert stats == LatencyStats(1, 12.34567, 12.34567, 12.34567, True, 0)


def test_latency_summary_preserves_precision_used_by_guardrails() -> None:
    stats = LatencyModel().summarize([0.00001])

    assert stats.p95_ms == 0.00001
    assert LatencyModel.should_cancel(stats.p95_ms, 0) is True


def test_latency_summary_uses_inclusive_p95() -> None:
    stats = LatencyModel().summarize([10, 20])

    assert stats.p95_ms == 19.5
    assert stats.mean_ms == 15.0
    assert stats.max_ms == 20.0


def test_latency_summary_accepts_generator() -> None:
    stats = LatencyModel().summarize(value for value in [10, 20, 30])

    assert stats.count == 3
    assert stats.invalid_count == 0
    assert stats.valid is True


@pytest.mark.parametrize("invalid", [None, -1, math.nan, math.inf, -math.inf, True, False, "10"])
def test_any_invalid_sample_marks_summary_invalid(invalid: object) -> None:
    stats = LatencyModel().summarize([10, invalid])  # type: ignore[list-item]

    assert stats.count == 1
    assert stats.invalid_count == 1
    assert stats.valid is False
    assert stats.mean_ms == 10.0


def test_all_invalid_samples_are_counted() -> None:
    stats = LatencyModel().summarize([None, -1, math.nan, True])  # type: ignore[list-item]

    assert stats.count == 0
    assert stats.invalid_count == 4
    assert stats.total_count == 4
    assert stats.valid is False


def test_total_count_combines_valid_and_invalid_samples() -> None:
    stats = LatencyModel().summarize([10, 20, None, -1])

    assert stats.count == 2
    assert stats.invalid_count == 2
    assert stats.total_count == 4


def test_large_finite_latency_does_not_overflow_p95() -> None:
    stats = LatencyModel().summarize([1e308, 1e308])

    assert stats.valid is True
    assert stats.mean_ms == 1e308
    assert stats.p95_ms == 1e308
    assert stats.max_ms == 1e308


@pytest.mark.parametrize(
    ("latency", "threshold", "expected"),
    [
        (0, 250, False),
        (250, 250, False),
        (250.0001, 250, True),
        (1e308, 250, True),
        (-1, 250, True),
        (math.nan, 250, True),
        (math.inf, 250, True),
        (-math.inf, 250, True),
        (True, 250, True),
        (False, 250, True),
        (None, 250, True),
        ("20", 250, True),
    ],
)
def test_should_cancel_is_conservative(latency: object, threshold: float, expected: bool) -> None:
    assert LatencyModel.should_cancel(latency, threshold) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize("threshold", [-1, math.nan, math.inf, -math.inf, True, None, "250"])
def test_should_cancel_rejects_invalid_threshold(threshold: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        LatencyModel.should_cancel(10, threshold)  # type: ignore[arg-type]


def test_latency_stats_is_frozen() -> None:
    stats = LatencyModel().summarize([1])

    with pytest.raises((AttributeError, TypeError)):
        stats.count = 2  # type: ignore[misc]
