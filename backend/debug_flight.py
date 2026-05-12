"""Debug the flight scraping pipeline step by step."""
import asyncio
import os
import sys

sys.path.insert(0, '.')
os.environ['DATAFORGE_STATE_FILE'] = 'data/jobs_state_test.json'

from app import scraper as scraper_mod
from app.intent_parser import parse_user_intent
from app.models import FieldType, SchemaField
from app.page_profiler import detect_page_structure, detect_value_patterns
from app.semantic_mapper import map_to_schema_fields, match_values_to_intent
from app.semantic_segmentation import StructuralMemoryTracker, expand_composite_records


async def debug_flight_scrape():
    url = (
        "https://flightsnholidays.co.uk/flight-result.aspx"
        "?From=LHR&To=PAR&ddate=05/22/2026&retdate=05/27/2026"
        "&Adult=1&Child=0&Infant=0&Class=Economy&FType=-1&IsReturn=1"
    )

    schema = [
        SchemaField(name="origin", field_type=FieldType.STRING, required=True),
        SchemaField(name="destination", field_type=FieldType.STRING, required=True),
        SchemaField(name="date", field_type=FieldType.DATE, required=False),
        SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        SchemaField(name="stops", field_type=FieldType.STRING, required=False),
    ]

    # Step 1: Fetch
    html = await scraper_mod.fetch_page_content(url)
    print(f"Step 1: Fetched {len(html)} chars")

    # Step 2: Profile
    intent = parse_user_intent("flights from London to Paris")
    profile = detect_page_structure(html)
    patterns = detect_value_patterns(html)
    print(f"Step 2: Structure={profile.structure_type}, headers={profile.headers[:3]}")

    # Step 3: Extract (fallback to regex since no selector)
    scraper_mod.clean_html_for_selectors(html, max_chars=12000)
    results = scraper_mod.extract_with_regex(html, schema)
    print(f"Step 3: Regex extracted {len(results)} raw records")
    if results:
        print(f"  Sample record keys: {list(results[0].keys())}")
        for i, r in enumerate(results[:3]):
            vals = {k: str(v)[:50] for k, v in r.items() if v}
            print(f"  Record {i}: {vals}")

    # Step 3b: Expand composites
    if results:
        mem = StructuralMemoryTracker()
        expanded = expand_composite_records(results, memory=mem)
        print(f"\nStep 3b: Expanded {len(results)} -> {len(expanded)} records")
        if expanded:
            print(f"  Sample expanded keys: {[k for k in expanded[0].keys() if 'seg_' in k][:5]}")
            print(f"  All keys: {list(expanded[0].keys())}")

    # Step 4: Semantic mapping
    if expanded:
        headers = profile.headers or []
        mapped = match_values_to_intent(expanded, intent, profile, patterns, headers)
        print(f"\nStep 4: Mapped {len(mapped)} records")
        for i, m in enumerate(mapped[:3]):
            print(f"  Record {i}: mapped={m.mapped_fields}, conf={m.confidence_scores}")

        # Convert to schema
        converted = map_to_schema_fields(mapped, schema, intent)
        print(f"\n  Converted: {len(converted)} records")
        for i, r in enumerate(converted[:3]):
            vals = {k: v for k, v in r.items() if v and k != 'record_score'}
            print(f"  Record {i}: {vals}")


if __name__ == "__main__":
    asyncio.run(debug_flight_scrape())
