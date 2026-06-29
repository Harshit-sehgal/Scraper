# DataForge Scraper — Improvement Roadmap

Target: **80+ in every scraper-evaluation sector** (Extraction Depth, Extraction Reliability, Anti-Bot Capability, Feature Completeness, Benchmark / Test Rigor, Production Readiness, Data Quality, Developer Experience, Compliance, Observability).

Current weighted scraper score: **41/100**

---

## 1. Extraction Reliability (30 → 80)

The biggest drag — the extraction pipeline has never been CI-tested with a real browser. Everything is mocked or regex-offline.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Add `test_pagination_executor.py`** with 20+ tests for all 5 async pagination strategies (next_button, page_number, url_pattern, infinite_scroll, load_more) against real Playwright-driven HTML fixtures | 3 days | P0 |
| 2 | **Add 30 unmocked extraction integration tests** — serve real HTML pages via `pytest-httpserver` or local HTTP server, run `scrape_url` with `PLAYWRIGHT_FULL` strategy, assert extracted records match expected output. Cover: JS-rendered content, lazy-loaded images, SPAs, iframes, shadow DOM | 5 days | P0 |
| 3 | **Convert `@pytest.mark.browser` gated tests to CI-default** — install Playwright browsers in CI, make the 16 benchmark enforcement tests part of `--quick` or `--full` validation. Currently they are skipped in normal CI | 1 day | P0 |
| 4 | **Add end-to-end job lifecycle test** — submit URL → job created → worker picks up → extraction runs → results stored → results retrieved. Single test that exercises every layer unmocked | 2 days | P0 |
| 5 | **Add sync pagination implementations** — sync versions of all 5 strategies are currently stubs returning empty results. This means the HTTPX-only path has no pagination. Implementing them closes a silent failure | 2 days | P1 |
| 6 | **Add extraction response validation** — assert that extraction results conform to the requested schema types (e.g., numeric fields are actually numbers, dates are valid). Currently no schema enforcement after extraction | 1 day | P1 |
| 7 | **Add browser crash recovery test** — kill browser mid-extraction, verify worker recovers gracefully and requeues the job | 2 days | P1 |
| 8 | **Add extraction timeout enforcement test** — submit a page that never finishes loading, verify job times out with a clean failure and no leaked browser contexts | 1 day | P1 |
| 9 | **Add resource blocking test** — verify blocking ads, tracking scripts, fonts, and images does not break extraction of core content | 1 day | P1 |
| 10 | **Add multi-format extraction test** — single page with JSON-LD, microdata, RDFa embedded simultaneously, verify all three are discovered and the best-scoring source wins | 1 day | P1 |
| 11 | **Add encoding detection test** — pages in UTF-8, ISO-8859-1, Shift-JIS, verify charset detection and clean text extraction | 1 day | P2 |
| 12 | **Add concurrent extraction test** — 10+ unique URLs submitted simultaneously, verify no cross-contamination (page A's data never appears in page B's results) and no resource deadlocks | 2 days | P1 |
| 13 | **Add concurrent same-URL test** — 5+ identical URLs submitted together, verify result deduplication, cache hits, and no duplicate workers for the same URL | 1 day | P2 |
| 14 | **Add extraction cancellation mid-flight test** — cancel a running job, verify partial results are clean, browser context is released, worker returns to idle | 1 day | P1 |
| 15 | **Add rate-limit handling test** — serve HTTP 429 with Retry-After header, verify worker backs off, retries, and succeeds on the retry | 1 day | P2 |
| 16 | **Add empty/null field handling test** — pages where some expected fields are missing, verify extraction returns nulls (not missing keys) and the cascade continues to lower layers | 1 day | P2 |
| 17 | **Add zero-content page test** — page with no extractable records at all (just navigation, footer, whitespace), verify empty result set with correct classification | 1 day | P2 |
| 18 | **Add domain-redirect test** — URL that HTTP-redirects to a completely different domain, verify the extraction follows the redirect and extracts from the final domain | 1 day | P2 |
| 19 | **Add binary-page rejection test** — URL serving a PDF or image instead of HTML, verify extraction classifies as unsupported format, returns zero records cleanly | 1 day | P2 |
| 20 | **Add infinite-scroll-ceiling test** — page whose content never stops growing, verify the max-pages / max-records / max-timeout ceiling is enforced gracefully | 2 days | P1 |
| 21 | **Add very large page stress test** — 500KB+ HTML page with deeply nested DOM (5000+ elements), verify extraction completes within bounded time and memory | 2 days | P2 |
| 22 | **Add redirect chain test** — URL that goes through 5+ HTTP redirects before landing, verify final page is extracted (not the redirect chain) and hop count is reported | 1 day | P2 |
| 23 | **Add continuous-DOM-modification test** — page where JS keeps modifying DOM after load (React re-renders, timers), verify extraction waits for stabilization and captures final state | 2 days | P1 |
| 24 | **Add automation-detection test** — page that checks `navigator.webdriver`, `navigator.plugins`, `chrome.runtime`, and other detection vectors, verify Playwright stealth evades them | 2 days | P1 |
| 25 | **Add SSRF-protocol-rejection test** — URLs with `file://`, `ftp://`, `dict://`, `gopher://` schemes, verify SSRF guard rejects them before any network call | 1 day | P1 |
| 26 | **Add AMP-page extraction test** — Accelerated Mobile Pages with limited JS, verify extraction works in AMP rendering mode | 1 day | P2 |
| 27 | **Add cross-browser extraction parity test** — run the same extraction against Chromium and Firefox (if supported), assert result equivalence | 2 days | P2 |
| 28 | **Add extraction of pages with noscript/fallback content** — pages that require JS but have `<noscript>` fallback, verify graceful degradation | 1 day | P2 |
| 29 | **Add slow-network test** — simulate slow 3G network conditions (e.g., via `page.route` delay), verify extraction waits for content but eventually times out gracefully | 1 day | P2 |
| 30 | **Add dynamic-class-name test** — pages where CSS class names are randomized per visit (common in Tailwind/MUI build systems), verify extraction uses semantic selectors not fragile class names | 1 day | P2 |
| 31 | **Add click-to-reveal content test** — page with "Show more" buttons, accordions, or "Read more" links that reveal extractable content on click, verify extraction clicks and captures hidden content | 2 days | P1 |
| 32 | **Add tab-content extraction test** — page with tabbed interface where each tab loads content via XHR/fetch, verify extraction clicks all tabs and merges content from all panels | 2 days | P1 |
| 33 | **Add modal/dialog content extraction test** — page where key content is in a modal opened by button click, verify extraction triggers the modal and captures its content | 1 day | P2 |
| 34 | **Add hover-triggered content test** — page where content appears on mouse hover (tooltips, dropdown menus), verify Playwright hover action triggers and content is captured | 1 day | P2 |
| 35 | **Add IntersectionObserver content test** — page that loads content progressively as user scrolls (using IntersectionObserver API), verify infinite scroll strategy captures all content | 2 days | P1 |
| 36 | **Add WebSocket-pushed content test** — page that receives real-time updates via WebSocket and renders them into DOM, verify extraction captures final state after a stabilization delay | 2 days | P1 |
| 37 | **Add Server-Sent Events content test** — page using EventSource to stream content updates, verify similar stabilization and capture | 1 day | P2 |
| 38 | **Add ServiceWorker-cached content test** — page using Service Workers to serve cached/offline content, verify extraction gets the correct version | 1 day | P2 |
| 39 | **Add expired-SSL extraction test** — page with expired TLS certificate, verify SSRF guard blocks it, extraction fails cleanly with SSL error classification | 1 day | P2 |
| 40 | **Add self-signed-certificate test** — page with self-signed cert, verify SSRF guard blocks it, extraction returns auth_required or ssl_error classification | 1 day | P2 |
| 41 | **Add A/B-test content test** — page that returns different HTML on each visit (random bucket assignment), verify extraction captures whichever variant is served and does not assume static structure | 1 day | P2 |
| 42 | **Add JavaScript-error-on-load test** — page that throws unhandled JS exceptions during load, verify extraction completes despite errors (Playwright should catch but not crash) | 1 day | P2 |
| 43 | **Add malformed-HTML recovery test** — page with unclosed tags, duplicate IDs, invalid nesting, verify extraction degrades gracefully and extracts what it can | 1 day | P2 |
| 44 | **Add authenticated-page extraction test** — page behind login with session cookie provided via job config, verify cookie injection, authenticated content extraction, and session expiry handling | 2 days | P1 |
| 45 | **Add geo-restricted content test** — page that returns different content based on geographic location, verify proxy geolocation targeting selects the correct regional content | 2 days | P2 |
| 46 | **Add user-triggered-content test** — pages where content loads only after a specific user action beyond scroll/click (drag, pinch, rotate, swipe), verify extraction detects unsupported interaction and falls back gracefully | 1 day | P2 |
| 47 | **Add beforeunload-dialog test** — page that triggers a "Are you sure you want to leave?" dialog on navigation, verify Playwright dismisses it and extraction continues | 1 day | P2 |
| 48 | **Add extremely-deep-DOM test** — page with 10,000+ nested DOM elements, verify extraction does not stack-overflow or exhaust memory | 2 days | P2 |
| 49 | **Add partial-results-on-crash test** — worker kills browser mid-extraction after 70% of content extracted, verify partial results are persisted with a `partial=true` flag | 2 days | P1 |

**Gate: 50+ tests across all extraction layers, running in CI with a real browser, covering pagination, JS rendering, hybrid fallback, edge cases, and recovery scenarios.**

---

## 2. Feature Completeness (25 → 80)

The project is missing basics that any production scraper user expects.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Add custom headers/cookies API** — `PATCH /api/jobs/{id}/headers` and per-job header store. This is the #1 blocker for real-world use (sites that need specific Accept-Language, Referer, or auth cookies) | 2 days | P0 |
| 2 | **Add webhook/callback on job completion** — `POST /api/jobs/{id}/webhook` endpoint, worker fires webhook on completion/failure with result summary. Essential for integration | 2 days | P0 |
| 3 | **Add cron scheduling / recurring jobs** — `POST /api/jobs/schedule` with cron expression, `GET /api/schedules` to list, worker picks up scheduled jobs. Recurring extraction is table stakes | 3 days | P0 |
| 4 | **Add user-configurable extraction params** — allow users to specify CSS selectors, wait time, scroll depth, pagination limit, fetch strategy per job. Currently everything is automatic with no user override | 3 days | P0 |
| 5 | **Add binary download support** — `scrape_url(extract_binary=True)` that saves PDF, ZIP, image files to storage and returns a download URL. Currently text-only | 2 days | P1 |
| 6 | **Add authenticated session support** — login form detection + credential injection + cookie persistence per user. At minimum: POST-based login with session cookie capture and replay | 4 days | P1 |
| 7 | **Add export integrations** — export results to S3, GCS, or webhook target in JSON/CSV/Parquet. Currently results are only accessible via API | 3 days | P1 |
| 8 | **Add general form filling** — extend `search_form_recovery` into a general form engine that can fill multi-field forms, select dropdowns, check boxes, and submit with configurable field mappings | 4 days | P1 |
| 9 | **Add job-level rate limiting** — per-user concurrency cap, per-job delay between requests, domain cooldown integration. Currently no protection against a user overwhelming a target | 2 days | P0 |
| 10 | **Add webhook retry with exponential backoff** — if webhook delivery fails, retry 3× with backoff, then mark as failed and surface in job status | 1 day | P1 |
| 11 | **Add result diffing API** — `GET /api/jobs/{id}/diff?compare_to={other_id}` returns added/removed/changed records between two runs. Essential for change detection | 2 days | P1 |
| 12 | **Add extraction templates** — save a set of extraction parameters (schema, strategy, wait conditions) as a reusable template, apply to multiple URL lists | 2 days | P1 |
| 13 | **Add batch URL submission** — CSV/JSON upload of 1000+ URLs as a single job, with progress tracking per URL | 2 days | P1 |
| 14 | **Add result deduplication** — merge identical records across pages within a job, with configurable dedup keys | 1 day | P2 |
| 15 | **Add custom output schema validation** — user defines output field types, extraction validates results against schema and flags mismatches | 1 day | P2 |
| 16 | **Add extraction annotations** — user marks fields as PII (redacted in exports), required (fail if missing), optional (allow null) — per extraction config | 2 days | P2 |
| 17 | **Add data enrichment pipeline** — post-extraction transformation hooks: regex replace, value mapping, field concatenation, unit conversion | 3 days | P2 |
| 18 | **Add export scheduling** — recurring export to S3/email/GCS on a cron schedule (separate from the extraction schedule) | 2 days | P2 |
| 19 | **Add extraction preview / dry-run** — execute extraction on a single URL with current config, return sample results without persisting to job history | 1 day | P1 |
| 20 | **Add API keys per project** — not just the global API key. Each project gets scoped keys with its own rate limits and audit trail | 2 days | P1 |
| 21 | **Add extraction job cloning** — duplicate an existing job's config (schema, strategy, headers, webhook) for use with a different URL list | 1 day | P2 |
| 22 | **Add extraction metrics dashboard** — per-domain success rate, average extraction time, field coverage, cascade layer usage histogram | 3 days | P2 |
| 23 | **Add custom user-agent per job** — allow user to set the User-Agent for their extraction job, with a curated pool of modern browser UAs as presets | 1 day | P2 |
| 24 | **Add WebSocket streaming of extraction results** — push partial results to client as they are extracted, rather than waiting for full job completion | 2 days | P1 |
| 25 | **Add result search/filter/sort API** — `GET /api/jobs/{id}/results?q=keyword&field=price&sort=asc` for querying within extracted data | 2 days | P2 |
| 26 | **Add bulk result delete API** — `DELETE /api/jobs/{id}/results` with optional date range filter for data lifecycle management | 1 day | P2 |
| 27 | **Add Google Sheets / Airtable / Notion export** — one-click push to collaborative workspaces | 2 days | P2 |
| 28 | **Add webhook payload signing** — HMAC-sign webhook payloads so consumers can verify they came from DataForge, not a spoof | 1 day | P1 |
| 29 | **Add RateLimit headers in API responses** — `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` on every API response (RFC 6585) | 1 day | P1 |
| 30 | **Add API usage dashboard per key** — show requests/day, records extracted, failures, average latency per API key | 2 days | P2 |
| 31 | **Add OpenAPI 3.1 spec with request/response examples** — currently the spec exists but lacks examples for every endpoint | 2 days | P2 |
| 32 | **Add Postman collection auto-generated from OpenAPI** — script exports updated collection on every release | 1 day | P2 |
| 33 | **Add screenshot API** — `POST /api/extract/screenshot` renders a URL to a PNG/Screenshot, useful for visual verification and debugging | 1 day | P1 |
| 34 | **Add PDF generation from results** — create a formatted PDF report of extracted data (useful for compliance/audit) | 2 days | P2 |
| 35 | **Add email delivery of results** — on job completion, email a summary + attachment (CSV/PDF) to configured recipients | 2 days | P2 |
| 36 | **Add Slack / Teams / Discord integration** — send extraction notifications (completed, failed, quota warning) to chat channels | 1 day | P2 |
| 37 | **Add templates marketplace** — community-shareable extraction templates with ratings, usage stats, and one-click import | 3 days | P2 |
| 38 | **Add public shareable job link** — `GET /share/{job_token}` renders a read-only view of extraction results without authentication, useful for stakeholders | 1 day | P2 |

**Gate: items 1–4, 9 are P0 (~9 days). Items 6, 7, 19, 24, 33 are P1 (~11 days). Rest is polish.**

---

## 3. Anti-Bot Capability (55 → 80)

The evasion layer is solid but detection-only is a hard ceiling.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Add CAPTCHA solving provider integration** — implement `captcha_solver.py` with 2Captcha/Anti-Captcha adapters. Detect CAPTCHA type → submit to solver → inject token → retry. This alone doubles usefulness | 3 days | P0 |
| 2 | **Add Cloudflare challenge token harvester** — detect Cloudflare JS challenge → extract `cf_clearance` cookie → persist + inject on subsequent requests. The detection code already exists (`anti_bot_engine.py`), just needs the harvesting loop | 2 days | P0 |
| 3 | **Add proxy provider integration** — pluggable proxy backends (BrightData, Oxylabs, Smartproxy, SOCKS5). Currently supports static proxy lists only, no automated rotation from a provider pool | 2 days | P0 |
| 4 | **Add HTTP/2 + TLS fingerprint randomization** — either via `curl_cffi` library or Playwright protocol-level fingerprint overrides. Current evasion is JS-only, does not mask transport-level fingerprints | 3 days | P1 |
| 5 | **Add intelligent retry with backoff and proxy rotation on block** — when `anti_bot_engine` classifies a block, automatically retry with escalated strategy + new proxy + user-agent rotation, up to N attempts. Currently it just records the block and moves on | 2 days | P0 |
| 6 | **Add IP rotation verification** — test that after proxy rotation, the egress IP actually changes. Currently the proxy rotation feeds addresses to Playwright contexts but there's no verification that the proxy is functional or the IP is unique | 1 day | P1 |
| 7 | **Add browser fingerprint rotation** — different canvas fingerprint, audio context fingerprint, font fingerprint per browser context. Currently only WebGL vendor/renderer is randomized | 2 days | P1 |
| 8 | **Add request header randomization** — vary Accept, Accept-Encoding, Accept-Language, Sec-CH-UA headers per request within realistic ranges | 1 day | P2 |
| 9 | **Add viewport rotation** — randomly select from 20 common viewport sizes (mobile + desktop), set corresponding screen dimensions | 1 day | P2 |
| 10 | **Add mouse movement simulation** — before clicking "load more" or pagination buttons, generate realistic mouse tracks (Bezier curves with human acceleration/deceleration) | 2 days | P1 |
| 11 | **Add human-like timing** — randomize delays between all actions (scroll, click, wait) with Gaussian distributions matching human timing data | 1 day | P2 |
| 12 | **Add geolocation spoofing** — set `navigator.geolocation` to a location matching the proxy IP's estimated geography | 1 day | P2 |
| 13 | **Add timezone/locale alignment** — ensure browser timezone, locale, and accept-language header all match the proxy IP's geolocation | 1 day | P2 |
| 14 | **Add WebRTC leak prevention** — disable WebRTC or route it through the configured proxy. Prevent real IP leakage via STUN requests | 1 day | P1 |
| 15 | **Add DNS leak prevention** — route DNS resolution through the proxy (SOCKS5 proxy does this natively; HTTP proxies need explicit `proxy_dns` config) | 1 day | P2 |
| 16 | **Add browser profile persistence** — maintain a consistent fingerprint per domain over time so the site sees the same "returning visitor". Currently each context gets fresh random fingerprints | 2 days | P1 |
| 17 | **Add challenge-solving marketplace** — when automated solving fails, escalate to a human-in-the-loop queue (operator sees a screenshot, solves CAPTCHA, result replayed). Practical for high-value extraction | 3 days | P2 |
| 18 | **Add session persistence between scheduled runs** — reuse cookies and browser profile across recurring jobs to the same domain. Avoids re-authentication on every run | 2 days | P1 |
| 19 | **Add anti-detection profile catalog** — pre-built, tested browser profiles: Chrome 124 Desktop (Windows 11), Chrome Mobile (Pixel 8), Safari (macOS), Firefox (Linux). Each with known-good fingerprint parameters | 2 days | P1 |
| 20 | **Add custom stealth configuration API** — allow users to enable/disable specific evasion features per job (e.g., disable WebGL spoofing if the target site uses WebGL legitimately and the spoof triggers detection) | 2 days | P2 |
| 21 | **Add request-behavior fingerprint randomization** — vary timing patterns, scroll patterns, click patterns across sessions to avoid behavioral fingerprinting | 2 days | P2 |
| 22 | **Add automatic proxy health scoring** — track success rate per proxy IP, evict proxies that consistently get blocked, prefer proxies with higher success rates | 1 day | P1 |
| 23 | **Add adaptive delay based on target response time variance** — measure per-domain response time jitter, set request delays to match natural human browsing variance (+/- 30%) | 1 day | P2 |
| 24 | **Add session diversity rotation** — rotate browser session parameters (viewport, timezone, locale) not just per-domain but also per-session-length to avoid session-length fingerprinting | 1 day | P2 |
| 25 | **Add automatic profile selection per target domain** — maintain a database of known-good fingerprint profiles per domain (e.g., "amazon.com works best with Chrome Desktop + Windows + no WebGL spoofing") | 2 days | P1 |
| 26 | **Add ML-based block prediction** — train a lightweight classifier on response features (status code, response time, page title, DOM structure) to predict block probability before extraction starts | 3 days | P2 |
| 27 | **Add A/B evasion strategy testing per domain** — run two evasion strategies on the same domain, track success rate, learn which wins over time | 2 days | P2 |
| 28 | **Add IP quality scoring** — score each proxy IP on freshness, reputation, datacenter vs residential classification, carrier-grade NAT detection, and historical success rate | 2 days | P1 |
| 29 | **Add residential proxy network integration** — connect to BrightData/Oxylabs residential proxy networks for high-value targets that block datacenter IPs | 2 days | P1 |
| 30 | **Add mobile 4G/5G proxy support** — egress via mobile carrier IP pools for mobile-site extraction and anti-bot evasion | 2 days | P2 |
| 31 | **Add CAPTCHA solving cost tracking** — track per-domain CAPTCHA solve costs, surface in job metrics so users can optimize spend | 1 day | P2 |
| 32 | **Add automatic strategy downgrade** — if a domain never blocks, avoid using expensive residential proxies or CAPTCHA solving on subsequent runs | 2 days | P2 |
| 33 | **Add headless detection test suite** — standalone CI pipeline that verifies DataForge's Playwright profiles are undetectable against known detection methods (https://bot.sannysoft.com, https://arh.antoinevastel.com/bots/) | 2 days | P1 |
| 34 | **Add fingerprint diversity scoring** — measure Shannon entropy of fingerprints across sessions, assert above configurable threshold. Alerts when entropy drops (fingerprints are too similar, risk of correlation) | 1 day | P2 |
| 35 | **Add automated fingerprint refresh** — configurable interval for refreshing browser fingerprints (per-page, per-session, per-hour) to avoid long-session correlation | 1 day | P2 |
| 36 | **Add proxy geolocation consistency** — ensure all requests for a single job come from the same geographic region. Prevents "your IP changed mid-session" detection | 1 day | P2 |
| 37 | **Add cookie jar with expiration-aware eviction** — SQLite-backed cookie store that evicts expired cookies, prioritizes session cookies, and handles SameSite attributes correctly | 1 day | P1 |
| 38 | **Add LocalStorage/sessionStorage persistence** — persist browser storage between navigations within a single extraction, ensuring JS-heavy sites maintain state | 1 day | P2 |
| 39 | **Add ServiceWorker unregister/re-register** — unregister existing ServiceWorkers before extraction to capture fresh server content, not cached responses | 1 day | P2 |
| 40 | **Add advanced WebDriver detection countermeasures** — spoof `navigator.webdriver`, `navigator.chrome`, `chrome.runtime`, `chrome.loadTimes()` to match real browser values | 1 day | P1 |

**Gate: solving integration (CAPTCHA + Cloudflare) plus intelligent retry plus proxy provider integration. Without these three, 70 is the ceiling.**

---

## 4. Benchmark / Test Rigor (40 → 80)

The benchmark corpus is only 14 offline cases, all synthetic HTML, all regex-tested. No real extraction performance data exists.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Add 20 real-world benchmark pages** — capture HTML from real sites (Amazon product page, Twitter profile, HN listing, Wikipedia article, eBay listing, StackOverflow Q&A, etc.), store as fixtures, run Playwright extraction against them, assert expected fields. Must have real DOM complexity, not synthetic | 4 days | P0 |
| 2 | **Add Playwright-driven benchmark suite** — `make benchmark-browser` target that launches Chromium, renders each fixture, runs full extraction cascade (not just regex), measures accuracy, latency, memory. Currently only regex/offline is measured | 3 days | P0 |
| 3 | **Add pagination benchmark** — multi-page extraction test with 3+ pages of paginated content, assert deduplication, ordering, completeness of extracted records across pages. Currently zero pagination tests exist | 2 days | P0 |
| 4 | **Add session expiry / recovery benchmark** — given a session-bound URL fixture, extract → expire session → recover via search form → re-extract. Assert no data loss across the recovery. Currently untested | 2 days | P1 |
| 5 | **Add anti-bot evasion benchmark** — serve a page that mimics Cloudflare / DataDome challenge behavior via middleware, run extraction, assert correct block classification and strategy escalation. Currently anti-bot is entirely untested | 2 days | P1 |
| 6 | **Add benchmark CI gate** — fail CI if aggregate F1 drops below 0.95 on the full benchmark suite (not just the current 0.90 threshold). Tighten over time | 1 day | P1 |
| 7 | **Add memory/leak benchmark** — run 100 extraction iterations sequentially on different URLs, measure RSS growth between first and last, assert no leak. Browser memory leaks are common in Playwright-based scrapers | 2 days | P1 |
| 8 | **Add mobile viewport benchmark** — run extraction suite with mobile viewport (375×812), verify responsive layout extraction quality | 1 day | P2 |
| 9 | **Add SPA benchmark** — React/Angular/Vue-rendered content extraction, verify the extraction waits for framework initialization and client-side render | 2 days | P1 |
| 10 | **Add internationalization benchmark** — non-English pages (Chinese, Arabic, Russian, Hindi), RTL layout, multi-byte encoding, verify field extraction accuracy | 2 days | P2 |
| 11 | **Add large result set benchmark** — page containing 1000+ extractable records, verify extraction completes within reasonable time and all records are captured | 2 days | P2 |
| 12 | **Add benchmark trend tracking** — store historical F1/latency/memory results in `artifacts/benchmarks/trends/`, CI diffs against last 10 runs and alerts on regression beyond 2σ | 2 days | P1 |
| 13 | **Add field-level accuracy breakdown** — per field type (price, date, name, rating, phone, email), report precision/recall separately. Identifies which extraction layers are weak at which field types | 2 days | P2 |
| 14 | **Add cost-per-extraction benchmark** — measure CPU time, peak RSS, number of HTTP requests, cascade layers attempted per extraction. Helps optimize and price | 2 days | P2 |
| 15 | **Add benchmark report visualization** — `scripts/generate_benchmark_dashboard.py` produces an HTML page with charts (F1 trend, latency distribution, field accuracy heatmap) from stored results | 3 days | P2 |
| 16 | **Add A/B benchmark mode** — compare two extraction strategies or cascade configurations on the same corpus, produce a diff report showing which config wins on which page types | 2 days | P1 |
| 17 | **Add lazy-load image benchmark** — pages where content images are lazy-loaded (loading="lazy"), verify Playwright scroll triggers image load and extraction captures image-attached data | 1 day | P2 |
| 18 | **Add iframe content extraction benchmark** — page with same-origin and cross-origin iframes containing extractable data, verify iframe content extraction works | 2 days | P2 |
| 19 | **Add WebSocket-fed content benchmark** — page that streams data via WebSocket and renders it dynamically, verify extraction waits for and captures streamed content | 3 days | P2 |
| 20 | **Add benchmark corpus versioning** — version the fixture HTML files and expected outputs so corpus changes are tracked alongside code, and CI can detect when corpus updates invalidate historical trend data | 1 day | P2 |
| 21 | **Add benchmark regression gate per PR** — on every PR, run a quick subset of the benchmark (~5 key cases), assert F1 does not regress compared to the base branch | 2 days | P1 |
| 22 | **Add warm-vs-cold extraction benchmark** — measure latency difference between first extraction (cold: no cache, cold browser) and repeated URL extraction (warm: in-memory cache, hot browser context) | 1 day | P2 |
| 23 | **Add database-size scalability benchmark** — measure extraction latency against databases with 10, 100, 1000, 10000 stored results. Identifies query performance regressions | 1 day | P2 |
| 24 | **Add API-overhead benchmark** — measure what % of total end-to-end latency is API routing vs extraction vs storage writes | 1 day | P2 |
| 25 | **Add worker-scaling linearity benchmark** — measure throughput with 1, 2, 4, 8 concurrent workers. Throughput should scale linearly; any plateau indicates a shared bottleneck | 2 days | P2 |
| 26 | **Add concurrent unique-domain benchmark** — extract from 100 different domains in parallel, measure completion time and error rate. Tests DNS resolution, connection pooling, and per-domain isolation | 2 days | P2 |
| 27 | **Add Docker resource-limit benchmark** — run extraction suite under constrained resources (256MB RAM, 0.5 CPU, no swap), verify graceful performance degradation not crashes | 2 days | P2 |
| 28 | **Add nightly benchmark run with trend dashboard** — full benchmark suite runs nightly, results posted to a persistent dashboard (charts of F1, latency, memory over time) | 2 days | P2 |
| 29 | **Add benchmark auto-rollback** — if benchmark regresses on a stable branch, automatically revert the offending commit and open a PR with the evidence | 2 days | P2 |
| 30 | **Add extraction quality-vs-speed pareto benchmark** — run extraction at multiple quality/speed tradeoff points (lightning: HTTPX-only, balanced: HYBRID, thorough: PLAYWRIGHT_FULL), plot the pareto curve, recommend optimal default per page type | 2 days | P2 |
| 31 | **Add browser startup-time benchmark** — measure cold-start browser launch, warm-start context creation, and recycled-context reuse latency | 1 day | P2 |
| 32 | **Add memory fragmentation over 24h benchmark** — run continuous extraction for 24 hours, sample RSS every 100 extractions, assert no unbounded growth | 3 days | P2 |
| 33 | **Add GC-pause impact benchmark** — measure extraction latency tail latency (p99.9) under load to identify Garbage Collection pause effects on Playwright/Chromium | 2 days | P2 |

**Gate: 50+ benchmark cases, with Playwright-driven extraction accuracy + performance gates running in CI.**

---

## 5. Extraction Depth (75 → 80+)

Already the strongest sector. Minor refinements and user-facing controls needed.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Move strategy evolution out of research shell** — `strategy_evolution.py` is in product imports (via `html_utils.py`) but classified as research. Either move it fully into stable product kernel or gate the import with `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES` | 1 day | P1 |
| 2 | **Add user-facing fetch strategy API** — `PATCH /api/jobs/{id}/strategy` allowing user to set `PLAYWRIGHT_FULL` / `HTTPX_SMART` / `HYBRID`, etc. Currently strategy selection is internal-only (auto-decided), users have no control | 1 day | P0 |
| 3 | **Add JS wait condition configuration** — allow users to set `wait_for_selector`, `wait_for_function`, `wait_for_timeout`, `wait_for_navigation` per job. Currently extraction waits for `networkidle` only, which misses lazy-loaded content | 2 days | P1 |
| 4 | **Add profile pack with 10+ real-world site profiles** — beyond the 3 demo-site profiles (books.toscrape, quotes.toscrape, scrapethissite), add profiles for common patterns with known working selectors: Amazon product, Twitter profile, LinkedIn company, HN listing, Wikipedia article, eBay item, Indeed job listing, YouTube video, Reddit post, StackOverflow Q&A | 2 days | P1 |
| 5 | **Add extraction diff / change detection** — compare current extraction results against previous run on the same URL, flag structural changes (selector failure, schema drift, new fields appearing, old fields disappearing). Essential for monitoring extraction health over time | 3 days | P1 |
| 6 | **Add quality score calibration** — the quality scoring in the cascade uses arbitrary thresholds (0.5 minimum for early cascade exit, 0.1 floor). Run a calibration study against the benchmark corpus to set thresholds that minimize false positives and false negatives | 1 day | P2 |
| 7 | **Add XPath selector support** — currently CSS-only for user-provided selectors. XPath enables complex DOM traversal (e.g., "the paragraph after the third h2") that CSS cannot express | 2 days | P2 |
| 8 | **Add extraction from shadow DOM** — traverse open shadow roots via Playwright's `shadowRoot` property, extract content from web component-rendered pages | 2 days | P2 |
| 9 | **Add extraction from canvas / rendered text** — OCR fallback via Tesseract.js for pages that render text onto `<canvas>` elements (common in ticket booking, airline sites) | 3 days | P2 |
| 10 | **Add extraction from SVG** — inline and external SVG content extraction, including `<text>` elements and `aria-label` attributes | 1 day | P2 |
| 11 | **Add table extraction with header inference** — auto-detect `<table>` headers from `<thead>` / `<th>` scope / first-row patterns, map to output schema field names automatically | 2 days | P1 |
| 12 | **Add nested record extraction** — extract sub-records within a record (e.g., each product row has a list of reviews underneath). Define parent-child relationships in the extraction schema | 3 days | P2 |
| 13 | **Add extraction result merging** — merge records from network payload sources + DOM extraction on the same page, deduplicate by content hash, combine fields from both sources | 2 days | P1 |
| 14 | **Add extraction field mapping API** — remap extracted field names to output schema names (e.g., `product_name` → `title`, `price_amount` → `price`). Currently field names are fixed | 1 day | P2 |
| 15 | **Add extraction post-processing pipeline** — chainable transforms: regex replace, value mapping table, string concatenation, unit conversion, date formatting. Apply after extraction, before storage | 3 days | P2 |
| 16 | **Add JS execution sandbox for custom extraction logic** — allow users to inject a JavaScript function that receives the page DOM and returns extracted data. `page.evaluate()` sandboxed within the extraction context | 3 days | P1 |
| 17 | **Add selectorgadget-like selector picker** — browser extension or tool that helps users visually pick CSS selectors by clicking elements, for use in extraction config | 2 days | P2 |
| 18 | **Add extraction cascade telemetry** — per-extraction, log which cascade layer succeeded, the quality score at each layer, and why the cascade stopped. Surface in job details API | 2 days | P1 |
| 19 | **Add semantic page-type classification** — before extraction, classify the page type (product, article, listing, job posting, event, review, forum, social media, search results) and tune cascade parameters per type | 3 days | P1 |
| 20 | **Add named entity extraction** — extract people, organizations, locations, dates, monetary values, percentages from unstructured text within extracted fields | 3 days | P2 |
| 21 | **Add relationship extraction** — extract relationships between entities (e.g., "John is CEO of Acme Corp" → `{subject: John, predicate: is_CEO_of, object: Acme Corp}`) | 3 days | P2 |
| 22 | **Add per-field sentiment extraction** — for each text field, return a sentiment score (positive/negative/neutral + confidence) | 2 days | P2 |
| 23 | **Add automatic category detection** — classify what type of data was extracted (product catalog, job board, real estate listing, news article, forum thread) for downstream routing | 2 days | P2 |
| 24 | **Add language detection and auto-translation** — detect language per extracted field, optionally translate to a target language via LLM or translation API | 2 days | P2 |
| 25 | **Add extractive summarization** — for article/long-form pages, generate a short summary of the extracted content using the LLM bridge | 2 days | P2 |
| 26 | **Add image metadata extraction** — extract alt text, title, src, dimensions, file size, EXIF data from images on the page | 2 days | P2 |
| 27 | **Add video metadata extraction** — extract title, description, duration, thumbnail URL, upload date, view count from embedded videos (YouTube, Vimeo, etc.) | 2 days | P2 |
| 28 | **Add e-commerce variant extraction** — for product pages with size/color/material variants, extract all variant options with per-variant prices and availability | 3 days | P1 |
| 29 | **Add specification table extraction** — extract key-value pairs from product specification tables (weight, dimensions, material, connectivity, etc.) with intelligent header-to-value mapping | 2 days | P1 |
| 30 | **Add FAQ extraction** — detect FAQ sections (schema.org FAQPage, accordion patterns, Q&A lists), extract question-answer pairs | 2 days | P2 |
| 31 | **Add tab-content extraction** — detect tabbed interfaces, click through each tab, extract and merge content from all tabs | 2 days | P1 |
| 32 | **Add carousel/slider content extraction** — detect carousel widgets, cycle through slides, extract content from each slide | 2 days | P2 |
| 33 | **Add star rating extraction** — extract numeric ratings from visual star representations using width/height percentage or `aria-label` attributes | 1 day | P2 |
| 34 | **Add progress bar value extraction** — extract numeric values from progress bar elements using width percentage or `aria-valuenow` | 1 day | P2 |
| 35 | **Add chart data extraction** — extract data series from canvas/SVG charts via OCR, data attributes, or underlying JSON configuration | 3 days | P2 |
| 36 | **Add price history tracking** — for recurring jobs on the same product URL, track price changes over time and surface in a dedicated endpoint | 2 days | P2 |
| 37 | **Add stock/availability extraction** — detect in-stock/out-of-stock/pre-order/discontinued status from e-commerce pages | 2 days | P2 |
| 38 | **Add comparison shopping data** — when extracting the same product from multiple URLs (competitor pages), normalize prices, features, and availability into a comparison table | 3 days | P2 |
| 39 | **Add nutrition information extraction** — detect nutrition facts tables/structured data, extract serving size, calories, macros, ingredients list | 2 days | P2 |
| 40 | **Add recipe extraction** — detect recipe structured data (Schema.org Recipe), extract ingredients with quantities, instructions with steps, prep/cook time, yield | 2 days | P2 |
| 41 | **Add job posting extraction** — extract standardized fields: title, company, location (with remote/onsite classification), salary range, description, posted date, application deadline | 2 days | P1 |
| 42 | **Add real estate listing extraction** — extract standardized fields: price, square footage, beds/baths, property type, address, lot size, year built, HOA fees | 2 days | P1 |
| 43 | **Add event extraction** — detect event date/time, venue name/location, organizer, ticket price range, description, category | 2 days | P2 |
| 44 | **Add social media engagement extraction** — extract likes, shares, comments, retweets, views count from social media posts | 2 days | P2 |

**Gate: items 2+3 close the user-control gap. Items 4+5 turn this from a research prototype into a usable tool. Items 28–44 add genuine extraction depth.**

---

## 6. Production Readiness (15 → 80)

The hardest sector — most items are operational, not code.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Staging deployment with real TLS** — deploy all services (API, worker, frontend, nginx, Prometheus, Alertmanager, Grafana) behind nginx with Let's Encrypt certs on a real domain. This is the prerequisite for every other ops item | 2 days | P0 |
| 2 | **Verified alert delivery to on-call destination** — configure Alertmanager receiver (PagerDuty / OpsGenie / Slack), trigger a synthetic alert via `scripts/run_alert_delivery_drill.py`, confirm a human receives it on the destination. Currently blocked by no on-call destination configured | 1 day | P0 |
| 3 | **Rate limiting per user/job** — implement `RateLimiter` middleware with per-user token bucket, per-domain cooldown, concurrent job cap. Without this, a single user or bug can DoS a target domain or the platform itself | 2 days | P0 |
| 4 | **Load test on staging** — run `scripts/run_load_test.py` against staging, establish baseline (target: 500+ RPS, p95 < 200ms, 0 errors). Scale until bottleneck identified | 2 days | P0 |
| 5 | **Incident runbook and drill** — write runbook for top 5 failure modes (DB down, browser pool exhausted, target domain blacklisting, storage full, Alertmanager offline). Run a drill for each, record timestamps and outcomes | 3 days | P1 |
| 6 | **Backup/restore drill on staging** — run `scripts/backup_and_restore_test.py` against staging database, verify data integrity after restore by comparing record counts and checksums. Not proven outside local dev | 1 day | P1 |
| 7 | **Fill monitoring coverage gaps (F-MON-004)** — add alerts for PG disk usage (>80%), container OOM events, TLS certificate expiry (<30 days), node-exporter availability, cadvisor container metrics scraping, public HTTPS blackbox probes from two geographic regions | 2 days | P1 |
| 8 | **Graceful degradation under load** — implement circuit breaker for browser pool exhaustion (partially done at LLM bridge), add DB connection pooling limits, add request queueing with backpressure when all workers are busy | 3 days | P1 |
| 9 | **Add health check endpoints for all services** — `GET /health` (API: DB reachable, browser pool alive, storage writable), `GET /health/worker` (worker: queue accessible, idle capacity), `GET /health/db` (DB: connection pool status, migrations current), `GET /health/browser` (Playwright pool: live browser count, context availability) | 1 day | P1 |
| 10 | **Fill deployment checklist** — populate the existing `docs/DEPLOYMENT_CHECKLIST.md` with actual staging verification steps (not skeleton/templates). Each step must be verifiable by a command run against staging | 1 day | P1 |
| 11 | **Add horizontal scaling support** — multiple API workers behind nginx load balancer, shared job queue via database (already SQLite-supported), ensure no worker-local state prevents scaling out | 3 days | P1 |
| 12 | **Add database connection pooling with max-connections limit** — prevent connection exhaustion under load. Wrap the SQLite connection (or Postgres pool) with a semaphore-capped accessor | 1 day | P2 |
| 13 | **Add request queue with priority levels** — high-priority jobs (single-URL previews) skip ahead of batch jobs in the queue. Prevents previews getting stuck behind 10K-URL batches | 2 days | P2 |
| 14 | **Add rate limit by IP and by API key** — two-tier rate limiting: IP-level prevents scraping of the platform itself; API-key-level enforces user quotas | 2 days | P1 |
| 15 | **Add IP allowlist/blocklist for API access** — deploy-time config for restricting API access to trusted IP ranges or blocking known abusive IPs | 1 day | P2 |
| 16 | **Add audit logging for all extraction jobs** — log who extracted what URL, when, with which config, how many records returned. Store in a separate append-only audit store | 2 days | P1 |
| 17 | **Add data retention policies** — auto-delete extraction raw results after configurable N days (default 30). Separate retention for structured results vs raw HTML vs screenshots | 2 days | P2 |
| 18 | **Add extraction data encryption at rest** — encrypt stored extraction results with a per-tenant key. Key material via env var or KMS integration | 2 days | P2 |
| 19 | **Add result export with data signing** — HMAC-sign exported files so consumers can verify the export hasn't been tampered with since generation | 1 day | P2 |
| 20 | **Add canary deployment / staged rollout** — deploy new extraction engine version to 10% of jobs first, compare accuracy/latency metrics, auto-rollback if regression detected | 3 days | P2 |
| 21 | **Add feature flags for extraction features** — gradual rollout of new extraction layers, strategies, or anti-bot features. Toggle per-tenant or per-job | 2 days | P2 |
| 22 | **Add SLA monitoring** — track uptime (API, worker, storage), extraction latency (p50/p95/p99), error rate (by error category). Budget: 99.5% uptime, p95 < 5s extraction time, <1% error rate | 2 days | P1 |
| 23 | **Add cost tracking per job** — compute (CPU-seconds), bandwidth (bytes transferred), proxy usage (requests per proxy tier). Essential for billing and cost optimization | 2 days | P1 |
| 24 | **Add billing integration** — charge per record extracted, with tiered pricing. Free tier: 100 records/day. Pro: 10K records/day. Enterprise: unlimited | 3 days | P2 |
| 25 | **Add chaos engineering drills** — random service failure injection, network partition simulation, disk-full simulation, DNS failure simulation. Automate as a monthly drill | 3 days | P2 |
| 26 | **Add disaster recovery plan with RTO/RPO targets** — document cross-region failover plan, test it, assert RTO < 1h and RPO < 5min | 3 days | P2 |
| 27 | **Add blue-green deployment strategy** — deploy new version alongside old, route 100% traffic to green, monitor for N minutes, cutover with zero downtime | 2 days | P2 |
| 28 | **Add zero-downtime migration framework** — schema changes deployable without locking tables or dropping connections. Versioned migrations with forward-only guarantee | 2 days | P2 |
| 29 | **Add database connection encryption** — enforce TLS for all Postgres connections, reject non-TLS connections | 1 day | P1 |
| 30 | **Add automated secrets rotation** — script that rotates API keys, session secrets, DB passwords on a configurable schedule (default: 90 days) | 2 days | P2 |
| 31 | **Add container image signing via cosign** — sign every release image, verify signature before deployment | 1 day | P2 |
| 32 | **Add SBOM generation per release** — generate CycloneDX SBOM during build, attach to release artifacts | 1 day | P2 |
| 33 | **Add container vulnerability scanning in CI** — scan images with Trivy/Grype before pushing to registry, fail on high/critical CVEs | 1 day | P1 |
| 34 | **Add request ID propagation** — generate `x-request-id` at ingress, propagate through all services (API → worker → browser → storage), include in all logs | 1 day | P1 |
| 35 | **Add distributed tracing via OpenTelemetry** — trace extraction request across API → job queue → worker → Playwright browser → storage → webhook delivery | 3 days | P2 |
| 36 | **Add structured JSON logging with correlation IDs** — all services log structured JSON with `request_id`, `tenant_id`, `job_id`, `service`, `duration_ms` fields | 1 day | P1 |
| 37 | **Add log aggregation integration** — ship logs to Loki / Elasticsearch / CloudWatch with a `docker-compose` profile | 1 day | P2 |
| 38 | **Add tenant cost allocation tags** — tag all cloud resources (compute, storage, network) with tenant/team/department for showback/chargeback | 1 day | P2 |
| 39 | **Add tenant resource quotas** — enforce max jobs, max URLs per job, max storage per tenant. Hard limit to prevent noisy-neighbor problems | 2 days | P1 |
| 40 | **Add tenant data isolation CI test** — CI test that creates two tenants, extracts different URLs, asserts tenant A cannot access tenant B's results via any API route | 2 days | P1 |
| 41 | **Add SLA breach notification automation** — when SLA metrics breach budget, automatically create incident, page on-call, post to status page | 2 days | P2 |
| 42 | **Add incident postmortem template and review process** — standardized template (what happened, why, how detected, how fixed, prevention) with quarterly cross-team review | 1 day | P2 |
| 43 | **Add on-call schedule with escalation policy** — primary → secondary → engineering-manager escalation with configurable response time SLAs | 1 day | P2 |
| 44 | **Add auto-remediation for common failures** — auto-restart worker on OOM, auto-reconnect DB on connection drop, auto-recreate browser pool on stall detection | 2 days | P1 |
| 45 | **Add database migration automation** — migrations run automatically on deploy, with automated rollback on failure, zero-downtime via backward-compatible changes | 2 days | P2 |

**Gate: items 1–4, 14, 34 are the critical path. Without staging deployment and verified alert delivery, this sector cannot exceed 40. Without rate limiting + tracing, deployment to production is irresponsible.**

---

## 7. Data Quality & Post-Processing (20 → 80)

New sector — the extraction pipeline produces raw records but has no systematic quality validation, cleaning, or enrichment.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Add configurable deduplication** — merge identical records within a job using content hash, configurable dedup key (URL + field hash, content fingerprint), configurable merge strategy (keep first, keep last, union fields) | 2 days | P0 |
| 2 | **Add field-level type validation** — validate extracted field values against their declared types in the schema (e.g., price is numeric, date is parseable, email matches RFC 5322). Flag mismatches, don't silently drop | 2 days | P0 |
| 3 | **Add quality score per extraction** — compute a per-record quality score (0.0–1.0) based on field completeness, type conformance, value plausibility. Surface in job results API | 2 days | P1 |
| 4 | **Add quality trend tracking** — store quality scores over time per-domain per-schema, alert when quality drops below configurable threshold (e.g., domain quality drops from 0.95 to 0.80 → trigger webhook) | 2 days | P1 |
| 5 | **Add outlier detection and flagging** — detect values that are statistical outliers within a field (e.g., a $999,999 price among $10–$50 prices), flag for manual review | 2 days | P2 |
| 6 | **Add missing-value imputation** — for optional fields with known default values or patterns, fill in missing values (e.g., currency = "USD" when not specified) | 1 day | P2 |
| 7 | **Add data normalization pipeline** — normalize phone numbers (E.164), dates (ISO 8601), currencies (ISO 4217), units (SI), addresses (via libpostal or geocoding API) | 3 days | P1 |
| 8 | **Add data enrichment via external APIs** — enrich extracted records with geocoding (lat/lon from address), company lookup (Clearbit/Debounce), IP geolocation, domain WHOIS | 3 days | P2 |
| 9 | **Add manual review workflow** — when extraction quality is below threshold (e.g., <0.7), route to a review queue where a human can correct fields and approve | 3 days | P2 |
| 10 | **Add data lineage tracking** — every field carries provenance metadata: which cascade layer produced it, which selector, which URL, extraction timestamp | 2 days | P1 |
| 11 | **Add data freshness monitoring** — for recurring jobs, track when data was last refreshed for each URL, flag records older than configurable staleness threshold | 1 day | P2 |
| 12 | **Add cross-job deduplication** — detect when the same entity (e.g., same product URL) was extracted in multiple jobs, merge records, track latest version | 2 days | P2 |
| 13 | **Add schema drift detection** — compare extracted field names and types against the expected schema on each run, alert when fields appear/disappear or types change | 2 days | P1 |
| 14 | **Add data export with quality metadata** — include quality scores, lineage, and validation status as a separate metadata sheet/field in every export (CSV, JSON, Parquet) | 1 day | P2 |
| 15 | **Add human-in-the-loop correction API** — `PATCH /api/jobs/{id}/results/{record_id}` allows user to correct extracted field values, which feeds back into the extraction model for future runs | 2 days | P2 |
| 16 | **Add value plausibility checks** — configure per-field validation rules (e.g., price > 0 and < 100000, date is not in the future for a historical record, email contains @). Reject implausible values | 2 days | P1 |
| 17 | **Add data completeness scoring** — for each record, compute what percentage of expected fields are non-null. Alert when completeness drops below threshold | 1 day | P2 |
| 18 | **Add automated data validation rules engine** — users define custom validation rules via a simple DSL (e.g., `field:price must be > 0`, `field:email must match /.+@.+/`), rules run post-extraction | 3 days | P2 |
| 19 | **Add data quality dashboard** — web UI showing per-domain quality scores, field-level accuracy breakdown, trend charts, top validation failures | 3 days | P2 |

**Gate: deduplication + type validation + quality scoring are the foundation. Without these, extracted data is untrustworthy.**

---

## 8. Developer Experience & Ecosystem (15 → 80)

New sector — the project has no SDKs, no CLI, no tooling for developers to integrate with.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Add Python SDK with full type hints** — `pip install dataforge-sdk`, `client = DataForge(api_key="...")`, `client.extract(url="...")`, `client.jobs.list()`. Typed requests and responses matching the API | 4 days | P0 |
| 2 | **Add JavaScript/TypeScript SDK** — `npm install dataforge-sdk`, `import { DataForge } from 'dataforge-sdk'`, with full TypeScript definitions | 3 days | P1 |
| 3 | **Add CLI tool** — `pip install dataforge-cli`, `dataforge extract https://example.com`, `dataforge jobs list`, `dataforge export job-123 --format csv`. Headless extraction from the terminal | 3 days | P1 |
| 4 | **Add auto-generated OpenAPI 3.1 spec with examples** — every endpoint annotated with request/response examples, status codes, error schemas. Available at `/openapi.json` | 2 days | P1 |
| 5 | **Add auto-generated Postman collection** — script in CI that regenerates `dataforge.postman_collection.json` from OpenAPI spec on every release | 1 day | P2 |
| 6 | **Add Swagger UI playground with live API calls** — interactive API explorer at `/docs` with pre-filled example values, try-it buttons | 1 day | P1 |
| 7 | **Add VS Code extension** — syntax highlighting for extraction config files (`dataforge.yml`), snippet for common extraction patterns, inline validation of extraction schemas | 5 days | P2 |
| 8 | **Add Docker dev environment with hot reload** — `docker compose up dev` starts all services with file watching, live reload, and sample data pre-loaded | 1 day | P1 |
| 9 | **Add webhook simulator for local development** — `docker compose up webhook-sim` starts a public-facing webhook receiver (via ngrok or similar) that logs all webhook payloads for inspection | 1 day | P2 |
| 10 | **Add Go SDK** — `go get github.com/dataforge/dataforge-go`, idiomatic Go client with context support, retry middleware, streaming | 3 days | P2 |
| 11 | **Add Terraform provider** — manage extraction jobs, schedules, and templates via Terraform for infrastructure-as-code workflows | 4 days | P2 |
| 12 | **Add Helm chart for Kubernetes deployment** — deploy API, worker, frontend, nginx, and monitoring stack via `helm install dataforge` | 3 days | P2 |
| 13 | **Add example projects in 5 languages** — Python (Flask app that uses extraction), JS (Node.js webhook consumer), Go (CLI tool), Bash (curl-based automation), Java (Spring Boot integration) | 3 days | P2 |
| 14 | **Add tutorial series** — 5 tutorials: "Your first extraction", "Pagination and infinite scroll", "Custom selectors and schemas", "Recurring jobs and webhooks", "Anti-bot and proxy configuration" | 5 days | P1 |
| 15 | **Add video walkthroughs** — screen recordings of the tutorial series, published to YouTube/blog | 3 days | P2 |
| 16 | **Add community forum / Discord** — support channel, feature requests, show-and-tell, integration help | 1 day | P2 |
| 17 | **Add GitHub issue templates** — bug report, feature request, integration question, performance issue. Each with structured fields and required reproduction steps | 1 day | P2 |
| 18 | **Add public roadmap** — `github.com/orgs/dataforge/projects` with planned, in-progress, completed, and deferred columns. Updated monthly | 1 day | P2 |
| 19 | **Add status page** — `status.dataforge.dev` showing API uptime, incident history, component health, and scheduled maintenance | 2 days | P2 |
| 20 | **Add API changelog and migration guide** — versioned changelog, breaking changes highlighted, migration steps with before/after code examples | 1 day | P1 |
| 21 | **Add deprecation notices via Sunset header** — when an API version is deprecated, include `Sunset: <date>` and `Link: <migration-guide>` headers in responses | 1 day | P2 |
| 22 | **Add SQLite-to-Postgres migration guide** — step-by-step guide with scripts for users who outgrow SQLite and need Postgres | 2 days | P2 |
| 23 | **Add extraction config YAML/JSON schema** — JSON Schema spec for extraction configuration files, enabling IDE autocomplete and validation | 1 day | P1 |
| 24 | **Add Docker Compose profiles** — `docker compose --profile dev`, `--profile staging`, `--profile prod` with appropriate service sets and resource limits | 1 day | P1 |

**Gate: Python SDK + OpenAPI spec with examples are P0. Without these, the platform has no developer entry point.**

---

## 9. Compliance & Ethics (40 → 80)

New sector — the project has SSRF protection and a safety policy, but no systematic compliance infrastructure.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Add robots.txt parser and enforcer** — before extracting, fetch and parse `robots.txt`, respect `Disallow` rules and `Crawl-delay`. Configurable override via opt-in flag | 2 days | P0 |
| 2 | **Add per-domain rate limiting with crawl-delay** — enforce minimum time between requests per domain (default: 1 second, configurable). Prevents accidentally overwhelming target servers | 2 days | P0 |
| 3 | **Add robots.txt sitemap discovery** — parse `Sitemap` directives from `robots.txt`, offer sitemap-based URL discovery as an alternative to manual URL listing | 1 day | P2 |
| 4 | **Add ToS violation detection** — maintain a database of known sites that prohibit scraping in their ToS, flag jobs targeting those sites with a warning, require explicit acknowledgment to proceed | 2 days | P1 |
| 5 | **Add legal-only extraction mode** — a platform mode that disables all bypass features (stealth, proxy rotation, CAPTCHA solving) and enforces robots.txt, crawl-delay, and ToS checks. Default for free tier | 2 days | P1 |
| 6 | **Add data minimization enforcement** — only extract the fields the user explicitly requests, never extract the full page "just in case". Reduces data liability | 2 days | P1 |
| 7 | **Add cookie consent handling** — detect Cookie Consent banners (Cookiebot, OneTrust, Osano), accept/reject based on configurable policy, only proceed after consent is handled | 2 days | P2 |
| 8 | **Add GDPR right to erasure API** — `POST /api/compliance/gdpr/forget` accepts user identifier, deletes all associated extraction data, returns deletion receipt | 2 days | P1 |
| 9 | **Add CCPA opt-out mechanism** — `POST /api/compliance/ccpa/opt-out` accepts user identifier, stops all extraction activity associated with that user, returns confirmation | 1 day | P2 |
| 10 | **Add Data Processing Agreement (DPA) generation** — API endpoint that generates a DPA PDF with tenant details, data categories, processing purposes, sub-processors list | 2 days | P2 |
| 11 | **Add data processing records** — append-only log of all data processing activities: what data was extracted from which URL, by which user, stored where, exported when | 2 days | P1 |
| 12 | **Add data classification by sensitivity** — classify extracted fields (PII, financial, health, general) based on field name patterns and regex. Tag records with classification for downstream handling | 2 days | P2 |
| 13 | **Add PII field redaction in exports** — when a field is tagged as PII, optionally redact it (show "***") or exclude it entirely in exports, depending on user preference | 1 day | P2 |
| 14 | **Add export control compliance** — detect when extracted data contains export-controlled information (ITAR, EAR items), flag for compliance review | 2 days | P2 |
| 15 | **Add age-restricted content detection** — detect pages with age gates, adult content classification, or age-restricted structured data, flag for age verification | 1 day | P2 |
| 16 | **Add Acceptable Use Policy (AUP) enforcement** — detect abuse patterns: too many requests to a single domain, extraction of personal data at scale, targeting of competitor services. Auto-suspend on threshold breach | 3 days | P1 |
| 17 | **Add abuse detection and rate limit abuse monitoring** — detect API key sharing, credential stuffing, DDoS-like request patterns. Rate limit and notify admin | 2 days | P1 |
| 18 | **Add IP blacklist for abusive sources** — maintain and auto-update a blocklist of known abusive IP ranges, reject requests from blacklisted sources before they reach the API | 1 day | P2 |
| 19 | **Add ethical scraping guidelines documentation** — published guide explaining what constitutes ethical scraping, how DataForge enforces it, and how users can report violations | 1 day | P2 |
| 20 | **Add DMCA takedown support** — documented process + API endpoint for submitting DMCA takedown requests, with automated content removal and counter-notification handling | 2 days | P2 |
| 21 | **Add data residency controls** — allow tenants to choose which geographic region their data is stored and processed in. Enforce at the storage backend level | 3 days | P2 |
| 22 | **Add SOC 2 evidence collection automation** — automated collection of access logs, change management records, incident response evidence, data deletion proofs for SOC 2 audits | 3 days | P2 |
| 23 | **Add penetration testing schedule** — quarterly third-party pen test, results shared with customers on request | 1 day (setup) | P2 |
| 24 | **Add bug bounty program** — public bug bounty with defined scope, reward tiers, disclosure policy, and hall of fame | 2 days (setup) | P2 |

**Gate: robots.txt enforcement + per-domain rate limiting + data minimization are P0. Without these, the platform is legally and ethically risky to operate.**

---

## 10. Observability & Debugging (50 → 80)

New sector — the project has basic Prometheus metrics but no extraction-specific observability or debugging tooling.

| # | Action | Est. Effort | Priority |
|---|--------|-------------|----------|
| 1 | **Add extraction-specific Prometheus metrics** — counters for: extractions attempted, succeeded, failed, blocked, timed out, by domain, by fetch strategy, by cascade layer | 2 days | P0 |
| 2 | **Add extraction latency histograms** — p50/p90/p95/p99 extraction time by domain, by strategy, by cascade layer. Essential for performance monitoring | 1 day | P1 |
| 3 | **Add per-domain success rate tracking** — rolling 24h success/failure rate per domain, alert when drops below 90% (indicates a site changed its structure or started blocking) | 1 day | P1 |
| 4 | **Add extraction cascade telemetry** — per-extraction log of: which cascade layers were attempted, which succeeded, quality score at each layer, why the cascade stopped. Stored in job result metadata | 2 days | P1 |
| 5 | **Add extraction debug output** — `GET /api/jobs/{id}/debug` returns the full cascade trace, rendered page screenshot (if Playwright was used), raw HTML snapshot, network capture log, and all error messages. Invaluable for debugging | 3 days | P0 |
| 6 | **Add screenshot-per-extraction storage** — for Playwright-based extractions, save a screenshot of the page at extraction time. Provide via job detail API for visual debugging | 2 days | P1 |
| 7 | **Add page HTML snapshot storage** — save the rendered HTML at extraction time alongside results, enables post-hoc debugging when extraction quality is poor | 2 days | P2 |
| 8 | **Add extraction trace viewer** — web UI showing the cascade layer-by-layer: what each layer extracted, quality scores, timing. Overlaid with the page screenshot for visual comparison | 4 days | P2 |
| 9 | **Add extraction performance flamegraph** — per-extraction timeline showing time spent in: URL analysis, browser launch, page load, DOM stabilization, selector extraction, network capture, post-processing | 3 days | P2 |
| 10 | **Add error classification and aggregation** — categorize extraction failures (timeout, block, auth_required, ssl_error, network_error, parse_error, empty_page), aggregate by category, alert on category spikes | 2 days | P1 |
| 11 | **Add extraction health dashboard** — Grafana dashboard showing: extraction rate (req/s), success rate %, p95 latency, top failing domains, cascade layer usage distribution, browser pool utilization | 2 days | P1 |
| 12 | **Add per-job tracing with OpenTelemetry** — trace a single job request through API → queue → worker → browser → storage. Includes timing per step and error attribution | 3 days | P2 |
| 13 | **Add structured job logs** — each job emits structured logs (JSON) with `job_id`, `url`, `strategy`, `duration_ms`, `records_found`, `cascade_layer`, `error`. Aggregated in Loki/Elasticsearch | 1 day | P1 |
| 14 | **Add log correlation ID per job** — single correlation ID (`x-correlation-id`) propagated from job creation through all services, included in every log line and metric | 1 day | P1 |
| 15 | **Add browser console log capture** — for Playwright extractions, capture `console.log`, `console.warn`, `console.error` from the browser page. Include in debug output. Catches JS errors that affect extraction | 1 day | P1 |
| 16 | **Add network request log capture** — capture all HTTP requests made by the page during extraction (URL, method, status, timing). Include in debug output | 1 day | P2 |
| 17 | **Add automated alert on extraction anomaly** — detect when extraction quality, latency, or success rate deviates >2σ from the 7-day rolling average, page on-call with a link to the debug dashboard | 2 days | P1 |
| 18 | **Add extraction audit log** — append-only log of every extraction: who, what URL, when, what strategy, how many records, error (if any). Immutable, queryable for compliance | 2 days | P1 |
| 19 | **Add browser resource usage metrics** — track per-browser-context: RSS, CPU, open handles, active requests. Export as Prometheus Gauge. Alert on per-context memory > 500MB | 2 days | P2 |
| 20 | **Add extraction cost breakdown per job** — in job detail API, show: compute cost (CPU-seconds), browser cost (context-seconds), network cost (bytes transferred), proxy cost (requests) | 2 days | P2 |
| 21 | **Add Grafana alert rules for all extraction metrics** — success rate < 90% for 5min, p95 latency > 10s for 5min, browser pool utilization > 80%, queue depth > 100 | 1 day | P1 |
| 22 | **Add anomaly detection for extraction quality** — ML-based detection of extraction quality degradation before it becomes a customer-facing issue (e.g., a site changed CSS classes but extraction still partially works) | 3 days | P2 |

**Gate: items 1, 5, 10, 11 are P0. Without extraction-specific metrics and debug output, diagnosing failures is guesswork.**

---

## Summary: Implementation Waves

| Wave | Focus | Key Items | Duration | Score After |
|------|-------|-----------|----------|-------------|
| **1** | Reliability tests + CI browser | Rel 1–6, Bench 1–3 | 10 days | 41 → 50 |
| **2** | Feature essentials | Feat 1–4, 9, 19, 29 | 9 days | 50 → 57 |
| **3** | Anti-bot solving + retry | Anti 1–3, 5, 33 | 8 days | 57 → 63 |
| **4** | Real-world benchmarks + CI gate | Bench 4–7, 9, 12, 16, 21 | 9 days | 63 → 68 |
| **5** | Production staging + rate limit | Prod 1–4, 14, 34 | 8 days | 68 → 73 |
| **6** | Data quality foundation | Qual 1–3, 6–7, 10, 13 | 8 days | 73 → 76 |
| **7** | Developer SDK + docs | Dev 1, 4, 6, 8, 14, 20 | 8 days | 76 → 78 |
| **8** | Observability + debugging | Obs 1, 5, 10, 11, 15 | 8 days | 78 → 80 |
| **9** | Compliance essentials | Comp 1, 2, 5, 6, 8 | 7 days | 80 → 82 |
| **10** | Polish across all sectors | All remaining items | 20 days | 82 → 87 |

**Total: ~95 engineering days (~19 weeks / ~4.5 months) to go from 41 → 87 overall scraper score.**

Waves 1–2 (~19 days) fix the two most embarrassing gaps: zero real extraction tests and no user-configurable job parameters. Waves 3–5 (~25 days) make the platform actually usable against real-world targets. Waves 6–10 (~50 days) make it production-grade, compliant, and developer-friendly.

---

## Session Log: 2026-06-29 (Session 87)

### Completed this session

The following items from the roadmap were fully or partially implemented:

| # | Item | Deliverable |
|---|------|-------------|
| Rel 4 | End-to-end job lifecycle test | `test_lifecycle_e2e_default.py` (9 tests: create, cancel, delete/restore, SSRF rejection, idempotency, bulk cleanup) |
| Rel 6 | Extraction response validation | `test_extraction_response_validation.py` (20 tests: field-level type validation, record quality scoring, post-extract validation, full pipeline) |
| Rel 2 | Extraction HTTP server integration | `test_extraction_http_server_integration.py` (14 tests: serves real fixture HTML, covers 8 page types, cross-contamination) |
| Bench 3 | Pagination benchmark | `test_pagination_benchmark.py` (17 tests: all 5 async strategies, dedup, limits, sync dispatch) |
| Feat 19 | Extraction preview/dry-run | Fixed `POST /api/scraper/preview` forwarding; `test_extraction_preview.py` (9 tests) |
| Dev 1 | Python SDK | `backend/sdk/__init__.py` (extract, preview, get/cancel/list/delete job, get_usage); `test_sdk_client.py` (9 tests) |
| Bench 16 | A/B benchmark mode | `test_benchmark_ab_mode.py` (4 tests: strategy comparison, sync dispatch, stop reasons) |
| Qual 6+7 | Missing-value imputation | `test_data_quality_imputation.py` (12 tests: empty records, nulls, whitespace, URL stripping, pipeline warnings) |
| Obs 15 | Browser console log capture | Modified `setup_network_capture()` to return `(captured_payloads, console_logs)`; console listener added; test in `test_browser_network_capture.py` |
| Obs 5 | Extraction debug endpoint | Added `GET /api/jobs/{job_id}/debug` in `jobs_read.py` — returns job summary, per-domain crawl policy state, all-domain states |
| Comp 2 | Per-domain rate limiting tests | `test_crawl_policy_rate_limiting.py` (30 tests: concurrency budget, request pacing, cooldown, page budget, observability) |
| Qual 13 | Schema drift detection tests | `test_schema_drift_detection.py` (23 tests: field drift, quality regression, record modifications, summaries) |
| Dev 4 | OpenAPI spec tests | `test_openapi_spec.py` (22 tests: spec structure, required routes, methods, parameters, schema components) |

### Fixes applied

- `backend/app/services/scraping.py` — Added missing `import threading` (NameError)
- `backend/app/crawl_policy.py` — `record_result(success=True)` now clears `cooldown_until` so a succeeding fetch immediately lifts cooldown
- `backend/sdk/__init__.py` — Fixed usage path from `/api/usage` to `/api/saas/usage`

### New test count: +176 tests (all passing)
- 176 new tests added, 0 regressions
- Full `--quick` validation passes (static analysis + boundary + dependency checks)
