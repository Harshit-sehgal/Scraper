import asyncio
import json
import sys

sys.path.insert(0, '/home/harshit/Documents/Work/Money/scraper/backend')
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


async def test():
    fields = [
        SchemaField(name='book_title', field_type=FieldType.STRING, description='title of the book'),
        SchemaField(name='price', field_type=FieldType.CURRENCY, description='price in pounds'),
        SchemaField(name='rating', field_type=FieldType.STRING, description='star rating'),
        SchemaField(name='availability', field_type=FieldType.STRING, description='in stock or not'),
    ]
    
    print('Scraping with scrape_url...')
    results = await scrape_url('https://books.toscrape.com/', fields)
    print(f'\n=== RESULTS: {len(results)} records ===')
    for r in results[:5]:
        print(json.dumps(r, ensure_ascii=False, indent=2))

asyncio.run(test())
