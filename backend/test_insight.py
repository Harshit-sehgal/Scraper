import asyncio
import sys

sys.path.insert(0, '/home/harshit/Documents/Work/Money/scraper/backend')
from app.scraper import generate_data_insight


async def test():
    records = [
        {"book_title": "A Light in the Attic", "price": "£51.77", "rating": "Three"},
        {"book_title": "Tipping the Velvet", "price": "£53.74", "rating": "One"},
        {"book_title": "Soumission", "price": "£50.10", "rating": "One"},
    ]
    print('Testing Insight Generation...')
    insight = await generate_data_insight(records)
    print(f'\n=== Insight ===\n{insight}')

asyncio.run(test())
