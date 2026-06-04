"""End-to-end test: scrape flight data from flightsnholidays.co.uk.

Uses the selector profile system (backend/app/selector_profiles/profiles/)
which stores site-specific CSS selectors as JSON configs, NOT hardcoded Python.

Adding a new site = drop a .json file in profiles/. No code changes needed.

After profile-based extraction, records go through the same normalization,
scoring, dedup, and pipeline processing as the generic path — so they're
fully compatible with the /app/ frontend and job system.
"""

import asyncio
from pathlib import Path

from app.models import FieldType, SchemaField
from app.scraper import scrape_url

FLIGHT_SCHEMA = [
    SchemaField(name="origin", field_type=FieldType.STRING, description="", required=True),
    SchemaField(name="destination", field_type=FieldType.STRING, description="", required=True),
    SchemaField(name="date", field_type=FieldType.STRING, description="", required=False),
    SchemaField(name="price", field_type=FieldType.STRING, description="", required=False),
    SchemaField(name="stops", field_type=FieldType.STRING, description="", required=False),
]


def parse_price(price_str: str | None) -> float | None:
    """Extract numeric price from strings like '£238' or 'AED 500'."""
    if not price_str:
        return None
    import re

    cleaned = price_str.replace(",", "")
    match = re.search(r"[\d]+(?:\.[\d]+)?", cleaned)
    return float(match.group(0)) if match else None


def clean_airport(text: str | None) -> str | None:
    """Extract 3-letter airport code from text."""
    if not text:
        return None
    import re

    match = re.search(r"\b([A-Z]{3})\b", text.strip())
    return match.group(1) if match else text.strip()


async def test_flights_scrape() -> None:
    import os

    os.environ["DATAFORGE_STATE_FILE"] = str(Path(__file__).resolve().parent.parent / "data" / "jobs_state_test.json")

    url = (
        "https://www.flightsnholidays.co.uk/flight-result.aspx"
        "?From=LHR&To=PAR&ddate=05/22/2026&retdate=05/27/2026"
        "&Adult=1&Child=0&Infant=0&Class=Economy&FType=-1&IsReturn=1"
    )

    results = await scrape_url(url, FLIGHT_SCHEMA, min_record_score=0.1)

    total_price = 0.0
    price_count = 0
    for _i, r in enumerate(results, 1):
        p = parse_price(r.get("price"))
        if p:
            total_price += p
            price_count += 1

    total_price / price_count if price_count > 0 else 0.0

    if (len(results) > 0 and price_count > 0) or len(results) > 0:
        pass
    else:
        pass


if __name__ == "__main__":
    asyncio.run(test_flights_scrape())
