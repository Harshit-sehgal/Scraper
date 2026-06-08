"""
Real-world Validation Script — flightsnholidays.co.uk
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.benchmark_accuracy import calculate_extraction_accuracy
from app.config import settings
from app.models import FieldType, SchemaField
from app.scraper import scrape_url

# URL from a known search (London to Paris)
URL = "https://www.flightsnholidays.co.uk/flight-result.aspx?From=LON&To=PAR&ddate=06/15/2026&retdate=06/22/2026&Adult=1&Child=0&Infant=0&Class=Economy&FType=-1&IsReturn=1"

GOLDEN_RECORDS = [
    {"origin": "LON", "destination": "PAR", "date": "15-06-2026", "price": "238"},
    {"origin": "LON", "destination": "PAR", "date": "15-06-2026", "price": "248"},
    {"origin": "LON", "destination": "PAR", "date": "15-06-2026", "price": "260"},
]


async def validate():
    # Enable manual visual debugging if needed
    settings.PLAYWRIGHT_HEADLESS = True

    fields = [
        SchemaField(name="origin", field_type=FieldType.STRING),
        SchemaField(name="destination", field_type=FieldType.STRING),
        SchemaField(name="date", field_type=FieldType.STRING),
        SchemaField(name="price", field_type=FieldType.CURRENCY),
    ]

    print(f"Scraping: {URL}")
    results = await scrape_url(URL, fields)

    print(f"\nEXTRACTED {len(results)} RECORDS:")
    for r in results[:3]:
        # Filter internal fields for clean output
        display = {k: v for k, v in r.items() if not k.startswith("_")}
        print(json.dumps(display, indent=2))

    # Compare with golden (subset matching)
    metrics = calculate_extraction_accuracy(results, GOLDEN_RECORDS, domain="flightsnholidays.co.uk")

    print("\n" + "=" * 40)
    print(" ACCURACY REPORT")
    print("=" * 40)
    print(f"Precision:   {metrics.precision:.2f}")
    print(f"Recall:      {metrics.recall:.2f}")
    print(f"F1 Score:    {metrics.f1_score:.2f}")
    print(f"Field Acc:   {metrics.field_accuracy}")
    print("=" * 40)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(validate())
