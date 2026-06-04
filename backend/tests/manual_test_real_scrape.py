import asyncio

from app.models import FieldType, SchemaField
from app.scraper import scrape_url


async def test() -> None:
    fields = [
        SchemaField(name="company_name", field_type=FieldType.STRING, description="name of the company", required=True),
        SchemaField(name="contact_phone", field_type=FieldType.PHONE, description="phone number", required=False),
        SchemaField(name="email", field_type=FieldType.EMAIL, description="contact email address", required=False),
        SchemaField(name="address", field_type=FieldType.STRING, description="physical office address", required=False),
    ]

    url = "https://irishinterior.com/contact-us/"
    results = await scrape_url(url, fields)
    for _r in results:
        pass


if __name__ == "__main__":
    asyncio.run(test())
