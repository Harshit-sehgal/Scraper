import asyncio
from app import scraper as s
from app.models import SchemaField, FieldType

async def test():
    schema = [SchemaField(name="test", field_type=FieldType.STRING)]
    
    # CASE 1: fast returns {}, std returns list
    print("CASE 1: fast returns {}, std returns list")
    s._llm_json_fast = lambda *args: {}
    s._llm_json = lambda *args: [{"test": "a"}]
    _, report = await s.ai_clean_and_align_records([{"test": "a"}], schema, 0.0)
    print(f"Report: {report}")
    
    # CASE 2: fast returns {}, std returns {} (3 times)
    print("\nCASE 2: fast returns {}, std returns {} (3 chunks)")
    s.AI_STRUCTURING_CHUNK_SIZE = 1
    s._llm_json_fast = lambda *args: {}
    s._llm_json = lambda *args: {}
    _, report = await s.ai_clean_and_align_records([{"test": "a"}, {"test": "b"}, {"test": "c"}], schema, 0.0)
    print(f"Report: {report}")

asyncio.run(test())
