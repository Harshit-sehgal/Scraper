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
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Runtime system libraries for Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Python dependencies (cached separately from app code)
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS deps

COPY backend/requirements.txt .

# Install production dependencies only
RUN pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Development (hot-reload, debug-friendly)
# ─────────────────────────────────────────────────────────────────────────────
FROM deps AS dev

# Install dev dependencies
RUN pip install --no-cache-dir pytest pytest-cov pytest-asyncio mypy pyflakes autoflake

# Install Playwright browsers (deferred to runtime in dev for faster image builds)
RUN playwright install chromium 2>&1 | tail -5

# Copy application code (thin layer — source changes don't invalidate deps)
COPY backend/ backend/
COPY frontend/ frontend/
COPY scripts/ scripts/

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import http.client; http.client.HTTPConnection('localhost', 8000).request('GET', '/');" || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "debug"]

# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: Production (minimal, secure)
# ─────────────────────────────────────────────────────────────────────────────
FROM deps AS production

# Install Playwright browsers (only chromium, minimal deps)
RUN playwright install chromium 2>&1 | tail -3

# Create non-root user
RUN groupadd -r dataforge && useradd -r -g dataforge -d /app -s /usr/sbin/nologin dataforge

# Copy application code
COPY backend/ backend/
COPY frontend/ frontend/

# Security: drop root privileges
RUN chown -R dataforge:dataforge /app
USER dataforge

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import http.client; http.client.HTTPConnection('localhost', 8000).request('GET', '/');" || exit 1

EXPOSE 8000

# Production: no --reload, info-level logs
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
