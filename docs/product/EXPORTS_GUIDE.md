# Exports (E4.2)

Download job results as CSV, JSON, or Excel. Exports are project-
scoped like every other resource; a user can only export results from
jobs they can see.

## Single-job export

```bash
curl -X GET http://localhost:8000/api/jobs/{job_id}/export/csv \
  -H "Authorization: Bearer $DATAFORGE_API_KEY"
```

Formats:

| Format | Endpoint | Notes |
|---|---|---|
| CSV | `/api/jobs/{job_id}/export/csv` | UTF-8, header row from schema |
| JSON | `/api/jobs/{job_id}/export/json` | array of records |
| Excel | `/api/jobs/{job_id}/export/excel` | single sheet, no macros |

## Batch export

```bash
curl -X POST http://localhost:8000/api/exports/batch \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"job_ids": ["job_1", "job_2"], "format": "csv"}'
```

Returns a packaged file served from `GET /api/download/{filename}`.

## Limits

- Export counts against the tier's export/quota allowance; exhausted
  plans return HTTP 429.
- Exports are tenant-isolated: requesting another project's job
  returns 404 (not 403), so existence is not leaked.
- Deleted jobs' exports are removed by retention; GDPR erasure also
  deletes the user's exports.
