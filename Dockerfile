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
FROM python:3.12-slim AS base

WORKDIR /app

# Environment defaults (overridable at runtime)
ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

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
# Production-only lock. Dev/test tooling lives in
# backend/requirements-dev.lock.txt and is NEVER installed in this stage.
# scripts/validate_dependency_bounds.py enforces this in CI.
FROM base AS deps

COPY backend/requirements.lock.txt .

# Install production dependencies only (from lock file for reproducible builds)
RUN pip install --no-cache-dir -r requirements.lock.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Development (hot-reload, debug-friendly)
# ─────────────────────────────────────────────────────────────────────────────
FROM deps AS dev

# Copy the dev lock and install dev tooling on top of the prod layer.
# Keep this separate from the prod lock so a dev-only pin can never leak
# into the production image.
COPY backend/requirements-dev.lock.txt /tmp/requirements-dev.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.lock.txt && \
    rm -f /tmp/requirements-dev.lock.txt

# Install Playwright browsers (deferred to runtime in dev for faster image builds)
RUN playwright install chromium

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
    CMD python -c "import http.client,sys; c=http.client.HTTPConnection('localhost', 8000, timeout=4); c.request('GET', '/ready'); r=c.getresponse(); sys.exit(0 if 200 <= r.status < 500 else 1)" || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "debug"]

# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: Production
# ─────────────────────────────────────────────────────────────────────────────
FROM deps AS production

# Create non-root user
RUN groupadd -r dataforge && useradd -r -g dataforge -d /app -s /usr/sbin/nologin dataforge

# Install Playwright browser binaries. The base image stage installs the runtime
# libraries explicitly, so avoid a second apt-driven install-deps pass here.
RUN mkdir -p /ms-playwright && playwright install chromium && chown -R dataforge:dataforge /ms-playwright

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
