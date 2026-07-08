import asyncio
import logging
from app.selector_profiles.loader import try_profile_extraction

async def debug():
    logging.basicConfig(level=logging.INFO)
    url = "https://www.flightsnholidays.co.uk/flight-result.aspx?From=LON&To=PAR&ddate=06/15/2026&retdate=06/22/2026&Adult=1&Child=0&Infant=0&Class=Economy&FType=-1&IsReturn=1"
    records = await try_profile_extraction(url)
    print("\nRAW EXTRACTED RECORDS:")
    for i, r in enumerate(records or []):
        print(f"Record {i}: {r}")

    from app.models import SchemaField, FieldType
    from app.data_utils import normalize_scraped_record
    from app.utils.quality import score_record_quality
    
    fields = [
        SchemaField(name="origin", field_type=FieldType.STRING, description="", required=False),
        SchemaField(name="destination", field_type=FieldType.STRING, description="", required=False),
        SchemaField(name="date", field_type=FieldType.STRING, description="", required=False),
        SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
    ]
    
    print("\nNORMALIZED & SCORED RECORDS:")
    for i, r in enumerate(records or []):
        norm = normalize_scraped_record(r, fields)
        score = score_record_quality(norm, fields)
        print(f"Record {i} Score: {score}")
        print(f"  {norm}")

if __name__ == "__main__":
    asyncio.run(debug())
