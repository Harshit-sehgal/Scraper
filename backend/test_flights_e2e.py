"""
End-to-end test: scrape flight data from flightsnholidays.co.uk
Uses the scraper's scrape_url function directly (manual mode).
"""
import asyncio
import sys
import os

sys.path.insert(0, '.')
os.environ['DATAFORGE_STATE_FILE'] = 'data/jobs_state_test.json'

from app.models import FieldType, SchemaField
from app import scraper as scraper_mod


async def test_flights_scrape():
    url = (
        "https://flightsnholidays.co.uk/flight-result.aspx"
        "?From=LHR&To=PAR&ddate=05/22/2026&retdate=05/27/2026"
        "&Adult=1&Child=0&Infant=0&Class=Economy&FType=-1&IsReturn=1"
    )

    # Define schema fields for what we want to extract
    schema = [
        SchemaField(name="origin", field_type=FieldType.STRING, required=True,
                    description="Origin airport code or name"),
        SchemaField(name="destination", field_type=FieldType.STRING, required=True,
                    description="Destination airport code or name"),
        SchemaField(name="date", field_type=FieldType.DATE, required=False,
                    description="Departure or travel date"),
        SchemaField(name="price", field_type=FieldType.CURRENCY, required=True,
                    description="Price of the ticket"),
        SchemaField(name="stops", field_type=FieldType.STRING, required=False,
                    description="Number of stops (direct, 1 stop, etc.)"),
    ]

    print(f"Fetching: {url}")
    print(f"Schema: {[f.name for f in schema]}")

    # Call scrape_url directly (manual mode)
    results = await scraper_mod.scrape_url(
        url=url,
        schema_fields=schema,
        min_record_score=0.0,
        user_intent="flights from London to Paris",
    )

    print(f"\nResults: {len(results)} records")
    for i, r in enumerate(results):
        print(f"\n  Record {i + 1}:")
        for field in schema:
            val = r.get(field.name, "")
            score = r.get("record_score", "?")
            print(f"    {field.name}: {val}")
        print(f"    record_score: {score}")

    # Basic assertions
    assert len(results) > 0, "Should have extracted at least one record"
    
    price_found = any(r.get("price") for r in results)
    print(f"\n  Price found: {price_found}")

    print("\n✓ Test completed successfully")


if __name__ == "__main__":
    asyncio.run(test_flights_scrape())
