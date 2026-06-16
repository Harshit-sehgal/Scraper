import asyncio

from app.models import FieldType, SchemaField
from app.scraper import scrape_url


async def _test() -> None:
    fields = [
        SchemaField(name="book_title", field_type=FieldType.STRING, description="title of the book", required=False),
        SchemaField(name="price", field_type=FieldType.CURRENCY, description="price in pounds", required=False),
        SchemaField(name="rating", field_type=FieldType.STRING, description="star rating", required=False),
        SchemaField(name="availability", field_type=FieldType.STRING, description="in stock or not", required=False),
    ]

    results = await scrape_url("https://books.toscrape.com/", fields)
    for _r in results[:5]:
        pass


if __name__ == "__main__":
    asyncio.run(_test())
