# Resource Leak Scan — Round N+3 Findings (2026-06-28)

Compiled by the running general-purpose deep-scan agent (a7713bc5a14a83cb4).
All findings are read-only; no file was modified by the agent.

## CRITICAL

- **C1** `_start_fixture_server` leaks aiohttp `AppRunner` on `site.start()` failure
  - File: `backend/app/services/browser_workflow_runner.py` lines 344–351
  - Fix: try/except inside `_start_fixture_server`, `await runner.cleanup()` before re-raise

- **C2** Playwright `page` leak when step execution or content fetch raises
  - File: `backend/app/services/browser_workflow_runner.py` lines 113–165
  - Fix: move `await page.close()` to outer `finally`

- **C3** `browser_pool._evict_lru_if_needed` redundant pop swallows close failures
  - File: `backend/app/browser_pool.py` lines 558–570
  - Fix: remove redundant pop; wrap close + bookkeeping in try/finally

## HIGH

- **H1** `httpx.get(...)` module-level shortcut in proxy provider
  - File: `backend/app/proxy_providers.py` lines 181–186
  - Fix: use `with httpx.Client(timeout=10.0) as client:`

- **H2** Half-initialized pool leak on `_pool.open()` failure
  - File: `backend/app/worker_queue_postgres_psycopg3.py` lines 54–84
  - Fix: in failure path, `with suppress(Exception): _pool.close()` then `_pool = None; raise`

- **H3** `PostgresWorkflowRepository._conn` (psycopg2 path) lacks commit/rollback on user exception
  - File: `backend/app/postgres_workflow_repository.py` lines 247–254
  - Fix: yield conn → commit on success, rollback + reraise on user exception

- **H4** `check_health()` can leak `ctx` and `page`
  - File: `backend/app/browser_pool.py` lines 660–666
  - Fix: outer try/finally around `new_context()` so ctx.close() always runs

- **H5** `notifications.py` singleton `httpx.AsyncClient` not deterministically closed
  - File: `backend/app/services/notifications.py` lines 17–46
  - Fix: explicit `await response.aclose()` in finally; confirm lifespan shutdown closes

- **H6** `requests.post()` response not deterministically released in telegram_notifier
  - File: `backend/app/utils/telegram_notifier.py` lines 144–156
  - Fix: `with requests.post(...) as response:` or explicit `response.close()` in `finally`

## MEDIUM

- **M1** `storage_interface.py` mkstemp → fdopen transfer window
  - File: `backend/app/storage_interface.py` lines 822–835
  - Fix: explicit os.close + os.unlink tmp_path on failure

- **M2** `worker_queue_postgres_base` semaphore permit leak on non-DB exceptions
  - File: `backend/app/worker_queue_postgres_base.py` lines 822–831
  - Fix: broaden except to `BaseException` so permit always released

- **M3** `crawl_frontier` sync DB I/O held under async lock
  - File: `backend/app/crawl_frontier.py` lines 209–220, 242–253, 273–301, 306–317, 357–367, 376–387, 395–398, 464–467
  - Fix: snapshot under lock; release lock; then `run_in_threadpool`

- **M4** `crawl_frontier._db_*` helpers open fresh `sqlite3.connect` for every operation
  - File: `backend/app/crawl_frontier.py` lines 38–82
  - Fix: long-lived `sqlite3.Connection` on frontier, or per-thread pool

- **M5** `crawl_frontier` SQLite fallback leaves in-memory mutations unrolled
  - File: `backend/app/crawl_frontier.py` lines 209–220, 242–253, 273–301, 306–317, 357–367, 376–387, 395–398
  - Fix: on fallback, undo in-memory mutation (heapq.heappop + _pending.discard)

- **M6** `worker_queue._get_connection` PRAGMA setup exception can leak conn
  - File: `backend/app/worker_queue.py` lines 208–216
  - Fix: wrap PRAGMA block in try/except with conn.close() + raise

- **M7** `job_runner.py` `ThreadPoolExecutor` futures never observed
  - File: `backend/app/services/job_runner.py` lines 40–76
  - Fix: capture Future; observe `.exception()`

- **M8** `cf_harvester` Playwright `page` never explicitly closed
  - File: `backend/app/cf_harvester.py` lines 60–199
  - Fix: `try: ... finally: await page.close()` around polling block

## LOW

- **L1** `notifications.py` lazy `_get_client()` race
- **L2** `telegram_notifier.py` `requests.post` (duplicates H6)
- **L3** `crawl_frontier` `_load_from_db` partial-state on mid-loop failure
- **L4** `storage_migrations.py` skips `DROP TABLE worker_heartbeats_v5_backup` on partial failure
- **L5** `rate_limiter.DatabaseSlidingWindowCounter.prune_all` error filtering
- **L6** `_SAVE_EXECUTOR` race in `state_store.flush_state_writes`
- **L7** `state_store.save_state` silently drops writes when executor is shut
- **L8** `cf_harvester.py` Playwright `Page` lifecycle (documents M8)
- **L9** `_on_task_done` orphan cleanup tasks on shutdown
- **L10** `rate_limiter._get_or_create_counter` always evicts DB-backed counters
- **L11** `url_safety.py` factory returns bare client (defense-in-depth gap)
- **L12** Job-runner ThreadPoolExecutor lacks `thread_name_prefix`

## Clean Files

- `llm_bridge.py`, `proxy_manager.py`, `captcha_solver.py`, `browser_network_capture.py`
- `page_profiler.py`, `page_evidence_collector.py`, `storage_health.py`
- `services/webhook_delivery.py`, `services/scraping.py`
- `services/workflow_runner.py`, `services/exports.py`
- `postgres_repository.py`, `postgres_repository_base.py`, `psycopg3_repository.py`
- `select_engine.py`, `selector_discovery.py`, `snapshot_desync_detector.py`, `url_analyzer.py`
- `storage_mapper.py`, `checkpoint_manager.py`, `state_store._write_state_to_disk`
- `semantic_world_state/locks.py`

## Priority

1. CRITICAL (C1–C3): Browser/aiohttp leaks compound under load
2. HIGH (H1–H6): Proxy and DB pool leaks
3. MEDIUM (M1–M8): Crawl frontier is the highest-impact cluster; one connection-pool refactor resolves M3, M4, M5
4. LOW (L1–L12): Clean opportunistically
