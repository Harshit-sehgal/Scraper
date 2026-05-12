import asyncio, sys, json
sys.path.insert(0, '/home/harshit/Documents/Work/Money/scraper/backend')
from app.scraper import scrape_url
from app.models import SchemaField, FieldType

async def test():
    fields = [
        SchemaField(name='company_name', field_type=FieldType.STRING, description='name of the company', required=True),
        SchemaField(name='contact_phone', field_type=FieldType.PHONE, description='phone number', required=False),
        SchemaField(name='email', field_type=FieldType.EMAIL, description='contact email address', required=False),
        SchemaField(name='address', field_type=FieldType.STRING, description='physical office address', required=False)
    ]
    
    url = 'https://irishinterior.com/contact-us/'
    print(f'Scraping {url}...')
    results = await scrape_url(url, fields)
    print(f'\n=== RESULTS: {len(results)} records ===')
    for r in results:
        print(json.dumps(r, ensure_ascii=False, indent=2))

asyncio.run(test())
