import asyncio, sys, json
sys.path.insert(0, '/home/harshit/Documents/Work/Money/scraper/backend')
from app.scraper import scrape_url
from app.models import SchemaField, FieldType

async def test():
    fields = [
        SchemaField(name='title', field_type=FieldType.STRING, description='title of the article'),
        SchemaField(name='score', field_type=FieldType.INTEGER, description='number of points or upvotes'),
        SchemaField(name='author', field_type=FieldType.STRING, description='username of submitter'),
        SchemaField(name='link', field_type=FieldType.URL, description='url of the article'),
    ]
    
    print('Scraping Hacker News...')
    results = await scrape_url('https://news.ycombinator.com/', fields)
    print(f'\n=== RESULTS: {len(results)} records ===')
    for r in results[:5]:
        print(json.dumps(r, ensure_ascii=False, indent=2))

asyncio.run(test())
