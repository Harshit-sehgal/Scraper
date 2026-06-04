"""Regression tests for Extraction Accuracy Framework."""

import pytest
from app.benchmark_accuracy import calculate_extraction_accuracy


def test_perfect_extraction_accuracy() -> None:
    golden = [{"name": "British Airways", "price": "£245.50"}, {"name": "Air France", "price": "£199.00"}]

    extracted = [
        {"name": "British Airways", "price": "£245.50", "record_score": 0.9},
        {"name": "Air France", "price": "£199.00", "record_score": 0.85},
    ]

    res = calculate_extraction_accuracy(extracted, golden, domain="travel")

    assert res.precision == 1.0
    assert res.recall == 1.0
    assert res.f1_score == 1.0
    assert res.completeness == 1.0
    assert res.duplicate_rate == 0.0
    assert res.field_accuracy["name"] == 1.0
    assert res.field_accuracy["price"] == 1.0


def test_partial_extraction_accuracy() -> None:
    golden = [{"name": "Acme Corp", "city": "London", "phone": "12345"}, {"name": "Globex", "city": "NY", "phone": "67890"}]

    # Missing phone for Globex, extra field 'country' for Acme
    extracted = [{"name": "Acme Corp", "city": "London", "phone": "12345", "country": "UK"}, {"name": "Globex", "city": "NY"}]

    res = calculate_extraction_accuracy(extracted, golden, domain="directory")

    # Expected fields: 3*2 = 6
    # Extracted fields (valid): 4 + 2 = 6
    # True positives: 3 (Acme) + 2 (Globex) = 5

    assert res.recall == 5 / 6
    assert res.precision == 5 / 6
    assert res.field_accuracy["phone"] == 0.5
    assert res.field_accuracy["name"] == 1.0
    assert res.completeness == 1.0
    assert res.schema_conformity == 5 / 6


def test_duplicate_detection() -> None:
    golden = [{"name": "A"}, {"name": "B"}]
    extracted = [{"name": "A"}, {"name": "A"}, {"name": "B"}]

    res = calculate_extraction_accuracy(extracted, golden)
    assert res.duplicate_rate == pytest.approx(1 / 3, 0.01)
    assert res.completeness == 1.0


def test_extra_records_are_penalized_in_precision() -> None:
    golden = [{"name": "A"}]
    extracted = [
        {"name": "A"},
        {"name": "Noise", "price": "999"},
    ]

    res = calculate_extraction_accuracy(extracted, golden)
    assert res.recall == 1.0
    assert res.precision == pytest.approx(1 / 3)
    assert res.f1_score == pytest.approx(0.5)


def test_extra_schema_fields_are_penalized() -> None:
    golden = [{"name": "A"}]
    extracted = [{"name": "A", "price": "999"}]

    res = calculate_extraction_accuracy(extracted, golden)
    assert res.recall == 1.0
    assert res.precision == pytest.approx(0.5)
    assert res.schema_conformity == pytest.approx(0.5)


def test_hallucination_indicators() -> None:
    golden = [{"name": "A"}]
    extracted = [{"name": "I'm sorry, I cannot determine the name"}]

    res = calculate_extraction_accuracy(extracted, golden)
    assert res.hallucination_rate > 0.0
    assert res.precision == 0.0
