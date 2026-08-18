# Tutorial 2: Pagination and Infinite Scroll

Learn how DataForge handles multi-page and dynamically-loading content.

## Pagination Strategies

DataForge supports five pagination strategies:

| Strategy | Description |
|----------|-------------|
| `next_button` | Clicks a "Next" button/link |
| `page_number` | Iterates through numbered page links |
| `url_pattern` | Follows URL patterns (e.g., `page=1`, `page=2`) |
| `infinite_scroll` | Scrolls down to trigger dynamic content loading |
| `load_more` | Clicks a "Load More" button |

## Automatic Detection

DataForge automatically detects pagination. You can override it:

```json
{
  "pagination": {
    "strategy": "next_button",
    "selector": ".pagination .next a",
    "max_pages": 10,
    "max_records": 500
  }
}
```

## Configuring Pagination

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Paginated extraction",
    "mode": "manual",
    "urls": ["https://books.toscrape.com/catalogue/page-1.html"],
    "pagination": {
      "strategy": "url_pattern",
      "pattern": "page-{page}.html",
      "start": 1,
      "end": 5
    }
  }'
```

## Infinite Scroll

For JavaScript-driven infinite scroll pages:

```json
{
  "pagination": {
    "strategy": "infinite_scroll",
    "scroll_attempts": 20,
    "scroll_delay_ms": 1000,
    "max_records": 200
  }
}
```

## Next Steps

- Learn custom selectors in Tutorial 3
- Set up recurring jobs in Tutorial 4
