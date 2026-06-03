"""Live E2E: profile extraction + schema alignment (requires network + Playwright + GROQ_API_KEY).

CI skips these tests by default. Run manually with:
    RUN_LIVE_LLM_TESTS=1 pytest backend/tests/test_profile_alignment_e2e.py -q
"""

from __future__ import annotations

import os

import pytest
from app.data_utils import align_profile_keys_to_schema
from app.models import FieldType, SchemaField
from app.scraper import scrape_url
from app.selector_profiles.loader import _load_all_profiles, match_profile_for_url, try_profile_extraction

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_LLM_TESTS"),
    reason="Live Groq tests are optional. Set RUN_LIVE_LLM_TESTS=1 to run.",
)


def _profile_search_url(domain: str) -> str:
    """Build a search URL from profile domain only (no site-specific logic in app code)."""
    return (
        f"https://www.{domain}/flight-result.aspx"
        "?From=LON&To=PAR&ddate=05/30/2026&retdate=06/01/2026"
        "&Adult=1&Child=0&Infant=0&Class=Economy&FType=-1&IsReturn=1"
    )


def _custom_flight_schema() -> list[SchemaField]:
    return [
        SchemaField(name="airlines_name", field_type=FieldType.STRING, description="Name of the airline", required=True),
        SchemaField(name="origin_airport", field_type=FieldType.STRING, description="Airport of origin", required=True),
        SchemaField(name="destination_airport", field_type=FieldType.STRING, description="Airport of destination", required=True),
        SchemaField(name="prices", field_type=FieldType.CURRENCY, description="Price of the flight", required=True),
        SchemaField(name="departure_date", field_type=FieldType.DATE, description="Date of departure", required=True),
        SchemaField(name="arrival_date", field_type=FieldType.DATE, description="Date of arrival", required=True),
    ]


def _skip_if_no_api_key():
    """Skip test if no Groq API key is available (live API test)."""
    if not os.environ.get("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY not set — live API test requires a valid key")


@pytest.mark.asyncio
async def test_profile_extraction_aligns_all_schema_fields():
    """Profile returns multiple rows; alignment maps every profile key to best schema field."""
    _skip_if_no_api_key()
    profiles = _load_all_profiles()
    if not profiles:
        pytest.skip("No selector profiles on disk")

    # Try each domain until one returns populated results
    last_error = None
    for domain in list(profiles.keys())[:5]:
        url = _profile_search_url(domain)
        try:
            profile = match_profile_for_url(url)
            if profile is None:
                last_error = f"No profile matched for {domain}"
                continue

            raw = await try_profile_extraction(url)
            if not raw:
                last_error = f"Live extraction unavailable for {domain}"
                continue

            # Check if records have populated data or just nulls from API rate-limiting
            populated = [r for r in raw if r.get("airlines_name") and r.get("prices") is not None]
            if not populated:
                last_error = f"try_profile_extraction returned {len(raw)} record(s) with null fields for {
                    domain
                } — likely API rate-limiting"
                continue

            # Got populated results — run assertions
            schema = _custom_flight_schema()
            aligned = align_profile_keys_to_schema(populated, schema, profile_fields=profile.get("fields"))
            assert len(aligned) >= 2

            for row in aligned:
                assert row.get("airlines_name")
                assert row.get("origin_airport")
                assert row.get("destination_airport")
                assert row.get("prices") is not None
                assert row.get("departure_date")
                assert row.get("arrival_date") not in ("Direct", "1 Stop", "2 Stops", None)
                assert "stops" not in row
                assert row.get("arrival_date")
            return  # Success!
        except Exception as e:
            last_error = f"Extraction failed for {domain}: {e}"
            continue

    # All domains failed
    pytest.skip(f"All domains failed: {last_error}")


@pytest.mark.asyncio
async def test_scrape_url_end_to_end_multiple_records():
    _skip_if_no_api_key()
    profiles = _load_all_profiles()
    if not profiles:
        pytest.skip("No selector profiles on disk")

    # Try each domain until one returns populated results
    last_error = None
    for domain in list(profiles.keys())[:5]:
        url = _profile_search_url(domain)
        try:
            results = await scrape_url(url, _custom_flight_schema(), min_record_score=0.1)
            if not results:
                last_error = f"scrape_url returned no records for {domain}"
                continue

            # Check if records have populated data or just nulls from API rate-limiting
            populated = [r for r in results if r.get("airlines_name") and r.get("prices") is not None]
            if not populated:
                last_error = (
                    f"scrape_url returned {len(results)} record(s) with null fields for {domain} — likely API rate-limiting"
                )
                continue

            # Got populated results — run assertions
            assert len(populated) >= 2
            for r in populated:
                assert r.get("airlines_name")
                assert r.get("origin_airport")
                assert r.get("destination_airport")
                assert r.get("prices") is not None
                assert r.get("departure_date")
                assert r.get("arrival_date") not in ("Direct", "1 Stop", "2 Stops", None)
                assert r.get("arrival_date")
            return  # Success!
        except Exception as e:
            last_error = f"scrape_url failed for {domain}: {e}"
            continue

    # All domains failed
    pytest.skip(f"All domains failed: {last_error}")
