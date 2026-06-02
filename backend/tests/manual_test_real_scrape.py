import asyncio
import json

from app.models import FieldType, SchemaField
from app.scraper import scrape_url


async def test():
    fields = [
        SchemaField(name="company_name", field_type=FieldType.STRING, description="name of the company", required=True),
        SchemaField(name="contact_phone", field_type=FieldType.PHONE, description="phone number", required=False),
        SchemaField(name="email", field_type=FieldType.EMAIL, description="contact email address", required=False),
        SchemaField(name="address", field_type=FieldType.STRING, description="physical office address", required=False),
    ]

    url = "https://irishinterior.com/contact-us/"
    print(f"Scraping {url}...")
    results = await scrape_url(url, fields)
    print(f"\n=== RESULTS: {len(results)} records ===")
    for r in results:
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(test())
