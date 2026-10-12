# Extraction Quickstart (E3.4)

Extract a product catalog from a public page in five steps: analyze,
define a schema, preview, create, and schedule. All endpoints are
covered by `docs/API.md`; this is the happy path for use case 1
(product catalog monitoring).

All requests use `Authorization: Bearer <API_KEY>`; role requirements
are listed per endpoint.

## 1. Analyze a catalog page

```bash
curl -X POST http://localhost:8000/api/workflow-drafts/from-url-analysis \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://books.toscrape.com/"}'
```

Returns a draft with `recommended_start_urls` and detected structure.
The URL safety gate rejects private/internal hosts, file://, and
unsafe schemes.

## 2. Define the schema

Detect fields from the page (POST to `/api/workflow-drafts/{draft_id}/detect-fields`
with an optional `html_snapshot`), or define them manually as an
`extraction_schema` — a list of `SchemaField` objects:

```json
[
  {"name": "title", "field_type": "string", "required": true},
  {"name": "price", "field_type": "currency", "required": false},
  {"name": "rating", "field_type": "string", "required": false}
]
```

Field types: `string`, `number`, `currency`, `date`, `url`, `email`,
`phone`, `boolean`. Mark only the identifier fields `required` — the
extractor uses them as record keys.

## 3. Preview before you commit

```bash
curl -X POST http://localhost:8000/api/workflows/{workflow_id}/preview \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"html_snapshot": "", "sample_limit": 5}'
```

Returns a sample of extracted records so you can validate the schema
against the live page before running at scale. `sample_limit` is 1–25.

## 4. Create the workflow

```bash
curl -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Books catalog watch",
    "start_url": "https://books.toscrape.com/",
    "mode": "workflow_replay",
    "extraction_schema": [
      {"name": "title", "field_type": "string", "required": true},
      {"name": "price", "field_type": "currency", "required": false}
    ],
    "pagination_config": {"max_pages": 10}
  }'
```

- `max_pages` per pagination config: 1–100, default 10.
- Run immediately: `POST /api/workflows/{workflow_id}/run` (202).
- List runs: `GET /api/workflows/{workflow_id}/runs`.

## 5. Schedule it

Scheduled jobs run on cron and compare each run against the previous
one (`GET /api/scheduled/{job_id}/changes` shows what changed):

```bash
curl -X POST 'http://localhost:8000/api/scheduled?name=Books%20monitor&job_name=Books%20daily&frequency=daily&urls=https%3A%2F%2Fbooks.toscrape.com%2F' \
  -H "Authorization: Bearer $DATAFORGE_OPERATOR_API_KEY" \
  -H "Accept: application/json"
```

- `cron_expression` (5-field cron) takes precedence over `frequency`
  (`hourly` | `daily` | `weekly`).
- Requires AUP acceptance; authenticated tenant users can manage their own schedule.

## Limits and billing

- Plan limits (fetches, jobs, exports) are enforced with HTTP 429 when
  a quota is exhausted; see `docs/SAAS_MODEL.md`.
- Entitlements are managed through Dodo Payments; local
  reconciliation: `python3 scripts/reconcile_billing.py`.

## Also in this directory

- `STAGING_RUNBOOK.md` — standing up a staging deployment
- `USER_DOCS.md` — the user-facing docs set (E4.2)
