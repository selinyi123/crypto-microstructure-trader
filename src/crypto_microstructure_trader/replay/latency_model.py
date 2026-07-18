"""Conservative latency summaries and fail-closed cancellation decisions."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Real


@dataclass(frozen=True)
class LatencyStats:
    count: int
    mean_ms: float
    p95_ms: float
    max_ms: float
    valid: bool
    invalid_count: int = 0

    @property
    def total_count(self) -> int:
        return self.count + self.invalid_count


def _finite_non_negative(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _overflow_safe_mean(values: list[float], maximum: float) -> float:
    if maximum == 0.0:
        return 0.0
    normalized_mean = math.fsum(value / maximum for value in values) / len(values)
    # The mathematical mean cannot exceed maximum.  Clamp the tiny rounding
    # overshoot that could otherwise overflow when maximum is near DBL_MAX.
    return maximum * min(1.0, max(0.0, normalized_mean))


def _inclusive_p95(sorted_values: list[float]) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * 0.95
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    fraction = position - lower_index
    # This form cannot create the oversized intermediates used by weighted-sum
    # percentile implementations (for example, 19 * 1e308).
    interpolated = lower + (upper - lower) * fraction
    return min(upper, max(lower, interpolated))


class LatencyModel:
    def summarize(self, samples_ms: Iterable[object]) -> LatencyStats:
        cleaned: list[float] = []
        invalid_count = 0
        for sample in samples_ms:
            number = _finite_non_negative(sample)
            if number is None:
                invalid_count += 1
            else:
                cleaned.append(number)

        if not cleaned:
            return LatencyStats(
                count=0,
                mean_ms=0.0,
                p95_ms=0.0,
                max_ms=0.0,
                valid=False,
                invalid_count=invalid_count,
            )

        cleaned.sort()
        maximum = cleaned[-1]
        mean_ms = _overflow_safe_mean(cleaned, maximum)
        p95_ms = _inclusive_p95(cleaned)
        derived_are_finite = math.isfinite(mean_ms) and math.isfinite(p95_ms)
        valid = invalid_count == 0 and derived_are_finite
        return LatencyStats(
            count=len(cleaned),
            # Preserve decision precision.  Rounding here could make a small
            # positive p95 equal zero (or move it below a nearby threshold),
            # causing callers such as the CLI guard to fail open.
            mean_ms=mean_ms if math.isfinite(mean_ms) else 0.0,
            p95_ms=p95_ms if math.isfinite(p95_ms) else 0.0,
            max_ms=maximum,
            valid=valid,
            invalid_count=invalid_count,
        )

    @staticmethod
    def should_cancel(expected_latency_ms: object, threshold_ms: object = 250) -> bool:
        """Return whether execution should be cancelled.

        Invalid expected latency fails closed and therefore cancels.  An invalid
        configured threshold is a programmer/configuration error and raises.
        """

        threshold = _finite_non_negative(threshold_ms)
        if threshold is None:
            if isinstance(threshold_ms, bool) or not isinstance(threshold_ms, Real):
                raise TypeError("threshold_ms must be a finite non-negative number")
            raise ValueError("threshold_ms must be a finite non-negative number")

        expected = _finite_non_negative(expected_latency_ms)
        if expected is None:
            return True
        return expected > threshold
