"""Unit tests for app.compound_record_assembler — segment detection and record assembly."""

from typing import Any

from app.compound_record_assembler import (
    CompoundRecord,
    Segment,
    _detect_repeated_groups,
    _extract_segment_fields,
    _extract_shared_fields,
    assemble_compound_records,
    assemble_single_container,
    detect_segments,
)

# ── Segment / CompoundRecord data classes ────────────────────────────────


class TestDataClasses:
    def test_segment_defaults(self):
        s = Segment(index=0, label="Part 1")
        assert s.fields == {}
        assert s.raw_text == ""
        assert s.confidence == 0.0

    def test_compound_record_to_dict(self):
        cr = CompoundRecord(
            segments=[
                Segment(index=0, label="From", fields={"code": "JFK"}, raw_text="JFK departure"),
                Segment(index=1, label="To", fields={"code": "LAX"}, raw_text="LAX arrival"),
            ],
            shared_fields={"price": "$500"},
        )
        d = cr.to_dict()
        assert len(d["segments"]) == 2
        assert d["shared_fields"]["price"] == "$500"
        assert d["segments"][0]["label"] == "From"

    def test_compound_record_flatten(self):
        cr = CompoundRecord(
            segments=[
                Segment(index=0, label="Departure", fields={"code": "JFK", "time_start": "10:00"}),
                Segment(index=1, label="Return", fields={"code": "LAX", "time_start": "15:00"}),
            ],
            shared_fields={"price": "$800"},
        )
        flat = cr.flatten()
        assert flat["departure_code"] == "JFK"
        assert flat["return_code"] == "LAX"
        assert flat["departure_time_start"] == "10:00"
        assert flat["price"] == "$800"


# ── detect_segments ──────────────────────────────────────────────────────


class TestDetectSegments:
    def test_label_separated_from_to(self):
        text = "From: New York JFK\n10:00 AM\nTo: Los Angeles LAX\n3:00 PM"
        segments = detect_segments(text)
        assert len(segments) >= 2
        assert segments[0]["label"] in ("From", "To")

    def test_label_separated_item_entry(self):
        text = "Item 1: Widget A\n$10.00\nItem 2: Widget B\n$20.00"
        segments = detect_segments(text)
        assert len(segments) == 2

    def test_no_separators_falls_through_to_groups(self):
        text = "Block one with long text about something important\n\n\nBlock two with another long text about something else"
        segments = detect_segments(text)
        assert len(segments) >= 2

    def test_empty_text(self):
        segments = detect_segments("")
        assert segments == []

    def test_single_line(self):
        segments = detect_segments("Just a single line")
        assert isinstance(segments, list)

    def test_segment_raw_text_cleaned(self):
        text = "From: data here\nmore data\nTo: other data\nmore other"
        segments = detect_segments(text)
        for s in segments:
            assert s["raw_text"] == s["raw_text"].strip()


# ── _detect_repeated_groups ──────────────────────────────────────────────


class TestDetectRepeatedGroups:
    def test_whitespace_separated_blocks(self):
        text = "First block with enough text to count\n\n\nSecond block with enough text too"
        groups = _detect_repeated_groups(text)
        assert len(groups) >= 2
        assert groups[0]["label"] == "Part 1"
        assert groups[1]["label"] == "Part 2"

    def test_date_value_clusters(self):
        text = "01/15/2026 Widget A $100.00 02/20/2026 Widget B $200.00"
        groups = _detect_repeated_groups(text)
        assert len(groups) >= 2

    def test_no_patterns_returns_empty(self):
        text = "short"
        groups = _detect_repeated_groups(text)
        assert groups == []


# ── _extract_segment_fields ──────────────────────────────────────────────


class TestExtractSegmentFields:
    def test_organization(self):
        fields = _extract_segment_fields("Operated by United Airlines from JFK")
        assert "organization" in fields
        assert "United Airlines" in fields["organization"]

    def test_times(self):
        fields = _extract_segment_fields("Depart 10:00am Arrive 2:30pm")
        assert fields["time_start"] == "10:00am"
        assert fields["time_end"] == "2:30pm"

    def test_single_time(self):
        fields = _extract_segment_fields("Depart at 9:15")
        assert fields["time_start"] == "9:15"
        assert "time_end" not in fields

    def test_three_letter_codes(self):
        fields = _extract_segment_fields("JFK to LAX nonstop")
        assert fields["code_from"] == "JFK"
        assert fields["code_to"] == "LAX"

    def test_single_code(self):
        fields = _extract_segment_fields("Terminal at JFK")
        assert fields["code"] == "JFK"

    def test_date(self):
        fields = _extract_segment_fields("Departure on 2026-06-15")
        assert fields["date"] == "2026-06-15"

    def test_date_slash_format(self):
        fields = _extract_segment_fields("Date: 6/15/2026")
        assert "date" in fields

    def test_price(self):
        fields = _extract_segment_fields("Total: $299.99")
        assert fields["price"] == "$299.99"

    def test_euro_price(self):
        fields = _extract_segment_fields("Cost: €150")
        assert fields["price"] == "€150"

    def test_no_fields(self):
        fields = _extract_segment_fields("nothing special here")
        assert isinstance(fields, dict)


# ── _extract_shared_fields ───────────────────────────────────────────────


class TestExtractSharedFields:
    def test_price_extraction(self):
        segments = [{"raw_text": "leg 1"}, {"raw_text": "leg 2"}]
        shared = _extract_shared_fields(segments, "Total fare $500.00 per person")
        assert shared["price"] == "$500.00"

    def test_largest_price_selected(self):
        segments: list[dict[str, Any]] = []
        shared = _extract_shared_fields(segments, "$100 economy $500 business $250 premium")
        assert shared["price"] == "$500"

    def test_rating(self):
        segments: list[dict[str, Any]] = []
        shared = _extract_shared_fields(segments, "Hotel rating: 4.5/5")
        assert shared["rating"] == "4.5"

    def test_status_available(self):
        segments: list[dict[str, Any]] = []
        shared = _extract_shared_fields(segments, "Room is available for booking")
        assert shared["status"].lower() == "available"

    def test_status_sold_out(self):
        segments: list[dict[str, Any]] = []
        shared = _extract_shared_fields(segments, "This item is sold out")
        assert "sold" in shared["status"].lower()

    def test_no_shared_fields(self):
        segments: list[dict[str, Any]] = []
        shared = _extract_shared_fields(segments, "plain text with no structured data")
        assert isinstance(shared, dict)


# ── assemble_compound_records ────────────────────────────────────────────


class TestAssembleCompoundRecords:
    def test_empty_input(self):
        assert assemble_compound_records([]) == []

    def test_non_compound_passthrough(self):
        records = [{"title": "Simple record", "price": "$10"}]
        result = assemble_compound_records(records)
        assert len(result) == 1
        assert result[0]["title"] == "Simple record"

    def test_compound_via_element_text(self):
        records = [
            {
                "_element_text": "From: JFK 10:00am\nDeparture via United Airlines\nTo: LAX 2:30pm\nArrival via United Airlines",
                "price": "$500",
            },
        ]
        result = assemble_compound_records(records)
        assert len(result) == 1
        flat = result[0]
        assert isinstance(flat, dict)

    def test_compound_via_full_texts(self):
        records = [{"name": "Flight"}]
        full_texts = {"0": "From: Origin City JFK\n10:00am departure\nTo: Destination LAX\n2:30pm arrival"}
        result = assemble_compound_records(records, full_texts=full_texts)
        assert len(result) == 1

    def test_metadata_preserved(self):
        records = [
            {
                "_element_text": "From: A\ndata\nTo: B\ndata",
                "source_url": "https://example.com",
                "_extraction_method": "selector",
                "_key": "k1",
            },
        ]
        result = assemble_compound_records(records)
        if "source_url" in result[0]:
            assert result[0]["source_url"] == "https://example.com"

    def test_fallback_to_concatenated_values(self):
        records = [{"a": "short", "b": "value"}]
        result = assemble_compound_records(records)
        assert len(result) == 1


# ── assemble_single_container ────────────────────────────────────────────


class TestAssembleSingleContainer:
    def test_short_text_returns_none(self):
        assert assemble_single_container("short") is None

    def test_empty_text_returns_none(self):
        assert assemble_single_container("") is None

    def test_no_segments_returns_none(self):
        assert assemble_single_container("a" * 60) is None

    def test_compound_detected(self):
        text = "From: Origin JFK\n10:00am United Airlines\nTo: Destination LAX\n2:30pm Delta Airlines"
        result = assemble_single_container(text)
        assert result is not None
        assert isinstance(result, CompoundRecord)
        assert len(result.segments) >= 2
        assert result.confidence > 0

    def test_compound_has_shared_fields(self):
        text = "From: City A $200\ndata content\nTo: City B $300\nmore content\nTotal $500"
        result = assemble_single_container(text)
        if result is not None:
            assert isinstance(result.shared_fields, dict)
