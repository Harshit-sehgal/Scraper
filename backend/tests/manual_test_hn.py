import asyncio
import json

from app.models import FieldType, SchemaField
from app.scraper import scrape_url


async def test():
    fields = [
        SchemaField(name='title', field_type=FieldType.STRING, description='title of the article', required=False),
        SchemaField(name='score', field_type=FieldType.INTEGER, description='number of points or upvotes', required=False),
        SchemaField(name='author', field_type=FieldType.STRING, description='username of submitter', required=False),
        SchemaField(name='link', field_type=FieldType.URL, description='url of the article', required=False),
    ]
    
    print('Scraping Hacker News...')
    results = await scrape_url('https://news.ycombinator.com/', fields)
    print(f'\n=== RESULTS: {len(results)} records ===')
    for r in results[:5]:
        print(json.dumps(r, ensure_ascii=False, indent=2))

asyncio.run(test())
