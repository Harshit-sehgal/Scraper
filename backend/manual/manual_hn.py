import asyncio

from app.models import FieldType, SchemaField
from app.scraper import scrape_url


async def test() -> None:
    fields = [
        SchemaField(name="title", field_type=FieldType.STRING, description="title of the article", required=False),
        SchemaField(name="score", field_type=FieldType.INTEGER, description="number of points or upvotes", required=False),
        SchemaField(name="author", field_type=FieldType.STRING, description="username of submitter", required=False),
        SchemaField(name="link", field_type=FieldType.URL, description="url of the article", required=False),
    ]

    results = await scrape_url("https://news.ycombinator.com/", fields)
    for _r in results[:5]:
        pass


if __name__ == "__main__":
    asyncio.run(test())
