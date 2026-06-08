"""
Real-world Validation Script — books.toscrape.com (Sandbox)
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.benchmark_accuracy import calculate_extraction_accuracy
from app.models import FieldType, SchemaField
from app.scraper import scrape_url

URL = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"

GOLDEN_RECORDS = [{"title": "Sharp Objects", "price": "47.82"}, {"title": "In a Dark, Dark Wood", "price": "19.63"}]


async def validate():
    fields = [
        SchemaField(name="title", field_type=FieldType.STRING, required=True),
        SchemaField(name="price", field_type=FieldType.CURRENCY),
        SchemaField(name="availability", field_type=FieldType.STRING),
    ]

    print(f"Scraping: {URL}")
    results = await scrape_url(URL, fields)

    print(f"\nEXTRACTED {len(results)} RECORDS:")
    for r in results[:3]:
        # Filter internal fields for clean output
        display = {k: v for k, v in r.items() if not k.startswith("_")}
        print(json.dumps(display, indent=2))

    # Compare with golden (subset matching)
    metrics = calculate_extraction_accuracy(results, GOLDEN_RECORDS, domain="books.toscrape.com")

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
