"""Qual 5: Outlier detection and flagging — statistical outlier detection in extracted values.

Regression coverage for the outlier detection module in ``app.utils.quality``.
Covers IQR + z-score methods, non-numeric field handling, missing values,
small datasets, threshold sensitivity, and the public ``flag_outlier_records``
contract.
"""
from __future__ import annotations

from typing import Any

from app.utils.quality import (
    _detect_outliers_iqr,
    _detect_outliers_zscore,
    flag_outlier_records,
)


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
        vals = [
            5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 1000, 5,
        ]
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


class TestFlagOutlierRecords:
    def test_flag_outlier_in_price_field(self) -> None:
        records = [
            {"name": "item_a", "price": 10.00},
            {"name": "item_b", "price": 12.00},
            {"name": "item_c", "price": 11.00},
            {"name": "item_d", "price": 999.00},
            {"name": "item_e", "price": 10.50},
        ]
        flagged = flag_outlier_records(records, field="price")
        outlier_names = [r["name"] for r in flagged if r["_outlier"]]
        assert "item_d" in outlier_names

    def test_no_outliers_when_values_close(self) -> None:
        records = [{"price": float(i)} for i in range(50, 60)]
        flagged = flag_outlier_records(records, field="price")
        assert not any(r["_outlier"] for r in flagged)

    def test_missing_field_skips_record_without_flagging(self) -> None:
        records: list[dict[str, Any]] = [
            {"name": "a", "price": 10.0},
            {"name": "b"},  # missing price
            {"name": "c", "price": 11.0},
        ]
        flagged = flag_outlier_records(records, field="price")
        # records without the field are retained but not flagged
        assert flagged[1]["name"] == "b"
        assert flagged[1]["_outlier"] is False

    def test_non_numeric_value_skipped_without_breaking(self) -> None:
        records: list[dict[str, Any]] = [
            {"name": "a", "price": 10.0},
            {"name": "b", "price": "not-a-number"},
            {"name": "c", "price": 12.0},
        ]
        flagged = flag_outlier_records(records, field="price")
        assert len(flagged) == len(records)
        # non-numeric value is not flagged even if `0.0` would be an outlier
        assert flagged[1]["_outlier"] is False

    def test_zscore_method_works(self) -> None:
        records = [{"value": float(10 + i)} for i in range(10)]
        records.append({"value": 1000.0})
        flagged = flag_outlier_records(records, field="value", method="zscore")
        assert flagged[-1]["_outlier"] is True

    def test_unknown_method_falls_back_to_iqr(self) -> None:
        records = [
            {"x": 10.0},
            {"x": 11.0},
            {"x": 12.0},
            {"x": 10.5},
            {"x": 11.5},
            {"x": 1000.0},
        ]
        # unknown method → IQR fallback, no exception
        flagged = flag_outlier_records(records, field="x", method="bogus")
        assert isinstance(flagged, list)
        assert len(flagged) == len(records)

    def test_returns_copy_not_mutation(self) -> None:
        records = [{"x": 10.0}, {"x": 11.0}, {"x": 1000.0}]
        originals = [dict(r) for r in records]
        flag_outlier_records(records, field="x")
        # original records dicts untouched
        assert all("_outlier" not in r for r in originals)
        # originals list not mutated
        assert records == originals

    def test_preserves_all_existing_fields(self) -> None:
        records = [
            {"name": "a", "price": 10.0, "category": "x"},
            {"name": "b", "price": 11.0, "category": "y"},
        ]
        flagged = flag_outlier_records(records, field="price")
        for original, annotated in zip(records, flagged):
            for key, value in original.items():
                assert annotated[key] == value
            assert "_outlier" in annotated

    def test_empty_records_returns_empty(self) -> None:
        assert flag_outlier_records([], field="price") == []

    def test_record_count_preserved(self) -> None:
        records = [{"price": float(i)} for i in range(20)]
        flagged = flag_outlier_records(records, field="price")
        assert len(flagged) == 20
