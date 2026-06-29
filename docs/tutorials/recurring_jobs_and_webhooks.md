# Tutorial 4: Recurring Jobs and Webhooks

Automate periodic extraction and get notified on completion.

## Scheduled Jobs

Create a job that runs on a cron schedule:

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily price monitoring",
    "mode": "scheduled",
    "urls": ["https://example.com/products"],
    "cron": "0 6 * * *",
    "schema_fields": [
      {"name": "title", "field_type": "string"},
      {"name": "price", "field_type": "number"}
    ]
  }'
```

### Cron Format

The cron expression uses standard 5-field format: `minute hour day month weekday`

Examples:
- `0 */6 * * *` — Every 6 hours
- `0 0 * * 1` — Every Monday at midnight
- `*/15 * * * *` — Every 15 minutes

## Webhooks on Completion

Configure a webhook to receive job results automatically:

```bash
curl -X POST http://localhost:8000/api/jobs/{job_id}/webhook \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://my-server.com/webhooks/dataforge",
    "events": ["completed", "failed"],
    "format": "json",
    "headers": {
      "X-Signature": "my-secret-key"
    }
  }'
```

### Webhook Payload

When the job completes, DataForge sends:

```json
{
  "event": "completed",
  "job_id": "abc-123",
  "status": "completed",
  "total_records": 150,
  "completed_at": "2026-06-29T12:00:00Z",
  "results_url": "http://localhost:8000/api/jobs/abc-123/results"
}
```

## Managing Schedules

List all active schedules:

```bash
curl -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  http://localhost:8000/api/schedules
```

Remove a schedule:

```bash
curl -X DELETE -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  http://localhost:8000/api/schedules/{id}
```

## Next Steps

- Configure anti-bot and proxies in Tutorial 5
