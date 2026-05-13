import asyncio
from app import scraper as s
from app.models import SchemaField, FieldType

async def test():
    schema = [SchemaField(name="test", field_type=FieldType.STRING)]
    records = [{"test": "a"}, {"test": "b"}, {"test": "c"}]
    
    # 1. Simulate empty fast, successful std
    print("Scenario 1: Empty fast, Success std")
    # Using real names now since they are in scraper.py
    s.AI_STRUCTURING_CHUNK_SIZE = 1
    # We must mock at the module level where they are imported or used
    # Actually scraper_mod uses _llm_json_fast which is imported from llm_bridge
    # but I re-imported it as _llm_json_fast in scraper.py
    
    original_fast = s._llm_json_fast
    original_std = s._llm_json
    
    s._llm_json_fast = lambda *args: {}
    s._llm_json = lambda *args: [{"test": "a"}]
    
    out, report = await s.ai_clean_and_align_records([{"test": "a"}], schema, 0.0)
    print(f"Report: {report}")
    
    # 2. Simulate 3 chunks, all fail
    print("\nScenario 2: 3 chunks, all fail")
    s._llm_json_fast = lambda *args: {}
    s._llm_json = lambda *args: {}
    s.AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES = 2
    
    out, report = await s.ai_clean_and_align_records(records, schema, 0.0)
    print(f"Report: {report}")

asyncio.run(test())
