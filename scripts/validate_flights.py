"""
Real-world Validation Script — flightsnholidays.co.uk
"""

import asyncio
import json
import logging
from app.models import FieldType, SchemaField
from app.scraper import scrape_url
from app.benchmark_accuracy import calculate_extraction_accuracy
from app.config import settings

# URL from a known search (London to Paris)
URL = "https://www.flightsnholidays.co.uk/flights-result.aspx?Origin=LON&Destination=PAR&DepartureDate=15/06/2026&ReturnDate=22/06/2026&Adults=1&Children=0&Infants=0&Class=Economy&IsDirect=false"

GOLDEN_RECORDS = [
    {"origin": "LHR", "destination": "CDG", "price": "238"},
    {"origin": "LGW", "destination": "ORY", "price": "195"}
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
    
    print("\n" + "="*40)
    print(" ACCURACY REPORT")
    print("="*40)
    print(f"Precision:   {metrics.precision:.2f}")
    print(f"Recall:      {metrics.recall:.2f}")
    print(f"F1 Score:    {metrics.f1_score:.2f}")
    print(f"Field Acc:   {metrics.field_accuracy}")
    print("="*40)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(validate())
