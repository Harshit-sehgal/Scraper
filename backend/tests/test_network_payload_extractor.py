"""Tests for network payload extraction and source arbitration."""

import json
from app.models import SchemaField, FieldType
from app.network_payload_extractor import (
    find_record_arrays,
    score_record_array,
    map_json_records_to_schema,
    extract_from_network_payloads,
    arbitrate_sources,
)


FLIGHT_PAYLOAD = json.dumps({
    "results": [
        {"carrier": "IndiGo", "fare": 4500, "depart": "10:30", "arrive": "12:45"},
        {"carrier": "Vistara", "fare": 6100, "depart": "12:00", "arrive": "14:30"},
        {"carrier": "SpiceJet", "fare": 3800, "depart": "08:15", "arrive": "10:00"},
    ],
    "meta": {"total": 3, "page": 1},
})

NESTED_PAYLOAD = json.dumps({
    "data": {
        "searchResults": {
            "flights": [
                {"airlineName": "Delta", "price": {"total": "$500"}, "stops": 0},
                {"airlineName": "United", "price": {"total": "$620"}, "stops": 1},
            ]
        }
    }
})

MIXED_PAYLOAD = json.dumps({
    "tags": ["cheap", "direct"],
    "filters": [{"name": "stops", "values": [0, 1, 2]}],
    "items": [
        {"name": "Product A", "price": "$10"},
        {"name": "Product B", "price": "$20"},
        {"name": "Product C", "price": "$30"},
    ]
})


class TestFindRecordArrays:
    def test_finds_results_array(self):
        payload = json.loads(FLIGHT_PAYLOAD)
        candidates = find_record_arrays(payload)
        assert len(candidates) > 0
        best = candidates[0]
        assert best.path in ("results", "$.results")
        assert len(best.records) == 3

    def test_finds_nested_arrays(self):
        payload = json.loads(NESTED_PAYLOAD)
        candidates = find_record_arrays(payload)
        assert len(candidates) > 0
        paths = [c.path for c in candidates]
        assert any("flights" in p for p in paths)

    def test_ignores_non_object_arrays(self):
        payload = json.loads(MIXED_PAYLOAD)
        candidates = find_record_arrays(payload)
        paths = [c.path for c in candidates]
        assert not any("tags" in p for p in paths)  # tags is string array, not objects

    def test_finds_items_in_mixed_payload(self):
        payload = json.loads(MIXED_PAYLOAD)
        candidates = find_record_arrays(payload)
        paths = [c.path for c in candidates]
        assert any("items" in p for p in paths)
        items = next(c.records for c in candidates if "items" in c.path)
        assert len(items) == 3


class TestScoreRecordArray:
    def test_flight_schema_scores_high(self):
        payload = json.loads(FLIGHT_PAYLOAD)
        candidates = find_record_arrays(payload)
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        score = score_record_array(candidates[0], schema)
        assert score > 30, f"Score too low: {score}"

    def test_empty_schema_scores_zero(self):
        payload = json.loads(FLIGHT_PAYLOAD)
        candidates = find_record_arrays(payload)
        score = score_record_array(candidates[0], [])
        assert score == 0.0

    def test_irrelevant_schema_scores_low(self):
        payload = json.loads(FLIGHT_PAYLOAD)
        candidates = find_record_arrays(payload)
        schema = [
            SchemaField(name="color", field_type=FieldType.STRING, required=False),
            SchemaField(name="weight", field_type=FieldType.STRING, required=False),
        ]
        score = score_record_array(candidates[0], schema)
        assert score < 35, f"Score should be relatively low for irrelevant schema: {score}"


class TestMapJsonRecords:
    def test_maps_carrier_to_airline(self):
        payload = json.loads(FLIGHT_PAYLOAD)
        records = payload["results"]
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        mapped, field_map = map_json_records_to_schema(records, schema)
        assert len(mapped) == 3
        assert mapped[0].get("airline") == "IndiGo"
        assert mapped[0].get("price") == 4500

    def test_field_map_has_provenance(self):
        payload = json.loads(FLIGHT_PAYLOAD)
        records = payload["results"]
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
        ]
        _, field_map = map_json_records_to_schema(records, schema)
        assert "airline" in field_map
        assert field_map["airline"].source == "network_payload"
        assert field_map["airline"].confidence > 0.5

    def test_nested_flight_payload_maps(self):
        payload = json.loads(NESTED_PAYLOAD)
        flights = payload["data"]["searchResults"]["flights"]
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        mapped, _ = map_json_records_to_schema(flights, schema)
        assert len(mapped) == 2
        assert mapped[0].get("airline") == "Delta"


class TestExtractFromNetworkPayloads:
    def test_extracts_from_flight_payload(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([FLIGHT_PAYLOAD], schema)
        assert result is not None
        assert result.record_count == 3
        assert result.score > 30

    def test_returns_none_for_empty_payloads(self):
        result = extract_from_network_payloads([], [
            SchemaField(name="x", field_type=FieldType.STRING, required=False),
        ])
        assert result is None

    def test_returns_none_for_low_scoring_payload(self):
        result = extract_from_network_payloads(
            [json.dumps({"not": "records", "here": 1})],
            [SchemaField(name="airline", field_type=FieldType.STRING, required=False)],
        )
        assert result is None


class TestSourceArbitration:
    def test_network_wins_when_dom_empty(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        net_result = extract_from_network_payloads([FLIGHT_PAYLOAD], schema)
        records, source, _ = arbitrate_sources([], 0, net_result, schema)
        assert source == net_result.source
        assert len(records) == 3

    def test_dom_wins_when_network_weak(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
        ]
        dom_records = [
            {"airline": "TestAir", "price": "$100"},
            {"airline": "DemoJet", "price": "$200"},
        ]
        net_result = extract_from_network_payloads(
            [json.dumps({"results": [{"x": 1}]})], schema,
        )
        records, source, _ = arbitrate_sources(dom_records, 80, net_result, schema)
        assert source == "dom"
        assert records == dom_records

    def test_secrets_not_in_field_map(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
        ]
        result = extract_from_network_payloads([FLIGHT_PAYLOAD], schema)
        assert result is not None
        for fm in result.field_map.values():
            assert "token" not in fm.mapped_from.lower()
            assert "cookie" not in fm.mapped_from.lower()
