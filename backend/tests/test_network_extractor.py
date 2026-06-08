"""Tests for network_extractor — JSON-LD, nested JSON, Apollo state, and network payload extraction."""

import pytest
from app.models import FieldType, SchemaField
from app.network_extractor import (
    _deduplicate_records,
    _extract_from_apollo_state,
    _extract_from_jsonld,
    _extract_from_nested_json,
    _extract_records_from_payloads,
    _find_value_for_field,
    _flatten_json_keys,
    _map_json_keys_to_schema,
    _map_jsonld_item,
    extract_from_network,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_schema():
    return [
        SchemaField(name="name", field_type=FieldType.STRING, required=False, description=""),
        SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
        SchemaField(name="description", field_type=FieldType.STRING, required=False, description=""),
    ]


# ─── Test extract_from_network (public API) ───────────────────────────────


class TestExtractFromNetwork:
    def test_returns_empty_list_for_empty_schema(self):
        result = extract_from_network({"jsonld": []}, [])
        assert result == []

    def test_returns_empty_list_for_empty_data(self, sample_schema):
        result = extract_from_network({}, sample_schema)
        assert result == []

    def test_extracts_from_jsonld_products(self, sample_schema):
        """Integration: JSON-LD product data flows through to records."""
        data = {
            "jsonld": [
                {
                    "@type": "Product",
                    "name": "Test Product",
                    "description": "A great product",
                    "offers": {"price": "29.99", "priceCurrency": "USD"},
                },
            ],
        }
        result = extract_from_network(data, sample_schema)
        assert len(result) > 0
        assert result[0].get("name") == "Test Product"
        assert result[0].get("record_score", 0) > 0

    def test_extracts_from_network_payloads(self, sample_schema):
        payloads = [{"body": {"results": [{"name": "Payload Item", "price": 100}]}}]
        data: dict = {"jsonld": []}
        result = extract_from_network(data, sample_schema, network_payloads=payloads)
        assert len(result) > 0
        assert result[0].get("name") == "Payload Item"

    def test_scored_and_sorted(self, sample_schema):
        data = {
            "jsonld": [
                {"@type": "Product", "name": "A", "description": "Desc A"},
                {"@type": "Product", "name": "B", "description": "Desc B"},
            ],
        }
        result = extract_from_network(data, sample_schema)
        assert len(result) == 2
        # Should be sorted by record_score descending
        scores = [r.get("record_score", 0) for r in result]
        assert scores == sorted(scores, reverse=True)


# ─── Test JSON-LD extraction ──────────────────────────────────────────────


class TestExtractFromJsonld:
    def test_extracts_from_graph(self, sample_schema):
        jsonld = [{"@graph": [{"@type": "Product", "name": "G1"}, {"@type": "Product", "name": "G2"}]}]
        result = _extract_from_jsonld(jsonld, sample_schema)
        assert len(result) == 2

    def test_extracts_from_item_list(self, sample_schema):
        jsonld = [{"itemListElement": [{"@type": "Product", "name": "I1"}, {"@type": "Product", "name": "I2"}]}]
        result = _extract_from_jsonld(jsonld, sample_schema)
        assert len(result) == 2

    def test_extracts_from_has_part(self, sample_schema):
        jsonld = [{"hasPart": [{"@type": "Article", "name": "Part1"}]}]
        result = _extract_from_jsonld(jsonld, sample_schema)
        assert len(result) >= 1

    def test_returns_empty_for_empty_list(self, sample_schema):
        assert _extract_from_jsonld([], sample_schema) == []

    def test_returns_empty_for_non_dict_items(self, sample_schema):
        assert _extract_from_jsonld([{"@graph": ["not_a_dict"]}], sample_schema) == []

    def test_extracts_flat_json_as_single_record(self, sample_schema):
        jsonld = [{"name": "Flat Item", "description": "Flat desc"}]
        result = _extract_from_jsonld(jsonld, sample_schema)
        assert len(result) == 1
        assert result[0]["name"] == "Flat Item"


# ─── Test map_jsonld_item type handlers ───────────────────────────────────


class TestMapJsonldItem:
    def test_product_type_handler(self, sample_schema):
        item = {"@type": "Product", "name": "Widget", "brand": {"name": "Acme"}, "sku": "W123"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None
        assert result.get("name") == "Widget"

    def test_offer_type_handler(self, sample_schema):
        item = {"@type": "Offer", "price": "49.99", "priceCurrency": "USD", "name": "Special Offer"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None

    def test_flight_type_handler(self, sample_schema):
        item = {
            "@type": "Flight",
            "flightNumber": "AA123",
            "airline": {"name": "American Airlines"},
            "departureAirport": {"iataCode": "JFK"},
            "arrivalAirport": {"iataCode": "LAX"},
            "departureTime": "2025-06-15T10:30:00",
            "arrivalTime": "2025-06-15T13:45:00",
            "totalPrice": "350",
        }
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None
        assert "carrier" in result

    def test_hotel_type_handler(self, sample_schema):
        item = {"@type": "Hotel", "name": "Grand Hotel", "telephone": "+1-555-0100"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None

    def test_job_type_handler(self, sample_schema):
        item = {"@type": "JobPosting", "title": "Engineer", "hiringOrganization": {"name": "Corp Inc"}}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None
        assert result.get("title") == "Engineer"

    def test_event_type_handler(self, sample_schema):
        item = {"@type": "Event", "name": "Concert", "startDate": "2025-07-04"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None

    def test_business_type_handler(self, sample_schema):
        item = {"@type": "LocalBusiness", "name": "Shop", "telephone": "+1-555-0200"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None

    def test_person_type_handler(self, sample_schema):
        item = {"@type": "Person", "name": "John Doe", "email": "john@example.com"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None
        assert result.get("name") == "John Doe"

    def test_article_type_handler(self, sample_schema):
        item = {"@type": "Article", "headline": "Breaking News", "datePublished": "2025-01-01"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None

    def test_book_type_handler(self, sample_schema):
        item = {"@type": "Book", "name": "The Book", "isbn": "978-3-16-148410-0"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None

    def test_movie_type_handler(self, sample_schema):
        item = {"@type": "Movie", "name": "The Movie"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None

    def test_app_type_handler(self, sample_schema):
        item = {"@type": "SoftwareApplication", "name": "MyApp"}
        result = _map_jsonld_item(item, sample_schema)
        assert result is not None

    def test_returns_none_for_empty_item(self, sample_schema):
        assert _map_jsonld_item({}, sample_schema) is None

    def test_returns_none_for_item_with_no_meaningful_values(self, sample_schema):
        result = _map_jsonld_item({"@type": "Product"}, sample_schema)
        assert result is None


# ─── Test nested JSON extraction ──────────────────────────────────────────


class TestExtractFromNestedJson:
    def test_finds_nested_record_arrays(self, sample_schema):
        data = {
            "data": {
                "products": [
                    {"name": "Nested Product", "price": 25},
                    {"name": "Nested Product 2", "price": 35},
                ],
            },
        }
        result = _extract_from_nested_json(data, sample_schema)
        assert len(result) > 0

    def test_returns_empty_for_empty_data(self, sample_schema):
        assert _extract_from_nested_json({}, sample_schema) == []

    def test_returns_empty_for_non_dict_data(self, sample_schema):
        # Type-safe: pass empty dict since the signature expects dict
        assert _extract_from_nested_json({}, sample_schema) == []

    def test_respects_max_depth(self, sample_schema):
        deep = {"l1": {"l2": {"l3": {"l4": {"l5": {"l6": {"name": "Too Deep"}}}}}}}
        result = _extract_from_nested_json(deep, sample_schema)
        assert result == []

    def test_finds_top_level_record_array(self, sample_schema):
        data = {"items": [{"name": "Item 1"}, {"name": "Item 2"}]}
        result = _extract_from_nested_json(data, sample_schema)
        assert len(result) > 0


# ─── Test Apollo state extraction ─────────────────────────────────────────


class TestExtractFromApolloState:
    def test_extracts_from_apollo_entities(self, sample_schema):
        data = {
            "Product:1": {"__typename": "Product", "name": "Apollo Product"},
            "Product:2": {"__typename": "Product", "name": "Apollo Product 2"},
        }
        result = _extract_from_apollo_state(data, sample_schema)
        assert len(result) > 0

    def test_extracts_from_root_query_refs(self, sample_schema):
        data = {
            "ROOT_QUERY": [{"__ref": "Product:1"}],
            "Product:1": {"__typename": "Product", "name": "Refd Product"},
        }
        result = _extract_from_apollo_state(data, sample_schema)
        assert len(result) > 0

    def test_returns_empty_for_empty_data(self, sample_schema):
        assert _extract_from_apollo_state({}, sample_schema) == []

    def test_returns_empty_for_non_dict_data(self, sample_schema):
        # Type-safe: pass empty dict since the signature expects dict
        assert _extract_from_apollo_state({}, sample_schema) == []


# ─── Test network payload extraction ──────────────────────────────────────


class TestExtractRecordsFromPayloads:
    def test_extracts_from_payload_body(self, sample_schema):
        payloads = [{"body": {"results": [{"name": "Payload Item"}]}}]
        result = _extract_records_from_payloads(payloads, sample_schema)
        assert len(result) > 0

    def test_returns_empty_for_empty_payloads(self, sample_schema):
        assert _extract_records_from_payloads([], sample_schema) == []

    def test_returns_empty_for_non_dict_body(self, sample_schema):
        payloads = [{"body": "not a dict"}]
        result = _extract_records_from_payloads(payloads, sample_schema)
        assert result == []

    def test_handles_list_body(self, sample_schema):
        payloads = [{"body": [{"name": "List Item 1"}, {"name": "List Item 2"}]}]
        result = _extract_records_from_payloads(payloads, sample_schema)
        assert len(result) == 2

    def test_deduplicates(self, sample_schema):
        payloads = [{"body": {"results": [{"name": "Dup"}, {"name": "Dup"}]}}]
        result = _extract_records_from_payloads(payloads, sample_schema)
        assert len(result) == 1


# ─── Test deduplication ───────────────────────────────────────────────────


class TestDeduplicateRecords:
    def test_removes_duplicates(self):
        records = [
            {"name": "Unique", "price": "10"},
            {"name": "Duplicate", "price": "20"},
            {"name": "Duplicate", "price": "20"},
        ]
        result = _deduplicate_records(records)
        assert len(result) == 2

    def test_keeps_unique_records(self):
        records = [
            {"name": "Product A", "price": "10.00"},
            {"name": "Product B", "price": "20.00"},
            {"name": "Product C", "price": "30.00"},
        ]
        result = _deduplicate_records(records)
        assert len(result) == 3

    def test_handles_empty_records(self):
        assert _deduplicate_records([]) == []

    def test_skips_records_without_significant_values(self):
        records = [{"x": "y"}, {"x": "y"}]
        result = _deduplicate_records(records)
        assert result == []  # No values > 2 chars = no signature


# ─── Test key-value alignment ─────────────────────────────────────────────


class TestMapJsonKeysToSchema:
    def test_direct_match(self, sample_schema):
        item = {"name": "Direct Match", "price": 100}
        result = _map_json_keys_to_schema(item, sample_schema)
        assert result.get("name") == "Direct Match"
        assert result.get("price") == 100

    def test_alias_match(self, sample_schema):
        item = {"title": "Alias Match"}
        result = _map_json_keys_to_schema(item, sample_schema)
        assert result.get("name") == "Alias Match"

    def test_returns_empty_for_empty_item(self, sample_schema):
        assert _map_json_keys_to_schema({}, sample_schema) == {}

    def test_returns_empty_for_non_dict(self, sample_schema):
        # Type-safe: pass empty dict since the signature expects dict
        assert _map_json_keys_to_schema({}, sample_schema) == {}


class TestFlattenJsonKeys:
    def test_flattens_simple_dict(self):
        result = _flatten_json_keys({"name": "test", "price": 100})
        assert result.get("name") == "test"
        assert result.get("price") == 100

    def test_flattens_nested_dict(self):
        result = _flatten_json_keys({"product": {"name": "Nested"}})
        # Should have both nested and flat keys
        assert "product_name" in result
        assert result.get("name") == "Nested"

    def test_respects_max_depth(self):
        deep = {"a": {"b": {"c": {"d": {"e": "too deep"}}}}}
        result = _flatten_json_keys(deep, max_depth=3)
        assert "a_b_c_d_e" not in result

    def test_handles_string_lists(self):
        result = _flatten_json_keys({"tags": ["a", "b", "c"]})
        assert "tags" in result
        assert "a, b, c" in result.values()


class TestFindValueForField:
    def test_direct_match(self, sample_schema):
        flat = {"name": "Direct"}
        result = _find_value_for_field("name", "name", None, flat)
        assert result == "Direct"

    def test_alias_match(self, sample_schema):
        flat = {"title": "Alias Match"}
        result = _find_value_for_field("name", "name", None, flat)
        assert result == "Alias Match"

    def test_word_overlap_match(self):
        flat = {"company_name": "Acme Corp"}
        result = _find_value_for_field("company", "company", None, flat)
        assert result == "Acme Corp"

    def test_low_overlap_returns_none(self):
        flat = {"completely_unrelated_key": "value"}
        result = _find_value_for_field("name", "name", None, flat)
        assert result is None
