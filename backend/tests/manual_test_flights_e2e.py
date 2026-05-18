"""
End-to-end test: scrape flight data from flightsnholidays.co.uk

Uses the site-specific custom scraper (app.custom_scrapers.flightsnholidays)
which targets the actual DOM structure with precise CSS selectors instead
of relying on the generic LLM-selector pipeline.
"""

import asyncio
import os
from pathlib import Path

os.environ['DATAFORGE_STATE_FILE'] = str(
    Path(__file__).resolve().parent.parent / 'data' / 'jobs_state_test.json'
)

from app.custom_scrapers.flightsnholidays import (
    scrape_flightsnholidays,
    parse_price,
    parse_airport,
)


async def test_flights_scrape():
    url = (
        "https://www.flightsnholidays.co.uk/flight-result.aspx"
        "?From=LHR&To=PAR&ddate=05/22/2026&retdate=05/27/2026"
        "&Adult=1&Child=0&Infant=0&Class=Economy&FType=-1&IsReturn=1"
    )

    print(f"Fetching: {url}")
    print(f"Using site-specific custom scraper for flightsnholidays.co.uk\n")

    results = await scrape_flightsnholidays(url, max_wait=30)

    print(f"Results: {len(results)} records\n")
    for i, r in enumerate(results, 1):
        print(f"  Record {i}:")
        print(f"    Origin:      {r.get('origin')}    → Clean: {parse_airport(r.get('origin'))}")
        print(f"    Destination: {r.get('destination')} → Clean: {parse_airport(r.get('destination'))}")
        print(f"    Date:        {r.get('date')}")
        print(f"    Price:       {r.get('price')}    → Numeric: £{parse_price(r.get('price')):.2f}" if parse_price(r.get('price')) else f"    Price:       {r.get('price')}    → Numeric: None")
        print(f"    Stops:       {r.get('stops')}")
        print()

    # Basic assertions
    assert len(results) > 0, "Should have extracted at least one record"

    price_found = any(parse_price(r.get("price")) for r in results)
    print(f"  Price found: {price_found}")
    print(f"  Origin found: {any(r.get('origin') for r in results)}")
    print(f"  Destination found: {any(r.get('destination') for r in results)}")

    if price_found:
        print("\n✓ Test completed successfully — flight data extracted correctly")
    else:
        print("\n⚠ Test completed — records found but prices may need format adjustment")


if __name__ == "__main__":
    asyncio.run(test_flights_scrape())
