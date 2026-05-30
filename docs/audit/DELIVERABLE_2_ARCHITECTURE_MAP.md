# Deliverable 2: Architecture Reality Map

**Purpose:** Document what the project ACTUALLY does based on code inspection, not marketing claims  
**Status:** COMPREHENSIVE CODE ANALYSIS  
**Methodology:** Direct code inspection, route enumeration, module analysis

---

## 1. System Overview (What It Actually Is)

### Truth Statement
DataForge is a **pre-production web extraction platform** built with FastAPI and Playwright browser automation. It:
- Creates scraping jobs for specified URLs
- Attempts to extract structured data using CSS selectors, AI-powered extraction, and adaptive learning
- Stores results in SQLite or PostgreSQL
- Provides REST API endpoints and observability/metrics
- Includes a dashboard for monitoring
- Implements job history, replay functionality, and some adaptive/self-healing mechanisms

### What It Is NOT
- ❌ Not a "universal" scraper that works on "any website"
- ❌ Not "fully autonomous" or "self-healing" without significant configuration
- ❌ Not "production-ready" without operational hardening
- ❌ Not "100% accurate" (accuracy depends on page structure, configuration, extraction method)
- ❌ Not a streaming/real-time system (it polls and orchestrates jobs)

---

## 2. Backend Architecture (Code Structure)

### Core Application (backend/app/)

#### **Entry Point: main.py**
- FastAPI application factory
- Lifespan management (startup/shutdown)
- Global state initialization (jobs_store, recycle_bin_store, CONFIG)
- Static file serving (frontend assets)
- Middleware stack (RBAC, rate limiting, CORS)
- Root routes: `/`, `/health`, `/ready`, `/metrics`

**Status:** ✅ IMPLEMENTED, startup gates production env validation

#### **Configuration: config.py**
- Pydantic settings management
- Reads environment variables
- Defines defaults for timeouts, limits, storage backend
- RBAC API keys (API_KEY, OPERATOR_API_KEY, ADMIN_API_KEY)

**Status:** ✅ IMPLEMENTED, centralized config exists

#### **Data Models: models.py**
- Pydantic models for:
  - JobCreate, Job, JobUpdate
  - FieldDefinition, Schema, SchemaDefinition
  - ExtractionResult, ExtractionRecord
  - Various response/request types

**Status:** ✅ IMPLEMENTED, type validation present

#### **Core Types: core_types.py**
- Shared enums and type definitions
- JobStatus, ExtractionMode, etc.

**Status:** ✅ IMPLEMENTED

---

### API Routers

#### **1. Jobs Router (routers/jobs.py)**
**Purpose:** Job lifecycle management

**Routes:**
- `POST /api/jobs` → Create job
- `GET /api/jobs` → List jobs
- `GET /api/jobs/{job_id}` → Get job details
- `DELETE /api/jobs/{job_id}` → Delete job
- `POST /api/jobs/{job_id}/cancel` → Cancel running job
- `POST /api/jobs/{job_id}/reclean` → Rerun cleaning on results
- `GET /api/jobs/{job_id}/results` → Get job results
- `GET /api/jobs/{job_id}/metadata` → Get job metadata
- `PUT /api/jobs/{job_id}/metadata` → Update metadata
- `POST /api/jobs/restore/{job_id}` → Restore from recycle bin
- `DELETE /api/jobs/hard-delete/{job_id}` → Permanent delete
- `POST /api/jobs/clear-recycle-bin` → Empty recycle bin

**Access Control:**
- Create/update/cancel: ADMIN or OPERATOR
- Delete: ADMIN only
- Read: Most routes allow authenticated access

**Status:** ✅ IMPLEMENTED, RBAC enforced

#### **2. Scraper Router (routers/scraper.py)**
**Purpose:** Scraper control, browser pool, telemetry

**Routes:**
- `GET /api/scraper/config` → Browser pool config
- `GET /api/scraper/browser` → Browser status
- `GET /api/scraper/stats` → Scraper statistics
- `GET /api/scraper/telemetry` → Telemetry data
- `DELETE /api/scraper/telemetry` → Clear telemetry
- `GET /api/scraper/memory/stats` → Memory usage
- `POST /api/scraper/diagnostics` → Run diagnostics
- `POST /api/scraper/trigger-selector-cleanup` → Cleanup selectors
- `POST /api/scraper/selector-learning` → Record learned selector
- Various other tuning/control endpoints

**Status:** ✅ IMPLEMENTED

#### **3. Operator Router (routers/operator.py)**
**Purpose:** System-wide operator mode and predictions

**Routes:**
- `GET /api/operator/mode` → Current operator mode
- `POST /api/operator/mode` → Change operator mode
- `GET /api/operator/dashboard` → Operator dashboard data
- `GET /api/operator/predictions` → Predictions across domains
- `GET /api/operator/predictions/{domain}` → Domain-specific predictions
- `GET /api/operator/health` → Operator health

**Status:** ✅ IMPLEMENTED, ADMIN only

#### **4. Exports Router (routers/exports.py)**
**Purpose:** Export job results in multiple formats

**Routes:**
- `GET /api/exports/job/{job_id}/json` → JSON export
- `GET /api/exports/job/{job_id}/csv` → CSV export
- `GET /api/exports/job/{job_id}/parquet` → Parquet export
- Possibly other formats

**Status:** ✅ IMPLEMENTED

#### **5. System Routes (main.py)**
**Purpose:** System-level operations (advanced features)

**Routes:**
- `GET /api/system/status` → System status
- `GET /api/system/storage/status` → Storage backend status
- `GET /api/system/topology` → Site topology data
- `GET /api/system/crystalline` → Crystalline structure (if applicable)
- `GET /api/system/export/knowledge` → Export domain knowledge
- `POST /api/system/merge/knowledge` → Merge knowledge bases
- `GET /api/system/search` → Search domains/results
- `GET /api/system/observability` → Observability data
- `GET /api/system/domain-policy` → Domain evolution policy
- `POST /api/system/scheduler/step` → Scheduler control
- `GET /api/system/replay/status` → Replay buffer status
- `GET /api/system/replay/chain` → Replay event chain
- `POST /api/system/refactor/compress` → Compress state

**Access Control:** Various (ADMIN, OPERATOR)

**Status:** ⚠️ IMPLEMENTED but many are advanced/experimental

#### **6. URL Analysis Route (main.py)**
**Purpose:** Preview/analyze single URL before job creation

**Route:**
- `POST /api/url/analyze` → Analyze URL with optional acquisition mode

**Status:** ✅ IMPLEMENTED

#### **7. Health & Metrics Routes**
- `GET /` → Root redirect
- `GET /health` → Health check (minimal)
- `GET /ready` → Readiness probe (with DB check)
- `GET /metrics` → Prometheus metrics

**Status:** ✅ IMPLEMENTED

---

### Storage Layer

#### **Storage Interface (storage_interface.py)**
**Abstract interface** defining:
- JobRepository interface (CRUD operations)
- StorageBackend interface
- Dependency injection via get_job_repository()

**Status:** ✅ IMPLEMENTED, clean abstraction

#### **SQLite Storage (sqlite_storage.py)**
**Implementation using SQLite**
- In-process, file-based database
- No external dependencies required
- Single-process usage (OK for single instance)

**Status:** ✅ IMPLEMENTED, tested

#### **PostgreSQL Storage (postgres_storage.py)**
**Implementation using PostgreSQL**
- Requires `psycopg2` dependency
- Supports distributed setup
- Connection pooling with SQLAlchemy

**Status:** ⚠️ IMPLEMENTED but tests skipped if Postgres unavailable

#### **Database Initialization**
- Migration scripts in `init-db/` (if they exist)
- Schema creation on startup (if using SQLAlchemy migrations)

**Status:** Unknown (requires inspection)

---

### Scraper & Extraction Pipeline

#### **Browser Pool (browser_pool.py)**
**Purpose:** Manage Playwright browser instances

**Functionality:**
- Pool of reusable browser instances
- Page context management
- Timeout enforcement
- Memory management

**Status:** ✅ IMPLEMENTED

#### **Network Capture (browser_network_capture.py)**
**Purpose:** Capture network requests/responses for analysis

**Features:**
- Intercept network events
- Extract response bodies
- Filter by content type
- Network payload analysis

**Status:** ✅ IMPLEMENTED, has logging for exceptions

#### **Extraction Orchestrator (extraction_orchestrator.py)**
**Purpose:** Coordinate extraction pipeline

**Pipeline stages:**
1. URL fetch (via browser)
2. DOM parsing
3. Selector-based extraction
4. Field validation
5. Data cleaning
6. Optional AI-powered extraction
7. Result deduplication/quality checking

**Status:** ✅ IMPLEMENTED

#### **Selector Learning (selector_learning.py)**
**Purpose:** Learn and optimize CSS selectors

**Features:**
- Track selector effectiveness
- Record user feedback on extracted data
- Adapt selectors based on feedback

**Status:** ✅ IMPLEMENTED, ⚠️ unclear if fully tested

#### **Field Validator (field_validator.py)**
**Purpose:** Validate extracted fields against schema

**Validation:**
- Type checking
- Required vs optional fields
- Format validation
- Precision/format constraints

**Status:** ✅ IMPLEMENTED

#### **Cleaning Engine (cleaning_engine.py)**
**Purpose:** Clean extracted data

**Functionality:**
- Remove whitespace
- Normalize values
- Handle special characters
- Apply transformation rules

**Status:** ✅ IMPLEMENTED

---

### Advanced/Adaptive Components

#### **Semantic Extraction (semantic_extraction.py)**
**Purpose:** Use LLM to extract data when selectors fail

**Mechanism:**
- Send page content to Groq API (optional)
- Parse LLM response to extract fields
- Fallback if LLM unavailable

**Status:** ✅ IMPLEMENTED, ⚠️ requires GROQ_API_KEY

#### **Topology Engine (topology_engine.py)**
**Purpose:** Model site structure/navigation

**Functionality:**
- Build site graph
- Identify nav patterns
- Plan crawl strategy
- Predict page types

**Status:** ✅ IMPLEMENTED, ⚠️ unclear if fully tested

#### **Domain Evolution Model (domain_evolution_model.py)**
**Purpose:** Track domain changes over time

**Functionality:**
- Monitor selector breakage
- Predict future breakage
- Suggest selector updates
- Track site version history

**Status:** ✅ IMPLEMENTED, ⚠️ unclear if fully tested

#### **Anti-Bot Engine (anti_bot_engine.py)**
**Purpose:** Detect and handle anti-bot measures

**Capabilities:**
- Detect rate limiting (HTTP 429)
- Detect bot detection (HTTP 403, etc.)
- Retry with backoff
- Session management
- Browser fingerprint rotation (if supported)

**Status:** ✅ IMPLEMENTED, ⚠️ incomplete coverage

#### **Failure Classification (failure_classification.py)**
**Purpose:** Categorize extraction failures

**Classification:**
- Network/connectivity failures
- Invalid selectors
- Rate limiting
- Anti-bot detection
- Server errors
- Timeout

**Status:** ✅ IMPLEMENTED

#### **Degradation Predictor (degradation_predictor.py)**
**Purpose:** Predict when extraction will break

**Features:**
- Analyze historical failures
- Predict future failures
- Suggest proactive fixes

**Status:** ✅ IMPLEMENTED, ⚠️ unclear if fully tested

---

### Job Orchestration

#### **Job Runner (services/job_runner.py)**
**Purpose:** Execute scraping jobs

**Workflow:**
1. Load job configuration
2. Fetch and parse URLs
3. Extract structured data
4. Validate results
5. Store results
6. Update job status

**Status:** ✅ IMPLEMENTED

#### **Worker/Queue (if exists)**
**Purpose:** Background job execution

**Technology:**
- Likely Python asyncio or Celery
- Queue backend (in-memory, Redis, or Postgres)

**Status:** ⚠️ Likely IMPLEMENTED but not fully validated

---

### Monitoring & Telemetry

#### **Metrics (metrics.py)**
**Purpose:** Collect and expose metrics

**Metrics:**
- Job count/status
- Extraction success rate
- Response time
- Error rates
- Resource usage

**Status:** ✅ IMPLEMENTED

#### **Event Dispatcher (event_dispatcher.py)**
**Purpose:** Emit events for observability

**Events:**
- Job lifecycle events
- Extraction events
- Error events
- Performance events

**Status:** ✅ IMPLEMENTED

#### **Benchmark Reporter (benchmark_reporter.py)**
**Purpose:** Report benchmark results

**Benchmarks:**
- Extraction accuracy
- Performance metrics
- Recovery effectiveness

**Status:** ✅ IMPLEMENTED, ⚠️ methodology unclear

#### **Telemetry (telemetry.py)**
**Purpose:** Collect and aggregate telemetry

**Data:**
- Job statistics
- Domain statistics
- Error summaries

**Status:** ✅ IMPLEMENTED

---

### Security & Authorization

#### **RBAC (utils/rbac.py)**
**Purpose:** Role-based access control

**Roles:**
- ADMIN — Full access
- OPERATOR — Job creation/control
- USER — Limited/read-only access

**Implementation:**
- API key-based (X-API-Key header or Bearer token)
- Timing-safe comparison (uses `secrets.compare_digest`)
- Configured via environment variables

**Routes Protected:**
- Job creation/deletion
- Operator mode
- System control routes
- Exports

**Status:** ✅ IMPLEMENTED, timing-safe comparison verified

#### **Rate Limiting (rate_limiter.py)**
**Purpose:** Prevent abuse

**Implementation:**
- Likely in-memory (token bucket or sliding window)
- Per-IP or per-key limiting

**Status:** ⚠️ IMPLEMENTED but single-process only

#### **CORS (config.py)**
**Purpose:** Control cross-origin requests

**Configuration:**
- CORS origins from environment (DATAFORGE_CORS_ORIGINS)
- Default: likely restrictive

**Status:** ✅ IMPLEMENTED

---

### Dashboard/Frontend

#### **Static Assets (frontend/)**
**Files:**
- `index.html` — Main page
- `app.js` — Application logic
- `styles.css` — Styling
- `dashboard/` — Dashboard components
- `js/` — Utilities

**Features:**
- Job creation UI
- Results display
- Metrics dashboard
- Operator mode controls

**Status:** ✅ PRESENT, ⚠️ production compatibility unknown

#### **CSP Compliance**
**Issue (from audit):**
- nginx.conf may enforce strict CSP
- Dashboard may use external CDN scripts (cdn.jsdelivr.net, cdn.tailwindcss.com)
- These may conflict

**Status:** ⚠️ POTENTIAL CONFLICT, documented in recent audit

---

## 3. Data Model

### Job Model
```
Job {
  id: str
  name: str
  urls: list[str]
  schema: Schema
  status: JobStatus (pending, running, completed, failed, cancelled)
  created_at: datetime
  started_at: datetime | None
  completed_at: datetime | None
  error: str | None
  extracted_records: int
  quality_score: float
  results: list[ExtractionRecord]
}
```

### Extraction Result Model
```
ExtractionResult {
  record_id: str
  job_id: str
  source_url: str
  extracted_data: dict[str, Any]
  confidence: float
  extraction_method: str (selector | ai | hybrid)
  validation_status: str (valid | invalid | partial)
  cleaned: bool
  extracted_at: datetime
}
```

### Schema Model
```
Schema {
  fields: dict[str, FieldDefinition]
}

FieldDefinition {
  name: str
  type: str (string, int, float, bool, date)
  required: bool
  description: str | None
}
```

---

## 4. Storage Backend Options

### SQLite (Default)
- **Pros:** No external dependencies, file-based, easy for dev
- **Cons:** Single-process, limited concurrency
- **Use case:** Development, single-instance deployment

### PostgreSQL
- **Pros:** Distributed, multi-process, transaction support
- **Cons:** External dependency, requires setup
- **Use case:** Production, multi-instance deployment

---

## 5. External Dependencies

### Required
- `fastapi` — Web framework
- `pydantic` — Data validation
- `sqlalchemy` — ORM (if using DB)
- `playwright` — Browser automation
- `pytest` — Testing

### Optional
- `psycopg2` — PostgreSQL support
- `groq` — LLM API for semantic extraction
- `redis` — Queue backend (if using)
- `celery` — Task queue (if using)

---

## 6. Job Lifecycle

### State Machine
```
NOT_STARTED
    ↓
RUNNING ← PAUSED (if pause is supported)
    ↓
COMPLETED (if all URLs extracted)
    ↓
ARCHIVED (moved to recycle bin or deleted)

OR

RUNNING
    ↓
FAILED (if critical error)
    ↓
ARCHIVED

OR

RUNNING
    ↓
CANCELLED (user-initiated)
    ↓
ARCHIVED
```

### Extraction Flow per URL
```
1. Fetch URL (with retries)
2. Parse HTML
3. Apply selectors → Extract data
4. If selectors fail AND AI enabled:
   - Send to LLM
   - Parse LLM response
5. Validate extracted fields
6. Clean data
7. Check for duplicates
8. Score quality
9. Store result
```

---

## 7. Deployment Architecture

### Docker Containers
1. **App** — FastAPI application (main.py)
2. **Worker** — Background job processor (if using async queue)
3. **Postgres** — Database (optional, for production)
4. **Nginx** — Reverse proxy, static file serving, CSP headers
5. **Prometheus** — Metrics collection
6. **Grafana** — Metrics dashboards

### Networking
```
External Traffic
    ↓
Nginx (reverse proxy, CSP, CORS)
    ↓
FastAPI App (health check, API routes)
    ↓
Storage (SQLite or Postgres)
    ↓
Browser Pool (Playwright)
    ↓
External Websites (scraping targets)
```

### Storage Options
```
SQLite (file-based, dev/small-scale)
    OR
Postgres (distributed, production)
```

---

## 8. Configuration & Secrets

### Environment Variables (from config.py)
```
# API Keys
DATAFORGE_API_KEY           (User-level access)
DATAFORGE_OPERATOR_API_KEY  (Operator-level access)
DATAFORGE_ADMIN_API_KEY     (Admin-level access)

# Storage
DATAFORGE_STORAGE_BACKEND   (sqlite or postgres)
DATAFORGE_DATABASE_URL      (PostgreSQL connection string)

# Timeouts & Limits
DATAFORGE_PER_URL_TIMEOUT_SECONDS       (default: 30)
DATAFORGE_MAX_JOB_RUNTIME_SECONDS       (default: 3600)
DATAFORGE_AI_STRUCTURING_TIMEOUT_SECONDS (default: 60)

# Browser & Scraping
DATAFORGE_BROWSER_POOL_SIZE             (default: 5)
DATAFORGE_MAX_DISCOVERY_URLS            (default: 100)

# Optional
GROQ_API_KEY                (for semantic extraction)
DATAFORGE_CORS_ORIGINS      (allowed domains)
DATAFORGE_ENV               (development or production)
```

### Secret Management
- **Development:** `.env` file (not committed)
- **Production:** Environment variables or secret manager
- **Validation:** `scripts/check_prod_env.py` validates on startup

---

## 9. API Security Model

### Authentication
- **Method:** API Key in header (X-API-Key) or Bearer token
- **Implementation:** Timing-safe comparison (`secrets.compare_digest`)
- **Not implemented:** JWT, OAuth2, mutual TLS, IP whitelisting

### Authorization
- **Method:** Role-based access control (RBAC)
- **Roles:** ADMIN, OPERATOR, USER
- **Scope:** Per-route enforcement via `require_role([...])`

### Production Hardening
- ⚠️ **Rate limiting:** Single-process only (not distributed)
- ⚠️ **Input validation:** Likely present but not audited
- ⚠️ **SSRF prevention:** Unknown (URL safety not verified)
- ⚠️ **Secret validation:** Startup check exists but unclear if comprehensive

---

## 10. Known Architectural Patterns

### Good Patterns
- ✅ Dependency injection (FastAPI Depends)
- ✅ Abstract storage interface (supports SQLite and Postgres)
- ✅ Async/await (FastAPI native async)
- ✅ Middleware for cross-cutting concerns (RBAC, rate limiting)
- ✅ Configuration management (Pydantic settings)

### Areas to Verify
- ⚠️ Error handling (silent exception handlers found in some modules)
- ⚠️ Logging (some operations may be silent)
- ⚠️ Testing (large suite but coverage/quality unclear)
- ⚠️ Benchmarks (methodology not clearly documented)

---

## 11. Component Verification Status

| Component | Status | Evidence |
|-----------|--------|----------|
| **FastAPI app** | ✅ | main.py exists, imports work |
| **API routes** | ✅ | ~40+ routes found and analyzed |
| **RBAC** | ✅ | rbac.py implements timing-safe comparison |
| **Storage interface** | ✅ | Abstract interface implemented |
| **SQLite storage** | ✅ | Module exists, testable |
| **PostgreSQL storage** | ⚠️ | Module exists, tests skipped if psycopg2 unavailable |
| **Browser pool** | ✅ | Module exists |
| **Extraction pipeline** | ✅ | Multiple extraction modules present |
| **Semantic extraction** | ✅ | Groq API integration exists |
| **Topology engine** | ✅ | Module exists, unclear if fully tested |
| **Domain evolution** | ✅ | Module exists, unclear if fully tested |
| **Metrics/telemetry** | ✅ | Modules exist |
| **Dashboard** | ✅ | Frontend directory exists |
| **Docker setup** | ✅ | docker-compose files present |
| **Worker/queue** | ⚠️ | Likely exists, not fully verified |
| **CI/CD** | ✅ | GitHub Actions workflow exists |

---

## 12. What The Project Actually Does (Summary)

### On API Request
1. User creates job with URL list and schema
2. Backend validates input
3. For each URL:
   - Fetches page via Playwright
   - Applies CSS selectors to extract data
   - If selectors fail, optionally calls Groq LLM
   - Validates and cleans extracted data
   - Stores in database
4. Exposes results via API (JSON, CSV, Parquet)
5. Provides metrics and observability

### What It Can Handle
- ✅ Static HTML pages with consistent structure
- ✅ JavaScript-rendered pages (via Playwright)
- ✅ Multiple URLs in a single job
- ✅ Custom schemas for different domains
- ✅ Partial extraction (some fields may be missing)
- ✅ Multiple extraction methods (selectors, AI, hybrid)

### What It Struggles With
- ❌ Dynamic/randomized layouts
- ❌ Heavily JavaScript-obfuscated content
- ❌ Aggressive anti-bot measures
- ❌ Authenticated content (requires session management)
- ❌ Infinite scroll / lazy loading (requires strategy)
- ❌ Varies by website configuration and schema accuracy

---

## 13. Summary Classification

| Layer | Status | Confidence |
|-------|--------|-----------|
| **Framework & Routing** | ✅ Verified | High |
| **Storage Interface** | ✅ Verified | High |
| **SQLite Implementation** | ✅ Verified | High |
| **PostgreSQL Support** | ⚠️ Partial | Medium |
| **Browser Automation** | ✅ Verified | High |
| **Extraction Pipeline** | ✅ Verified | High |
| **Selector Learning** | ✅ Partial | Medium |
| **Semantic Extraction** | ✅ Implemented | Medium |
| **Topology Engine** | ✅ Implemented | Low |
| **Domain Evolution** | ✅ Implemented | Low |
| **RBAC & Security** | ✅ Implemented | High |
| **Rate Limiting** | ⚠️ Limited | Medium |
| **Metrics & Telemetry** | ✅ Implemented | Medium |
| **Dashboard** | ⚠️ Present | Unknown |
| **Docker & Deployment** | ✅ Implemented | Medium |
| **Testing** | ✅ Large | Unknown (coverage/quality unclear) |

---

**Architecture Reality Confirmed:** The project is a functioning web extraction system with good foundational architecture but significant unknowns in advanced features, production hardening, and test coverage quality.

**Next:** Deliverable 3 (Claims Audit) will compare this reality against what the documentation claims.
