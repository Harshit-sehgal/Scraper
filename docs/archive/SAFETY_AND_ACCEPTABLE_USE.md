# Safety And Acceptable Use

DataForge Scraper is for lawful extraction from accessible web pages
and user-authorized workflows. It must not be used to bypass access
controls or extract private data without authorization.

## Allowed Uses

- Extract structured data from public, lawfully accessible pages.
- Run user-authorized authenticated sessions through domain-scoped
  profiles when the user has the right to access the site.
- Respect configured crawl policies, rate limits, domain denylist, and
  target-site restrictions.
- Use preview/dry-run behavior to verify extraction before full jobs.
- Export only data the authenticated tenant/user/project is allowed to
  access.

## Disallowed Uses

- CAPTCHA bypass
- anti-bot bypass
- paywall bypass
- login bypass
- session ID brute force
- token forging
- credential stealing
- raw cookie dumping
- scraping private or unauthorized systems
- scraping internal/private networks
- ignoring configured crawl or domain policy

## Current Safety Controls

- URL safety rejects unsupported schemes, private/internal IPs,
  metadata endpoints, internal TLDs, and disallowed ports.
- Admin domain denylist is consulted by URL safety.
- Crawl policy tracks per-domain concurrency, delays, retries,
  cooldowns, and best-effort robots awareness.
- API auth is centralized through `app.utils.rbac.resolve_auth_context`.
- Tenant-sensitive routes should enforce owner/org/project checks.
- Audit logger records security-relevant events.
- Validation scripts redact common secret patterns.

## Required Before Production

- Complete dependency vulnerability triage.
- Prove backup/restore and migration rollback drills.
- Verify full audit coverage for exports, deletes, auth failures,
  tenant denials, quota denials, and workflow/profile use.
- Define data retention and deletion policies.
- Keep all workflow/session features within user-authorized normal
  browser actions only.
