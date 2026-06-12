# DataForge Scraper — Extraction Depth Design Review

Date: 2026-06-13
Commit: `7d47045`
Scope: Planning and design review for Prompt 11 extraction depth features. No implementation changes.

---

## 1. What Exists

### Pagination Detection (`backend/app/url_analyzer.py`)

- `_detect_pagination_signals(url)` — detects page/offset/limit query parameters and path-based pagination
- `_has_infinite_scroll_keywords(url)` — keyword heuristic for infinite-scroll/load-more patterns
- `PAGINATION_PAGE`, `INFINITE_SCROLL_PAGE`, `LOAD_MORE_PAGE` classification types
- 53 tests covering pagination signal detection

### Pagination Configuration

- `WorkflowPaginationConfig` model: `enabled`, `strategy` (next_button, page_number, url_pattern, infinite_scroll), `max_pages` (1-100), `stop_condition`, `selector`
- `Job.pagination` boolean field with `max_pages` (1-100)
- SQLite/Postgres persistence of pagination fields

### Network Capture (`backend/app/browser_network_capture.py`)

- Browser network request/response interception
- JSON response detection and candidate extraction
- Pagination-only payload filtering
- Sensitive header redaction

### Domain Intelligence (`backend/app/domain_intelligence.py`)

- `DomainIntelligence.infinite_scroll_required` tracking
- Telemetry-based domain learning

### HTML Analysis (`backend/app/html_utils.py`)

- Infinite scroll detection from DOM signals
- Sets `infinite_scroll_required` on domain intelligence

### Workflow Runner (`backend/app/services/workflow_runner.py`)

- Snapshot-based field detection from HTML
- Bounded step execution with timeline
- Friendly failure messages with `failure_type`, `user_message`, `recommended_action`
- Sensitive value redaction
- Sample rows output from preview

### Schema / Data Model

- `SchemaField` model with types: string, integer, float, boolean, email, url, phone, location, date, list_string, currency, percentage, code, rating, number
- `RESERVED_FIELD_NAMES` set for system-injected fields
- `FilterRule` model for post-processing filters
- `quality_report: dict` on Job model

### Data Cleaning (Minimal)

- `deduplicate` and `deduplicate_field` on Job model
- `min_record_score` threshold
- No dedicated cleaning module yet

---

## 2. What Is Missing

### Pagination Execution
- Detection exists; live Playwright pagination execution does not
- No next-button clicker, page-number iterator, or URL pattern follower
- No duplicate-page detection for stop condition

### Infinite Scroll Execution
- Detection keyword heuristic exists; no bounded scroll loop
- No scroll-until-no-new-records logic
- No scroll timeout

### Load More Execution
- Detection keyword list includes "load_more"; no click-until-gone loop
- No max-clicks safety

### Network/API Extraction
- Capture infrastructure exists; no user-facing toggle
- No comparison mode (DOM vs network JSON)
- No source selector UI

### Schema Builder
- `SchemaField` model exists for job creation
- No UI schema builder (field type picker, sample preview)
- No schema discovery from page analysis

### Data Quality Engine
- No dedicated cleaning module
- No validation rules per field type
- No quality scoring heuristic beyond `min_record_score`
- No duplicate detection beyond boolean flag
- No data normalization (currency, date, URL, whitespace)

### Failure Explanations
- Workflow runner has `failure_type` and `recommended_action`
- No centralized failure classifier
- No mapping from error signals to user-facing explanations
- Failure types needed: `login_required`, `session_expired`, `session_url`, `selector_not_found`, `blocked_or_challenge`, `timeout`

### Screenshots
- Workflow runner returns `screenshot: null`
- No screenshot capture during browser execution

---

## 3. Recommended Architecture

```
                          ┌──────────────────────┐
                          │   Extraction Job     │
                          │   (or Workflow Run)  │
                          └──────────┬───────────┘
                                     │
            ┌────────────────────────┼────────────────────────┐
            │                        │                        │
     ┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
     │  Pagination  │         │  Network    │         │  DOM        │
     │  Service     │         │  Capture    │         │  Extraction │
     │              │         │  Service    │         │             │
     │ - next_btn   │         │             │         │ - selectors │
     │ - page_num   │         │ - JSON      │         │ - tables   │
     │ - url_param  │         │   detection │         │ - text     │
     │ - scroll     │         │ - redaction │         │             │
     │ - load_more  │         │             │         │             │
     └──────┬───────┘         └──────┬───────┘         └──────┬───────┘
            │                        │                        │
            └────────────────────────┼────────────────────────┘
                                     │
                          ┌──────────▼───────────┐
                          │   Source Selector    │
                          │   (user preference)  │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │   Data Quality       │
                          │   Pipeline           │
                          │                      │
                          │ - Clean (normalize)  │
                          │ - Validate (schema)  │
                          │ - Deduplicate        │
                          │ - Score (quality)    │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │   Results / Export   │
                          └──────────────────────┘
```

---

## 4. Do-Not-Do Warnings

- Do not implement unbounded pagination/scrolling (always enforce max_pages, max_records, timeout)
- Do not capture Authorization headers or cookies in network extraction
- Do not log raw extracted data in audit logs
- Do not silently discard invalid records without reporting them
- Do not implement CAPTCHA bypass or anti-bot behavior during pagination
