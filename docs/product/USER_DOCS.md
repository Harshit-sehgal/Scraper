# User Docs (E4.2)

Five short pages covering the full beta flow. Start with the
Quickstart; each page links to the API reference (`docs/API.md`) for
details.

| Page | Covers |
|---|---|
| [Quickstart](USER_DOCS.md#quickstart) | Signup, first extraction in 5 steps, limits |
| [Extraction guide](EXTRACTION_QUICKSTART.md) | Schema definition, preview, create, schedule |
| [API keys](API_KEYS_GUIDE.md) | Create, use, rotate, revoke `dfk_` keys |
| [Exports](EXPORTS_GUIDE.md) | CSV / JSON / Excel download and batch export |
| [Scheduled jobs](SCHEDULED_JOBS_GUIDE.md) | Cron schedules, change tracking, pause/resume |

## Quickstart

1. **Create an account** — landing page → "Create your account"
   (`POST /api/saas/signup`). You land in the app and are asked to
   accept the current AUP before doing protected actions.
2. **Get an API key** — *API keys* tab → create a project key
   (`POST /api/saas/projects/{project_id}/keys`). Keys look like
   `dfk_...`; the raw key is shown exactly once, so copy it
   immediately.
3. **Analyze a page** — paste a catalog URL into *New job*; the URL
   safety gate rejects private hosts, `file://`, and unsafe schemes.
4. **Preview then run** — define fields (or auto-detect), preview a
   sample, then create the workflow and run it. Results land in the
   job's result view.
5. **Schedule it** — create a scheduled job with a 5-field cron
   expression; run-to-run changes are listed per job.

Plan limits (jobs, fetches, scheduled jobs, API requests) are enforced
per month per tier and return HTTP 429 when exhausted — upgrade or
wait for the next cycle. See `docs/SAAS_MODEL.md` for the tier table.

## Support

- API reference: `docs/API.md`
- Limits and billing: `docs/SAAS_MODEL.md`
- Legal pages are served by the app at `/legal/terms`,
  `/legal/privacy`, `/legal/aup`.
