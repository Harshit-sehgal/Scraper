import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.scraper import scrape_url
from app.models import ScrapeMode, SchemaField, FieldType
from app.config import settings

async def main():
    target = "https://nowsecure.nl/"
    if len(sys.argv) > 1:
        target = sys.argv[1]

    print(f"Testing Scraper against live target: {target}")
    
    try:
        result = await scrape_url(
            url=target,
            schema_fields=[SchemaField(name="title", field_type=FieldType.STRING, required=True)],
            user_intent="Extract the page title",
            selectors_map={"title": "title"}
        )
        
        print("\n--- EXTRACTION RESULTS ---")
        if not result:
            print("No records extracted.")
        for r in result[:3]:
            print(r)
            
        print("\n--- TELEMETRY / ANTI-BOT ---")
        # Telemetry info should be in the result object if it's a ScrapeAttemptResult
        if hasattr(result, 'to_telemetry_dict'):
            t = result.to_telemetry_dict()
            print(f"Fallback: {t.get('fallback_triggered')} | Evasion: {t.get('evasion_used')} | State: {t.get('state')} | Strategy: {t.get('strategy')}")
        else:
            print("Result is a plain list, checking telemetry store.")
            from app.scrape_telemetry import get_scrape_telemetry
            tel = get_scrape_telemetry().get_recent(5)
            for t in tel:
                if target in t.get('url', ''):
                    print(f"Fallback: {t.get('fallback_triggered')} | Evasion: {t.get('evasion_used')} | State: {t.get('state')} | Strategy: {t.get('strategy')}")
            
    except Exception as e:
        print(f"Extraction failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
