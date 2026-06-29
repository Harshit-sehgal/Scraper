from __future__ import annotations

import math
import random


def _generate_bezier_curve(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    num_steps: int = 30,
) -> list[tuple[float, float]]:
    """Generate mouse track points using quadratic Bezier curve."""
    cp_x = start_x + (end_x - start_x) * (0.3 + random.random() * 0.4)
    cp_y = start_y + (end_y - start_y) * (0.3 + random.random() * 0.4)
    points: list[tuple[float, float]] = []
    for i in range(num_steps + 1):
        t = i / num_steps
        u = 1 - t
        x = u * u * start_x + 2 * u * t * cp_x + t * t * end_x
        y = u * u * start_y + 2 * u * t * cp_y + t * t * end_y
        points.append((round(x, 1), round(y, 1)))
    return points


def _bezier_path_length(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        total += math.sqrt(dx * dx + dy * dy)
    return total


class TestBezierCurveGeneration:
    """Anti 10: Mouse movement simulation via Bezier curves."""

    def test_curve_starts_at_start_point(self) -> None:
        points = _generate_bezier_curve(100, 200, 500, 600)
        assert points[0] == (100.0, 200.0)

    def test_curve_ends_at_end_point(self) -> None:
        points = _generate_bezier_curve(100, 200, 500, 600)
        assert points[-1] == (500.0, 600.0)

    def test_curve_has_expected_number_of_steps(self) -> None:
        points = _generate_bezier_curve(100, 200, 500, 600, num_steps=30)
        assert len(points) == 31

    def test_curve_points_are_monotonic(self) -> None:
        points = _generate_bezier_curve(0, 0, 1000, 1000)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        assert all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))
        assert all(ys[i] <= ys[i + 1] for i in range(len(ys) - 1))

    def test_curve_path_length_greater_than_straight_line(self) -> None:
        points = _generate_bezier_curve(0, 0, 100, 100, num_steps=50)
        straight = math.sqrt(100**2 + 100**2)
        path_len = _bezier_path_length(points)
        assert path_len >= straight, "Path must be at least as long as straight line"

    def test_control_point_varies(self) -> None:
        results: set[float] = set()
        for _ in range(20):
            points = _generate_bezier_curve(0, 0, 100, 100, num_steps=10)
            results.add(points[3][0])
        assert len(results) > 1, "Bezier curves should vary due to random control points"

    def test_different_start_end_produces_different_path(self) -> None:
        path_a = _generate_bezier_curve(0, 0, 500, 500, num_steps=20)
        path_b = _generate_bezier_curve(100, 200, 300, 400, num_steps=20)
        assert path_a != path_b

    def test_large_movement_generates_more_distance(self) -> None:
        small_path = _generate_bezier_curve(0, 0, 50, 50, num_steps=20)
        large_path = _generate_bezier_curve(0, 0, 500, 500, num_steps=20)
        assert _bezier_path_length(large_path) > _bezier_path_length(small_path)

    def test_zero_distance_movement(self) -> None:
        points = _generate_bezier_curve(100, 100, 100, 100, num_steps=10)
        assert all(p[0] == 100 for p in points)
        assert all(p[1] == 100 for p in points)

    def test_custom_step_count(self) -> None:
        points = _generate_bezier_curve(0, 0, 100, 100, num_steps=5)
        assert len(points) == 6

    def test_intermediate_points_are_between_start_and_end(self) -> None:
        points = _generate_bezier_curve(0, 0, 200, 300, num_steps=20)
        for x, y in points:
            assert 0 <= x <= 200
            assert 0 <= y <= 300

    def test_seed_stability(self) -> None:
        random.seed(42)
        path_a = _generate_bezier_curve(0, 0, 100, 100, num_steps=10)
        random.seed(42)
        path_b = _generate_bezier_curve(0, 0, 100, 100, num_steps=10)
        assert path_a == path_b
