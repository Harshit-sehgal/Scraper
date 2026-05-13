import asyncio
from app import scraper as s
from app.models import SchemaField, FieldType

async def test():
    schema = [SchemaField(name="test", field_type=FieldType.STRING)]
    # CASE: fast returns {} (non-list), std returns list
    s._llm_json_fast = lambda *args: {}
    s._llm_json = lambda *args: [{"test": "a"}]
    _, report = await s.ai_clean_and_align_records([{"test": "a"}], schema, 0.0)
    print(f"Report: {report}")

asyncio.run(test())
