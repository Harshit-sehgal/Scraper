# Tutorial 1: Your First Extraction

This tutorial walks through creating your first extraction job with DataForge.

## Prerequisites

- DataForge API running locally or a deployed instance
- API key (set `DATAFORGE_API_KEY` in your environment)

## Step 1: Create an Extraction Job

Use the API to extract data from a public web page:

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My first extraction",
    "mode": "manual",
    "urls": ["https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"],
    "schema_fields": [
      {"name": "title", "field_type": "string"},
      {"name": "price", "field_type": "string"}
    ]
  }'
```

## Step 2: Check Job Status

Poll the job endpoint until the status is `completed`:

```bash
curl -s http://localhost:8000/api/jobs/{job_id} \
  -H "Authorization: Bearer $DATAFORGE_API_KEY"
```

## Step 3: Retrieve Results

After completion, fetch the extracted data:

```bash
curl -s http://localhost:8000/api/jobs/{job_id}/results \
  -H "Authorization: Bearer $DATAFORGE_API_KEY"
```

## Using the Python SDK

```python
from sdk import DataForge

client = DataForge(api_key="df_key_...")
result = await client.extract(
    url="https://books.toscrape.com/",
    schema_fields=[{"name": "title", "field_type": "string"}],
)
print(result)
```

## Next Steps

- Learn about pagination in Tutorial 2
- Customize selectors in Tutorial 3
