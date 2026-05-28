import asyncio
import os
import json
from dotenv import load_dotenv

# Load env before importing app modules
load_dotenv()

from app.models import SchemaField, FieldType
from app.extraction_orchestrator import orchestrate_extraction
from app.html_utils import fetch_page_content
from app.llm_extractor import html_to_markdown

async def run_test():
    url = "https://news.ycombinator.com/"
    print(f"Testing extraction on {url}")
    
    # 1. Define schema
    schema = [
        SchemaField(name="title", field_type=FieldType.STRING, description="The title of the news article", required=True),
        SchemaField(name="points", field_type=FieldType.INTEGER, description="The number of points or votes", required=False),
        SchemaField(name="user", field_type=FieldType.STRING, description="The username of the submitter", required=False),
    ]
    
    # 2. Fetch page
    print("Fetching page...")
    html, score, fetch_method, time_ms = await fetch_page_content(url)
    if not html:
        print("Failed to fetch page.")
        return
        
    print(f"Fetched HTML ({len(html)} bytes).")
    
    # Optional: check markdown length
    md = html_to_markdown(html)
    print(f"Converted to Markdown ({len(md)} characters).")
    print("-" * 50)
    print(md[:500] + "\n...")
    print("-" * 50)
    
    print("Extracting data via Direct LLM Layer...")
    from app.llm_extractor import extract_with_llm
    llm_records = await extract_with_llm(html, schema, url)
    print(f"LLM returned: {len(llm_records)} records")
    print(llm_records)
    
    print("\nExtracting data via Orchestrator (Direct LLM Layer + Fallbacks)...")
    # Using orchestrate_extraction to test the full cascade we just refactored
    result = await orchestrate_extraction(
        html=html,
        schema_fields=schema,
        url=url,
        min_record_score=0.1,
    )
    
    print("\n--- EXTRACTION RESULTS ---")
    print(f"Extraction Method: {result.method}")
    print(f"Number of records: {len(result.records)}")
    print(json.dumps(result.records[:5], indent=2))
    
    if len(result.records) > 0:
        print("\nSUCCESS! Extraction retrieved records.")
    else:
        print("\nFAILURE. No records extracted.")

if __name__ == "__main__":
    asyncio.run(run_test())
