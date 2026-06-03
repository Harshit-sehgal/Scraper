"""Tests: extract full selector map, then align to user schema."""

from typing import Any

from app.data_utils import align_extracted_keys_to_schema
from app.models import FieldType, SchemaField
from app.selector_engine import apply_selectors, extract_raw_from_selectors

SAMPLE_HTML = """
<html><body>
<div class="card">
  <span class="airline-name">Acme Air</span>
  <span class="from-code">AAA</span>
  <span class="to-code">BBB</span>
  <span class="dep-date">01-01-2026</span>
  <span class="ret-date">02-01-2026</span>
  <span class="cost">£99</span>
  <span class="stops">Direct</span>
</div>
<div class="card">
  <span class="airline-name">Beta Jet</span>
  <span class="from-code">AAA</span>
  <span class="to-code">BBB</span>
  <span class="dep-date">01-01-2026</span>
  <span class="ret-date">02-01-2026</span>
  <span class="cost">£120</span>
  <span class="stops">1 Stop</span>
</div>
</body></html>
"""

SELECTORS = {
    "item_container": ".card",
    "fields": {
        "airline": ".airline-name",
        "origin": ".from-code",
        "destination": ".to-code",
        "date": ".dep-date",
        "return_date": ".ret-date",
        "price": ".cost",
        "stops": ".stops",
    },
}

USER_SCHEMA = [
    SchemaField(name="airlines_name", field_type=FieldType.STRING, description="Airline name", required=False),
    SchemaField(name="origin_airport", field_type=FieldType.STRING, description="Origin airport", required=False),
    SchemaField(name="destination_airport", field_type=FieldType.STRING, description="Destination", required=False),
    SchemaField(name="prices", field_type=FieldType.CURRENCY, description="Price", required=False),
    SchemaField(name="departure_date", field_type=FieldType.DATE, description="Departure date", required=False),
    SchemaField(name="arrival_date", field_type=FieldType.DATE, description="Arrival date", required=False),
]


class TestExtractAllThenAlign:
    def test_extract_raw_includes_all_selector_keys(self) -> None:
        raw = extract_raw_from_selectors(SAMPLE_HTML, SELECTORS)
        assert len(raw) == 2
        fields = SELECTORS["fields"]
        assert isinstance(fields, dict)
        assert set(raw[0].keys()) == set(fields.keys())

    def test_align_maps_to_user_schema(self) -> None:
        raw = extract_raw_from_selectors(SAMPLE_HTML, SELECTORS)
        aligned: list[dict[str, Any]] = align_extracted_keys_to_schema(raw, USER_SCHEMA)
        assert aligned[0]["airlines_name"] == "Acme Air"
        assert aligned[0]["origin_airport"] == "AAA"
        assert aligned[0]["prices"] == "£99"
        assert aligned[0]["departure_date"] == "01-01-2026"
        assert aligned[0]["arrival_date"] == "02-01-2026"
        assert "stops" not in aligned[0]

    def test_apply_selectors_end_to_end(self) -> None:
        results: Any = apply_selectors(SAMPLE_HTML, SELECTORS, USER_SCHEMA)
        assert len(results) == 2
        assert results[0]["airlines_name"] == "Acme Air"
        assert results[0]["arrival_date"] == "02-01-2026"
