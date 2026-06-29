# Tutorial 3: Custom Selectors and Schemas

Define exactly what data to extract and how to extract it.

## Field Schema

Each field in your extraction schema defines:

```json
{
  "schema_fields": [
    {
      "name": "product_title",
      "field_type": "string",
      "selector": "h1",
      "attribute": "text",
      "required": true
    },
    {
      "name": "price",
      "field_type": "number",
      "selector": ".price_color",
      "required": true
    },
    {
      "name": "availability",
      "field_type": "string",
      "selector": ".availability",
      "required": false
    },
    {
      "name": "image_url",
      "field_type": "string",
      "selector": ".thumbnail img",
      "attribute": "src"
    }
  ]
}
```

## Custom CSS Selectors

Provide precise CSS selectors to target specific elements:

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Custom selectors",
    "urls": ["https://example.com/products"],
    "schema_fields": [
      {"name": "title", "field_type": "string", "selector": "h2.product-title"},
      {"name": "price", "field_type": "number", "selector": "span.price"}
    ],
    "selectors_map": {
      "container": "div.product-grid > article",
      "next_page": "a.pagination-next"
    }
  }'
```

## Fetch Strategy

Control how the page is loaded:

| Strategy | Description |
|----------|-------------|
| `httpx_smart` | Fast HTTP-only extraction (no JS rendering) |
| `playwright_full` | Full browser rendering with JavaScript |
| `hybrid` | Try HTTPX first, fall back to browser if needed |

## Next Steps

- Set up recurring jobs in Tutorial 4
- Configure anti-bot in Tutorial 5
