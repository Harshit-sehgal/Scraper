# DataForge Scraper — Extraction Depth

Date: 2026-06-13
Commit: `7d47045`

Support for real-world website patterns: pagination, infinite scroll, load-more, and network/API-backed extraction.

---

## 1. Pagination

### Detection (Implemented)

The URL analyzer (`backend/app/url_analyzer.py`) detects pagination signals:

- **Query parameters:** `page`, `offset`, `limit`, `p`, `pg`
- **Path patterns:** `/page/2`, `/search?page=3`
- **Confidence scoring:** higher when multiple signals concur

### Configuration

```json
{
  "pagination_config": {
    "enabled": true,
    "strategy": "next_button",
    "max_pages": 10,
    "stop_condition": "no_more_records",
    "selector": "a.next, a.pagination-next"
  }
}
```

### Supported Strategies

| Strategy | Description | Implementation |
|----------|-------------|---------------|
| `next_button` | Click "Next" / ">" button | Detection exists; execution pending |
| `page_number` | Follow numbered page links | Detection exists; execution pending |
| `url_pattern` | Replace `?page=N` in URL | Detection exists; execution pending |
| `infinite_scroll` | Scroll to load more | Detection exists; execution pending |

### Safety Limits

- `max_pages`: 1–100 (hard cap, configurable default 10)
- Stop conditions: `no_more_records`, `duplicate_threshold`, `custom`
- Per-page delay: configurable (default 1 second)

---

## 2. Infinite Scroll

### Detection (Implemented)

Keyword heuristics in URL analyzer detect infinite-scroll patterns:
- URL contains: `infinite`, `scroll`, `lazy`, `load-more`, `feed`
- Domain intelligence learns `infinite_scroll_required` from prior runs

### Execution (Pending)

Planned behavior:
1. Scroll to page bottom.
2. Wait for network idle or new content.
3. Extract new records.
4. Repeat until: max records reached, no new records, or timeout.
5. Hard limit: N scroll iterations (configurable).

---

## 3. Load More

### Detection (Implemented)

Same keyword heuristic detects load-more buttons:
- Keywords: `load_more`, `load-more`, `show_more`, `view_more`
- URL path patterns

### Execution (Pending)

Planned behavior:
1. Find and click "Load More" button.
2. Wait for new content to load.
3. Extract new records.
4. Repeat until: button absent, max clicks, no new records, or timeout.

---

## 4. Network / API Extraction

### Detection (Implemented in `browser_network_capture.py`)

- Intercepts browser network requests and responses.
- Detects structured JSON responses from XHR/fetch calls.
- Returns candidate endpoints with record count and confidence.
- Skips pagination-only payloads (smaller result sets, duplicates).

### User Choice (Future)

Users should be able to choose:
- **DOM extraction:** Scrape rendered HTML with CSS selectors.
- **Network JSON extraction:** Parse public API responses directly.
- **Compare both:** Run both and recommend the cleaner source.

### Security

- Authorization headers, cookies, tokens are **never captured or logged**.
- Response bodies are redacted of sensitive fields before storage.
- Only public JSON responses are eligible (no internal APIs).

---

## 5. Extraction Source Selector (Future)

Users can specify the preferred extraction source:

| Source | When to use | Pros | Cons |
|--------|-------------|------|------|
| `rendered_dom` | Static pages, server-rendered content | Most reliable | May miss client-loaded data |
| `visible_text` | Simple text extraction | Fast | Loses structure |
| `tables` | Tabular data | Clean row/column structure | Only works for `<table>` |
| `network_json` | SPA pages with public APIs | Fast, structured | API may change or be private |
| `workflow_result` | Workflow replay pages | Targeted extraction | Requires workflow setup |
| `custom_selector` | Power users | Full control | Requires technical knowledge |

---

## 6. Screenshots and Timeline

### Timeline (Partially Implemented)

The workflow runner records a step timeline:
```json
{
  "steps": [
    {"step": 1, "action": "goto", "selector": "", "duration_ms": 1200, "success": true},
    {"step": 2, "action": "fill", "selector": "input[name='q']", "duration_ms": 300, "success": true},
    {"step": 3, "action": "click", "selector": "button[type='submit']", "duration_ms": 800, "success": true}
  ],
  "total_duration_ms": 2300,
  "result_url": "https://example.com/search?q=laptops"
}
```

### Screenshots (Pending)

- Screenshot capture on key steps (page load, before/after actions, final result).
- Redacted to avoid capturing sensitive content.
- Configurable retention period for screenshot storage.

---

## 7. Tests

Existing test coverage:
- `backend/tests/test_url_analyzer.py` — pagination signal detection, infinite scroll keywords
- `backend/tests/test_workflow.py` — pagination config model validation
- `backend/tests/test_paginated_results.py` — paginated result retrieval
- `backend/tests/test_list_jobs_pagination.py` — cursor-based job listing pagination

Tests needed for execution:
- Pagination: next-button clicker against local fixture pages
- Infinite scroll: scroll loop against fixture pages with scroll-loaded content
- Load more: click loop against fixture pages with load-more buttons
- Network JSON: detection accuracy against fixture pages with XHR/fetch
- Source selector: recommendation logic against mixed fixture pages
