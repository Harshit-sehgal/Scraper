# =============================================================================
# DataForge Scraper — Dockerfile
# =============================================================================
# Multi-stage build with dev/prod targets and a dedicated Node builder stage
# for the frontend (F-DOCKER-FRONTEND).
#
# Build:         docker build -t dataforge:latest .
# Dev:           docker compose up
# Production:    docker compose -f docker-compose.prod.yml up -d
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Stage 0: Base — shared system dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9 AS base

WORKDIR /app

ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

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
FROM base AS deps

COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir .

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1b: Frontend bundle (separate Node stage — F-DOCKER-FRONTEND)
# ─────────────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY frontend/ ./frontend/
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Development (hot-reload, debug-friendly)
# ─────────────────────────────────────────────────────────────────────────────
FROM deps AS dev

RUN pip install --no-cache-dir ".[dev]"

# Install Playwright browsers
RUN if [ "${PLAYWRIGHT_BROWSERS_VERSION}" = "0" ]; then \
        playwright install chromium; \
    else \
        PLAYWRIGHT_BROWSERS_VERSION="${PLAYWRIGHT_BROWSERS_VERSION}" playwright install chromium; \
    fi

RUN groupadd -r dataforge && useradd -r -g dataforge -d /app -s /usr/sbin/nologin dataforge

COPY backend/ backend/
COPY frontend/ frontend/
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY scripts/ scripts/

RUN mkdir -p /app/backend/data && chown -R dataforge:dataforge /app/backend/data
RUN chown -R dataforge:dataforge /app
USER dataforge

HEALTHCHECK --interval=15s --timeout=6s --start-period=10s --retries=3 \
    CMD python -c "import http.client,sys; c=http.client.HTTPConnection('localhost', 8000, timeout=4); c.request('GET', '/ready'); r=c.getresponse(); sys.exit(0 if r.status==200 else 1)" || exit 1

EXPOSE 8000

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

RUN groupadd -r dataforge && useradd -r -g dataforge -d /app -s /usr/sbin/nologin dataforge

# Install Playwright browser binaries
RUN mkdir -p /ms-playwright && \
    if [ "${PLAYWRIGHT_BROWSERS_VERSION}" = "0" ]; then \
        playwright install chromium; \
    else \
        PLAYWRIGHT_BROWSERS_VERSION="${PLAYWRIGHT_BROWSERS_VERSION}" playwright install chromium; \
    fi && \
    chown -R dataforge:dataforge /ms-playwright

COPY backend/ backend/
COPY frontend/ frontend/
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY scripts/ scripts/

RUN mkdir -p /app/backend/data && chown -R dataforge:dataforge /app/backend/data
RUN chown -R dataforge:dataforge /app
USER dataforge

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import http.client,sys; c=http.client.HTTPConnection('localhost', 8000, timeout=8); c.request('GET', '/ready'); r=c.getresponse(); sys.exit(0 if r.status==200 else 1)" || exit 1

EXPOSE 8000

CMD ["/app/scripts/start_server.sh"]
