"""Tests for network payload extraction and source arbitration."""

import json
import pytest
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

    def test_weak_dom_strong_network_chooses_network(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        # Strong network data: has high field coverage and high score
        net_result = extract_from_network_payloads([FLIGHT_PAYLOAD], schema)

        # Weak DOM data: low coverage (e.g. missing prices, only 1 record, low score)
        dom_records = [{"airline": "PoorDOM"}]

        records, source, _ = arbitrate_sources(dom_records, 15.0, net_result, schema)
        assert source == net_result.source
        assert len(records) == 3

    def test_strong_dom_weak_network_chooses_dom(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        # Weak network data
        net_result = extract_from_network_payloads(
            [json.dumps({"results": [{"carrier": "Indigo"}]})], schema,
        )

        # Strong DOM data
        dom_records = [
            {"airline": "IndiGo", "price": 4500},
            {"airline": "Vistara", "price": 6100},
        ]

        records, source, _ = arbitrate_sources(dom_records, 95.0, net_result, schema)
        assert source == "dom"
        assert len(records) == 2

    def test_both_weak_arbitration_flow(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        # Both DOM and network have very low quality data
        net_result = extract_from_network_payloads(
            [json.dumps({"results": [{"x": 1, "y": 2}]})], schema,
        )
        dom_records = [{"airline": "BadDOM"}]

        records, source, _ = arbitrate_sources(dom_records, 5.0, net_result, schema)
        # Should fallback gracefully to DOM
        assert source == "dom"
        assert records == dom_records

    def test_graphql_shape_unwrapping(self):
        graphql_payload = json.dumps({
            "data": {
                "flights": {
                    "edges": [
                        {"node": {"carrier": "AirIndia", "fare": 3200}},
                        {"node": {"carrier": "GoAir", "fare": 2900}},
                    ]
                }
            }
        })
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([graphql_payload], schema)
        assert result is not None
        assert result.record_count == 2
        assert result.records[0].get("airline") == "AirIndia"
        assert result.records[1].get("price") == 2900

    def test_nextjs_props_handling(self):
        nextjs_payload = json.dumps({
            "props": {
                "pageProps": {
                    "results": [
                        {"carrier": "Delta", "fare": "$500"},
                        {"carrier": "United", "fare": "$600"},
                    ]
                }
            }
        })
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([nextjs_payload], schema)
        assert result is not None
        assert result.record_count == 2
        assert result.records[0].get("airline") == "Delta"

    def test_nested_value_extraction(self):
        nested_val_payload = json.dumps({
            "results": [
                {"carrier": {"name": "Lufthansa"}, "fare": {"total": "$700"}},
                {"carrier": {"name": "Emirates"}, "fare": {"total": "$950"}},
            ]
        })
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([nested_val_payload], schema)
        assert result is not None
        assert result.record_count == 2
        assert result.records[0].get("airline") == "Lufthansa"
        assert result.records[0].get("price") == "$700"

    def test_secrets_not_in_field_map(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
        ]
        result = extract_from_network_payloads([FLIGHT_PAYLOAD], schema)
        assert result is not None
        for fm in result.field_map.values():
            assert "token" not in fm.mapped_from.lower()
            assert "cookie" not in fm.mapped_from.lower()

    def test_root_array_payload_extraction(self):
        root_array_payload = json.dumps([
            {"carrier": "British Airways", "fare": 310, "depart": "11:00"},
            {"carrier": "Lufthansa", "fare": 420, "depart": "15:30"},
        ])
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([root_array_payload], schema)
        assert result is not None
        assert result.record_count == 2
        assert result.records[0].get("airline") == "British Airways"
        assert result.records[1].get("price") == 420

    def test_irrelevant_arrays_ignored(self):
        payload = json.dumps({
            "status": "success",
            "metadata": {"user_id": 123},
            "tags": ["tag1", "tag2", "tag3"],  # Primitive array, ignored
        })
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
        ]
        result = extract_from_network_payloads([payload], schema)
        assert result is None

    def test_secret_heavy_payloads_not_ignored_but_sanitized(self):
        payload = json.dumps({
            "session_id": "sess_12345",
            "auth_token": "bearer_token_abc_xyz_789",
            "client_secret": "sec_99999",
            "results": [
                {"carrier": "IndiGo", "fare": 4500},
                {"carrier": "Vistara", "fare": 6100},
            ]
        })
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([payload], schema)
        assert result is not None
        assert result.record_count == 2
        assert result.records[0].get("airline") == "IndiGo"

    def test_candidate_array_secret_heavy_ignored(self):
        payload = json.dumps({
            "tokens": [
                {"session_id": "sess_1", "cookie": "abc", "token": "t1"},
                {"session_id": "sess_2", "cookie": "def", "token": "t2"},
            ]
        })
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
        ]
        result = extract_from_network_payloads([payload], schema)
        assert result is None

    def test_provenance_exact_path(self):
        nested_payload = json.dumps({
            "data": {
                "flights": [
                    {"airlineName": "Qatar", "fareCost": 900},
                    {"airlineName": "Emirates", "fareCost": 950},
                ]
            }
        })
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([nested_payload], schema)
        assert result is not None
        assert "airline" in result.field_map
        assert "price" in result.field_map
        assert result.field_map["airline"].mapped_from == "$.data.flights[*].airlineName"
        assert result.field_map["price"].mapped_from == "$.data.flights[*].fareCost"

    def test_strong_dom_weak_network_chooses_dom_explicit(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        net_result = extract_from_network_payloads(
            [json.dumps({"results": [{"x": 1}]})], schema
        )
        dom_records = [
            {"airline": "Air India", "price": "$300"},
            {"airline": "Singapore Air", "price": "$750"},
        ]
        records, source, _ = arbitrate_sources(dom_records, 95.0, net_result, schema)
        assert source == "dom"
        assert len(records) == 2

    def test_network_high_count_poor_coverage_does_not_win(self):
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        unrelated_records = [{"id": i, "timestamp": 123456789} for i in range(50)]
        net_result = extract_from_network_payloads(
            [json.dumps({"results": unrelated_records})], schema
        )
        dom_records = [
            {"airline": "Qatar Airways", "price": "$800"},
            {"airline": "Air France", "price": "$950"},
        ]
        records, source, _ = arbitrate_sources(dom_records, 85.0, net_result, schema)
        assert source == "dom"
        assert len(records) == 2

    def test_mixed_safe_results_secret_metadata_extracts_safe_records(self):
        payload = json.dumps({
            "session_id": "sess_deadbeef",
            "auth_token": "bearer_jwt_token_here",
            "client_secret": "my-secret-key-12345",
            "results": [
                {"carrier": "Lufthansa", "fare": 400},
                {"carrier": "KLM", "fare": 450},
            ]
        })
        schema = [
            SchemaField(name="airline", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([payload], schema)
        assert result is not None
        assert result.record_count == 2
        assert result.records[0].get("airline") == "Lufthansa"
        assert result.records[0].get("price") == 400
        for r in result.records:
            for k in r:
                assert "session_id" not in k
                assert "auth_token" not in k
                assert "client_secret" not in k

    def test_provenance_nested_suffix(self):
        payload = json.dumps({
            "results": [
                {"carrier": "Delta", "price": {"total": "$500"}},
                {"carrier": "United", "price": {"total": "$600"}},
            ]
        })
        schema = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = extract_from_network_payloads([payload], schema)
        assert result is not None
        assert "price" in result.field_map
        assert result.field_map["price"].mapped_from == "$.results[*].price.total"

    def test_invalid_airport_code_rejected_and_warnings(self):
        from app.utils.quality import post_extract_validate_records
        schema = [
            SchemaField(name="origin_airport_code", field_type=FieldType.STRING, required=True),
            SchemaField(name="destination_airport_code", field_type=FieldType.STRING, required=False),
        ]
        
        # 1. Required field invalid -> Discards record
        records1 = [
            {"origin_airport_code": "Guatemala City aerial view", "destination_airport_code": "JFK"}
        ]
        warnings = []
        res1 = post_extract_validate_records(records1, schema, warnings=warnings)
        assert len(res1) == 0
        assert "Airport-code fields failed semantic validation" in warnings

        # 2. Optional field invalid -> Sets to None
        records2 = [
            {"origin_airport_code": "MIA", "destination_airport_code": "New York City"}
        ]
        warnings = []
        res2 = post_extract_validate_records(records2, schema, warnings=warnings)
        assert len(res2) == 1
        assert res2[0]["destination_airport_code"] is None
        assert "Airport-code fields failed semantic validation" in warnings

    @pytest.mark.asyncio
    async def test_memory_downgraded_and_arbitration(self, monkeypatch):
        pass

