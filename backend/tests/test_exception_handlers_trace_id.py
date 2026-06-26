"""Static + behavioral guard for F-EXCEPTION-001 — JSON 5xx with trace_id.

Pre-fix, ``backend/app/main.py:configure_exception_handlers`` was an
empty stub. The FastAPI default handlers returned a plaintext
``Internal Server Error`` body with status 500 and no correlation key —
operators had no way to map a client-side 500 message to a server log
line. Several routers (``scraper.py``, ``services/job_mutation_service.py``)
also raised plain ``HTTPException(status_code=500, detail='...')``
without structured detail.

The fix wires ``app.add_exception_handler`` for both
``StarletteHTTPException`` and the generic ``Exception``. Each response
carries a hex ``trace_id`` (16 chars) that is mirrored in the server
log so the operator dashboard can pivot.

This test:

1. Confirms ``app.add_exception_handler`` was actually wired for both
   paths.
2. Drives a TestClient through a deliberately-broken handler that
   raises ``HTTPException(500)`` and verifies the trace_id appears in
   the JSON body.
3. Drives a generic ``Exception`` through TestClient and verifies the
   500 body carries a trace_id and the ``error_class`` field.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))


class TestFastAPITraceIdExceptionHandlers:
    """``configure_exception_handlers`` ships trace_id + log mirror."""

    def test_handlers_wired_on_app(self) -> None:
        # Import inside the test so we don't pull FastAPI at collection time.
        import app.main as main_module
        from fastapi import FastAPI
        from starlette.exceptions import HTTPException as StarletteHTTPException

        app = FastAPI()
        main_module.configure_exception_handlers(app)
        # FastAPI stores installed handlers in ``app.exception_handlers``
        # (a dict keyed by exception class). Both must be present.
        handlers = app.exception_handlers  # type: ignore[attr-defined]
        assert StarletteHTTPException in handlers, (
            "F-EXCEPTION-001: StarletteHTTPException handler is not wired."
            " Custom 4xx/5xx HTTPException responses will fall back to"
            " FastAPI's default empty body."
        )
        assert Exception in handlers, (
            "F-EXCEPTION-001: generic Exception handler is not wired."
            " Unhandled errors return FastAPI's default 500 with no"
            " correlation id."
        )

    def test_http_exception_response_has_trace_id(self) -> None:
        import app.main as main_module
        from fastapi import FastAPI, HTTPException
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/break-with-http")
        def _break() -> None:
            raise HTTPException(status_code=418, detail="drill says no")

        main_module.configure_exception_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.get("/break-with-http")
        assert res.status_code == 418
        body = res.json()
        assert "detail" in body
        assert "trace_id" in body, (
            "F-EXCEPTION-001: HTTPException handler response had no"
            " trace_id; the operator dashboard cannot pivot to the"
            " server log without it."
        )
        # 16-hex-char (8 random bytes) is the agreed format.
        assert re.fullmatch(r"[0-9a-f]{16}", body["trace_id"]), (
            f"F-EXCEPTION-001: trace_id is not a 16-hex-char string; got {body['trace_id']!r}."
        )

    def test_unhandled_exception_returns_structured_500(self) -> None:
        import app.main as main_module
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/break-with-generic")
        def _break() -> None:
            msg = "synthetic test failure"
            raise ValueError(msg)

        main_module.configure_exception_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.get("/break-with-generic")
        assert res.status_code == 500, (
            "F-EXCEPTION-001: unhandled exception returned a non-500"
            f" status code ({res.status_code}); replay the test against"
            " a fresh app."
        )
        body = res.json()
        assert "trace_id" in body, "F-EXCEPTION-001: 500 body without trace_id; client cannot link back to the server log."
        assert "error_class" in body, (
            "F-EXCEPTION-001: 500 body missing error_class; ops only see a generic 'internal error' string."
        )
        assert body["error_class"] == "ValueError", (
            "F-EXCEPTION-001: error_class is the exception type's name"
            " so operators can quickly triage (e.g. ValueError = bad"
            " input, RuntimeError = missing config). Got"
            f" {body['error_class']!r}."
        )
        # Error message must NOT leak the full exception text — that
        # would otherwise expose stack frame layout to clients.
        assert "synthetic test failure" not in str(body), (
            "F-EXCEPTION-001: 500 body leaked the exception message; client-facing responses should never include raw str(exc)."
        )
