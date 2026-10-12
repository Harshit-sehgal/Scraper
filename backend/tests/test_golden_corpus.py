"""Unit tests for golden-corpus metrics (E3.2/E3.3).

These run in the default CI suite (no network, no golden_dataset
marker): they pin field-level F1, diagnosis cards, and the trend /
>5pt-drop alert logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.golden_corpus import (
    DROP_ALERT_POINTS,
    field_level_f1,
    read_trend,
    record_trend,
    write_diagnosis_card,
)

BOOKS = [
    {"title": "A", "price": "£10.00", "rating": "star-rating One"},
    {"title": "B", "price": "£12.00", "rating": "star-rating Two"},
]
EXPECTED = [
    {"title": "A", "price": "£10.00", "rating": "star-rating One"},
    {"title": "B", "price": "£12.00", "rating": "star-rating Two"},
]


def test_field_level_f1_perfect_match() -> None:
    result = field_level_f1(BOOKS, EXPECTED, ["title", "price"])
    assert result["title"]["f1"] == 1.0
    assert result["price"]["f1"] == 1.0
    assert result["title"]["true_positives"] == 2


def test_field_level_f1_missing_field() -> None:
    extracted = [
        {"title": "A", "price": "£10.00"},
        {"title": "B"},  # price missing
    ]
    result = field_level_f1(extracted, EXPECTED, ["price"])
    assert result["price"]["true_positives"] == 1
    assert result["price"]["false_negatives"] == 1
    assert result["price"]["recall"] == 0.5


def test_field_level_f1_pairs_values_by_record_identity() -> None:
    """Equal value sets in different rows must not score as a perfect match."""
    extracted = [
        {"title": "A", "price": "£12.00"},
        {"title": "B", "price": "£10.00"},
    ]
    expected = [
        {"title": "A", "price": "£10.00"},
        {"title": "B", "price": "£12.00"},
    ]
    result = field_level_f1(extracted, expected, ["title", "price"])
    assert result["price"]["f1"] == 0.0


def test_field_level_f1_no_data() -> None:
    result = field_level_f1([], [], ["title"])
    assert result["title"]["f1"] == 0.0
    assert result["title"]["precision"] == 0.0


def test_write_diagnosis_card_records_failure_taxonomy(tmp_path: Path) -> None:
    card_path = write_diagnosis_card(
        site_id="books_toscrape",
        url="https://books.toscrape.com/",
        f1_result={"f1": 0.6, "precision": 0.6, "recall": 0.6},
        fields=["title", "price"],
        extracted=[{"title": "A"}],
        expected=[{"title": "A"}, {"title": "B"}],
        diagnosis_dir=tmp_path,
    )
    card: dict[str, Any] = __import__("json").loads(card_path.read_text())
    assert card["site_id"] == "books_toscrape"
    assert card["record_f1"] == 0.6
    assert "failure_category" in card
    assert "failure_confidence" in card
    assert "recovery_strategy" in card
    assert "field_level_f1" in card
    assert card["field_level_f1"]["title"]["true_positives"] == 1


def test_record_trend_first_observation(tmp_path: Path) -> None:
    trend_path = tmp_path / "trend.jsonl"
    info = record_trend("books_toscrape", 0.95, path=trend_path)
    assert info["previous_f1"] is None
    assert info["drop"] == 0.0
    entries = read_trend(trend_path)
    assert len(entries) == 1
    assert entries[0]["site_id"] == "books_toscrape"
    assert entries[0]["f1"] == 0.95


def test_record_trend_alert_on_drop(tmp_path: Path) -> None:
    trend_path = tmp_path / "trend.jsonl"
    record_trend("books_toscrape", 0.95, path=trend_path)
    info = record_trend("books_toscrape", 0.88, path=trend_path)
    assert info["previous_f1"] == 0.95
    assert info["drop"] == pytest.approx(0.07)
    assert info["drop"] > DROP_ALERT_POINTS / 100


def test_record_trend_no_alert_on_small_drop(tmp_path: Path) -> None:
    trend_path = tmp_path / "trend.jsonl"
    record_trend("books_toscrape", 0.95, path=trend_path)
    info = record_trend("books_toscrape", 0.94, path=trend_path)
    assert info["drop"] == pytest.approx(0.01)
    assert info["drop"] <= DROP_ALERT_POINTS / 100


def test_record_trend_prunes_old_entries(tmp_path: Path) -> None:
    trend_path = tmp_path / "trend.jsonl"
    for i in range(15):
        record_trend("books_toscrape", 0.9 + i * 0.001, path=trend_path)
    entries = read_trend(trend_path)
    assert len(entries) == 10  # TREND_KEEP_PER_SITE


def test_record_trend_tolerant_of_corrupt_lines(tmp_path: Path) -> None:
    trend_path = tmp_path / "trend.jsonl"
    trend_path.write_text("not json\n{also not}\n")
    assert read_trend(trend_path) == []
    record_trend("quotes_toscrape", 1.0, path=trend_path)
    entries = read_trend(trend_path)
    assert len(entries) == 1
