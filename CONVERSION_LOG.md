# Conversion Log — asyncpg → psycopg2

## Date
2026-05-26

## Summary
Replaced `asyncpg` (async Postgres driver) with `psycopg2-binary` (sync Postgres driver) in the `PostgresJobRepository` implementation.

## Motivation
The `JobRepository` ABC is fully synchronous. Wrapping asyncpg calls with `_run_async()` (which used `asyncio.run()` + `ThreadPoolExecutor`) created event-loop/pool hazards:

- A new event loop was created on every repository call
- The asyncpg pool was created in one event loop and could be accessed from another
- This pattern risked `RuntimeError: Cannot close a running event loop` in production
- No existing callers benefited from async — all consumer code expects sync operations

## Changes Made

### backend/app/postgres_repository.py — Complete rewrite
- **Pool**: `asyncpg.create_pool()` → `psycopg2.pool.ThreadedConnectionPool` (thread-safe)
- **Connections**: `async with pool.acquire() as conn:` → `with _conn():` context manager with proper commit/rollback/putconn lifecycle
- **Queries**: `await conn.fetch()` → `conn.cursor() + cur.fetchall()` via `_fetch_all()`/`_fetch_one()` helpers
- **Placeholders**: `$1, $2, ...` → `%s` (psycopg2 style)
- **No async wrappers**: Removed all `_run_async()` and `async def` patterns
- **Thread safety**: `asyncio.Lock` → `threading.Lock`

### backend/app/storage_interface.py
- Error message updated: `"Install asyncpg"` → `"Install psycopg2-binary"`
- `reset_repository()`: removed `asyncio.run(shutdown_postgres())` — now calls `shutdown_postgres()` directly (sync)

### backend/requirements.txt
- `asyncpg>=0.29.0` → `psycopg2-binary>=2.9.0`

## Verification
- 33/33 unit tests pass (worker queue + Postgres repository)
- 1419 tests pass in full suite (excluding pre-existing `test_browser_pool_hard_recycling` failure)
- Pyflakes clean across entire codebase
- Architecture validator: PASSED
- No `asyncpg` or `_run_async` references remain in the Postgres repository layer

## Postgres Integration Tests
Located at `backend/tests/test_postgres_integration.py` — behind `-m postgres` marker.
Requires Docker and a running Postgres container (via `testcontainers`).
Run with:
```bash
pytest -m postgres -v
```

## Future Considerations
- If async support is needed in the future, consider making the entire `JobRepository` ABC async and updating all callers, rather than using sync wrappers around an async driver.
