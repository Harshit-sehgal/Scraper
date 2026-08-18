# API Keys (E4.2)

Project-scoped keys for programmatic access. Keys are created in the
app under *API keys*, or via the SaaS endpoints below.

## Create

```bash
curl -X POST http://localhost:8000/api/saas/projects/{project_id}/keys \
  -H "Authorization: Bearer $DATAFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-export", "scope": "write"}'
```

- Returns the raw key **once** — a `dfk_`-prefixed string with 32
  bytes of randomness (256 bits). Copy it immediately; it is never
  stored or shown again (only its SHA-256 hash is kept).
- Scopes: `read` (jobs, results, exports) and `write` (create jobs,
  run workflows).
- List keys: `GET /api/saas/projects/{project_id}/keys`
- Revoke: `DELETE /api/saas/projects/{project_id}/keys/{key_id}` —
  revocation is immediate; a revoked key is rejected by every route.

## Use

```bash
curl -X GET http://localhost:8000/api/jobs \
  -H "Authorization: Bearer dfk_..."            # or
  -H "x-api-key: dfk_..."
```

Keys are project-scoped: they only see jobs, workflows, and exports
of their own project. Users can only access projects of organizations
they are members of.

## Rotation

1. Create a new key with the same name.
2. Switch your scripts to the new key.
3. Revoke the old key and verify a request now fails with 401.

## Hygiene

- Never commit raw keys; use environment variables or a secret
  manager.
- Prefer short-lived keys for CI jobs; revoke them when the pipeline
  is retired.
- Audit log records key creation and revocation (actor, project,
  timestamp).
