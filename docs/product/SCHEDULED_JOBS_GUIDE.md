# Scheduled Jobs (E4.2)

Run extraction on a schedule and track what changed between runs.
Requires AUP acceptance; roles ADMIN or OPERATOR.

## Create

```bash
curl -X POST http://localhost:8000/api/scheduled-jobs \
  -H "Authorization: Bearer $DATAFORGE_OPERATOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://books.toscrape.com/"],
    "cron_expression": "0 6 * * *",
    "frequency": "daily"
  }'
```

- `cron_expression` (standard 5-field cron: minute hour dom month dow)
  takes precedence over `frequency` (`hourly` | `daily` | `weekly`)
  when computing next-run times.
- Every URL passes the same safety validation as one-off jobs.
- Invalid cron expressions are rejected with 400 before the job is
  stored.

## Track changes

```bash
curl -X GET http://localhost:8000/api/scheduled-jobs/{job_id}/changes \
  -H "Authorization: Bearer $DATAFORGE_OPERATOR_API_KEY"
```

Lists the differences between the last two runs (new records, removed
records, field-value changes) so you can act on catalog drift without
re-downloading everything.

## Manage

| Action | Endpoint |
|---|---|
| List | `GET /api/scheduled-jobs` |
| Get | `GET /api/scheduled-jobs/{job_id}` |
| Update | `PUT /api/scheduled-jobs/{job_id}` |
| Delete | `DELETE /api/scheduled-jobs/{job_id}` |

Pausing: set the cron expression to a far-future schedule or delete
the job; records and change history stay visible.

## Limits

Scheduled-job creation counts against the tier's monthly scheduled-job
quota; exhausted plans return HTTP 429. See `docs/SAAS_MODEL.md`.
