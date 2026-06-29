from __future__ import annotations

import random
import statistics


def _gaussian_delay(mean_ms: float, stddev_ms: float, min_ms: float = 0.0) -> float:
    """Generate a Gaussian-distributed timing delay."""
    delay = random.gauss(mean_ms, stddev_ms)
    return max(min_ms, delay)


def _bounded_jitter(base_ms: float, jitter_fraction: float = 0.25) -> float:
    """Apply bounded jitter to a base delay."""
    jitter = random.uniform(-jitter_fraction, jitter_fraction)
    return max(0, base_ms * (1.0 + jitter))


class TestGaussianTiming:
    """Anti 11: Human-like timing with Gaussian distribution."""

    def test_delay_is_non_negative(self) -> None:
        for _ in range(100):
            assert _gaussian_delay(100, 20) >= 0

    def test_delay_minimum_applied(self) -> None:
        for _ in range(100):
            assert _gaussian_delay(10, 50, min_ms=5) >= 5

    def test_mean_approximated_over_samples(self) -> None:
        samples = [_gaussian_delay(200, 40) for _ in range(2000)]
        assert 180 < statistics.mean(samples) < 220

    def test_stddev_approximated_over_samples(self) -> None:
        samples = [_gaussian_delay(300, 50) for _ in range(2000)]
        assert 30 < statistics.stdev(samples) < 75

    def test_gaussian_with_zero_stddev(self) -> None:
        samples = [_gaussian_delay(100, 0) for _ in range(10)]
        assert all(s == 100 for s in samples)

    def test_different_means_give_different_results(self) -> None:
        low = [_gaussian_delay(50, 5) for _ in range(500)]
        high = [_gaussian_delay(500, 5) for _ in range(500)]
        assert statistics.mean(high) > statistics.mean(low)

    def test_different_stddevs_give_different_spread(self) -> None:
        narrow = [_gaussian_delay(200, 5) for _ in range(500)]
        wide = [_gaussian_delay(200, 50) for _ in range(500)]
        assert statistics.stdev(wide) > statistics.stdev(narrow)

    def test_outliers_clamped_by_minimum(self) -> None:
        samples = [_gaussian_delay(5, 100, min_ms=0) for _ in range(500)]
        assert all(s >= 0 for s in samples)


class TestBoundedJitter:
    """Bounded jitter used in retry policies."""

    def test_jitter_within_bounds(self) -> None:
        base = 100
        for _ in range(200):
            delay = _bounded_jitter(base, 0.25)
            assert 73 <= delay <= 127, f"Jitter out of bounds: {delay}"

    def test_jitter_zero_base_returns_zero(self) -> None:
        assert _bounded_jitter(0) == 0

    def test_jitter_negative_base_clamped(self) -> None:
        assert _bounded_jitter(-50, 0.25) >= 0

    def test_jitter_spread(self) -> None:
        delays = {_bounded_jitter(100, 0.25) for _ in range(100)}
        assert len(delays) >= 5

    def test_jitter_max_fraction(self) -> None:
        for _ in range(100):
            delay = _bounded_jitter(100, 0.5)
            assert 48 <= delay <= 152

    def test_no_lockstep_pattern(self) -> None:
        d1 = [_bounded_jitter(100, 0.25) for _ in range(100)]
        d2 = [_bounded_jitter(100, 0.25) for _ in range(100)]
        assert d1 != d2
