"""Qual 5: Outlier detection and flagging — statistical outlier detection in extracted values."""
from __future__ import annotations

import statistics


def _detect_outliers_iqr(values: list[float]) -> list[int]:
    """Return indices of values that are outliers via IQR method."""
    if len(values) < 4:
        return []
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[3 * n // 4]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [i for i, v in enumerate(values) if v < lower or v > upper]


def _detect_outliers_zscore(values: list[float], threshold: float = 3.0) -> list[int]:
    """Return indices of values that are outliers via z-score method."""
    if len(values) < 4:
        return []
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    if stdev == 0.0:
        return []
    return [i for i, v in enumerate(values) if abs(v - mean) / stdev > threshold]


def _flag_outlier_records(records: list[dict], field: str, method: str = "iqr") -> list[dict]:
    """Annotate records with an ``_outlier`` flag for the given field."""
    values = []
    for r in records:
        try:
            values.append(float(r.get(field, 0)))
        except (TypeError, ValueError):
            values.append(0.0)

    if method == "iqr":
        outlier_indices = set(_detect_outliers_iqr(values))
    else:
        outlier_indices = set(_detect_outliers_zscore(values))

    flagged = []
    for i, r in enumerate(records):
        r = dict(r)
        r["_outlier"] = i in outlier_indices
        flagged.append(r)
    return flagged


class TestOutlierIQR:
    def test_no_outliers_in_uniform_data(self) -> None:
        vals = [10.0] * 10
        assert _detect_outliers_iqr(vals) == []

    def test_detects_obvious_outlier(self) -> None:
        vals = [10, 12, 11, 13, 10, 12, 100, 11, 13, 10]
        outliers = _detect_outliers_iqr(vals)
        assert 6 in outliers

    def test_handles_small_dataset(self) -> None:
        assert _detect_outliers_iqr([1, 2]) == []

    def test_handles_empty(self) -> None:
        assert _detect_outliers_iqr([]) == []


class TestOutlierZScore:
    def test_no_outliers_in_uniform_data(self) -> None:
        vals = [5.0] * 10
        assert _detect_outliers_zscore(vals) == []

    def test_detects_extreme_outlier(self) -> None:
        vals = [5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 1000, 5]
        outliers = _detect_outliers_zscore(vals)
        assert 18 in outliers

    def test_handles_small_dataset(self) -> None:
        assert _detect_outliers_zscore([1, 2]) == []

    def test_handles_single_value(self) -> None:
        assert _detect_outliers_zscore([42]) == []

    def test_lower_threshold_detects_more(self) -> None:
        vals = [1, 2, 1, 2, 1, 2, 10, 1, 2, 1]
        strict = _detect_outliers_zscore(vals, threshold=1.5)
        loose = _detect_outliers_zscore(vals, threshold=3.0)
        assert len(strict) >= len(loose)


class TestOutlierFlaggingRecords:
    def test_flag_outlier_in_price_field(self) -> None:
        records = [
            {"name": "item_a", "price": "10.00"},
            {"name": "item_b", "price": "12.00"},
            {"name": "item_c", "price": "11.00"},
            {"name": "item_d", "price": "999.00"},
            {"name": "item_e", "price": "10.50"},
        ]
        flagged = _flag_outlier_records(records, field="price")
        outlier_names = [r["name"] for r in flagged if r["_outlier"]]
        assert "item_d" in outlier_names

    def test_no_outliers_when_values_close(self) -> None:
        records = [{"price": str(i)} for i in range(50, 60)]
        flagged = _flag_outlier_records(records, field="price")
        assert not any(r["_outlier"] for r in flagged)

    def test_non_numeric_field_handled(self) -> None:
        records = [
            {"name": "a", "rating": "good"},
            {"name": "b", "rating": "better"},
            {"name": "c", "rating": "best"},
        ]
        flagged = _flag_outlier_records(records, field="rating")
        assert all(r["_outlier"] is False for r in flagged)

    def test_missing_field_no_error(self) -> None:
        records = [
            {"name": "a"},
            {"name": "b"},
        ]
        flagged = _flag_outlier_records(records, field="price")
        assert isinstance(flagged, list)

    def test_zscore_method_works(self) -> None:
        records = [{"value": str(10 + i)} for i in range(10)]
        records.append({"value": "1000"})
        flagged = _flag_outlier_records(records, field="value", method="zscore")
        assert flagged[-1]["_outlier"]
