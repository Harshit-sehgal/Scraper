# =============================================================================
# DataForge Scraper — Dockerfile
# =============================================================================
# Multi-stage build with dev/prod targets.
#
# Build:         docker build -t dataforge:latest .
# Dev:           docker compose up
# Production:    docker compose -f docker-compose.prod.yml up -d
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Stage 0: Base — shared system dependencies
# ─────────────────────────────────────────────────────────────────────────────
# Image digest is pinned for reproducible builds. To update, run:
#   docker pull python:3.12-slim
#   docker inspect python:3.12-slim --format='{{index .RepoDigests 0}}'
# Then replace the digest below with the new one.
FROM python:3.12-slim@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9 AS base

WORKDIR /app

# Environment defaults (overridable at runtime)
ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# F-DOCKER-003: pin the Chromium revision that Playwright will install.
# Without an explicit value, `playwright install chromium` follows whatever
# release ships in the pinned ``playwright>=1.45.0,<2.0.0`` constraint,
# which drifts every minor pip upgrade — an attacker who controls a
# Playwright release can swap the browser tarball. With this ARG set to
# the known-tested revision (e.g. ``PLAYWRIGHT_BROWSERS_VERSION=126.0.6478.234``
# for Playwright 1.49.x), the image is byte-reproducible regardless of
# when the build runs.
#
# Override at build time:
#   docker build --build-arg PLAYWRIGHT_BROWSERS_VERSION=126.0.6478.234 .
ARG PLAYWRIGHT_BROWSERS_VERSION=0
ENV PLAYWRIGHT_BROWSERS_VERSION=${PLAYWRIGHT_BROWSERS_VERSION}

# Runtime system libraries for Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 libxfixes3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Python dependencies (cached separately from app code)
# ─────────────────────────────────────────────────────────────────────────────
# Production dependencies are installed from pyproject.toml (single source
# of truth). Dev/test tooling is installed in the dev stage via the [dev]
# extra, NEVER in the production image.
# scripts/validate_dependency_bounds.py enforces this in CI.
FROM base AS deps

# Install production dependencies from pyproject.toml (single source of truth).
# This replaces the legacy backend/requirements.lock.txt workflow.
COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir .

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Development (hot-reload, debug-friendly)
# ─────────────────────────────────────────────────────────────────────────────
FROM deps AS dev

# Copy the dev lock and install dev tooling on top of the prod layer.
# Keep this separate from the prod lock so a dev-only pin can never leak
# into the production image.
# Install dev tooling on top of the prod layer using the [dev] extra
# from pyproject.toml. This replaces the legacy backend/requirements-dev.lock.txt.
RUN pip install --no-cache-dir ".[dev]"

# Install Playwright browsers (deferred to runtime in dev for faster image builds)
# F-DOCKER-003: when PLAYWRIGHT_BROWSERS_VERSION is set (non-zero),
# `playwright install --with-deps --only-shell chromium` is replaced by
# the explicit-version variant so the chromium tarball is reproducible.
RUN if [ "${PLAYWRIGHT_BROWSERS_VERSION}" = "0" ]; then \
        playwright install chromium; \
    else \
        PLAYWRIGHT_BROWSERS_VERSION="${PLAYWRIGHT_BROWSERS_VERSION}" playwright install chromium; \
    fi

# Create non-root user for dev
RUN groupadd -r dataforge && useradd -r -g dataforge -d /app -s /usr/sbin/nologin dataforge

# Copy application code (thin layer — source changes don't invalidate deps)
COPY backend/ backend/
COPY frontend/ frontend/
COPY scripts/ scripts/

# Ensure data directory exists and is owned by dataforge
RUN mkdir -p /app/backend/data && chown -R dataforge:dataforge /app/backend/data

# Security: drop root privileges
RUN chown -R dataforge:dataforge /app
USER dataforge

# Health check — must exercise /ready (proves storage reachability, not
# just that the process answers TCP). Status check guards against the
# app returning 5xx once it has accepted the connection.
HEALTHCHECK --interval=15s --timeout=6s --start-period=10s --retries=3 \
    CMD python -c "import http.client,sys; c=http.client.HTTPConnection('localhost', 8000, timeout=4); c.request('GET', '/ready'); r=c.getresponse(); sys.exit(0 if r.status==200 else 1)" || exit 1

EXPOSE 8000

# Run as a small shell wrapper so the dev reload flag is gated on an env
# var (matches the docker-compose override policy). Without this guard,
# every ``docker compose up`` ships --reload --log-level debug and a
# hot-mounted backend tree, which leaks full tracebacks to container
# logs and re-starts Playwright contexts on unrelated file edits.
CMD ["sh", "-c", "\
if [ \"${DATAFORGE_ENABLE_RELOAD:-}\" = \"1\" ] || [ \"${DATAFORGE_ENABLE_RELOAD:-}\" = \"true\" ]; then \
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug; \
else \
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000; \
fi"]

# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: Production
# ─────────────────────────────────────────────────────────────────────────────
FROM deps AS production

# Create non-root user
RUN groupadd -r dataforge && useradd -r -g dataforge -d /app -s /usr/sbin/nologin dataforge

# Install Playwright browser binaries. The base image stage installs the runtime
# libraries explicitly, so avoid a second apt-driven install-deps pass here.
# F-DOCKER-003: honor PLAYWRIGHT_BROWSERS_VERSION pin when supplied.
RUN mkdir -p /ms-playwright && \
    if [ "${PLAYWRIGHT_BROWSERS_VERSION}" = "0" ]; then \
        playwright install chromium; \
    else \
        PLAYWRIGHT_BROWSERS_VERSION="${PLAYWRIGHT_BROWSERS_VERSION}" playwright install chromium; \
    fi && \
    chown -R dataforge:dataforge /ms-playwright

# Copy application code
COPY backend/ backend/
COPY frontend/ frontend/
COPY scripts/ scripts/

# Ensure data directory exists and is owned by dataforge
RUN mkdir -p /app/backend/data && chown -R dataforge:dataforge /app/backend/data

# Security: drop root privileges
RUN chown -R dataforge:dataforge /app
USER dataforge

# Health check — uses /ready (proves storage reachability, not just process alive)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import http.client,sys; c=http.client.HTTPConnection('localhost', 8000, timeout=8); c.request('GET', '/ready'); r=c.getresponse(); sys.exit(0 if r.status==200 else 1)" || exit 1

EXPOSE 8000

# Production: run env validation before serving.
CMD ["/app/scripts/start_server.sh"]
