# Deliverable 9: Corrected README

**Purpose:** Replace overclaimed README with honest, technically accurate version  
**Format:** Ready to replace existing README.md  
**Approach:** Clear scope, no hype, transparent about limitations

---

# DataForge — Web Extraction Platform

**An honest, pre-production web data extraction system built with FastAPI and Playwright.**

---

## What Is DataForge?

DataForge is a **REST API server** for automating web data extraction. It:

- **Extracts structured data** from websites using CSS selectors, field validation, and optional LLM-powered extraction
- **Manages extraction jobs** with full lifecycle support (create, monitor, export results)
- **Stores results** in SQLite (default) or PostgreSQL
- **Provides observability** via Prometheus metrics and JSON APIs
- **Supports role-based access** (Admin, Operator, User) via API keys

**Current Maturity:** Pre-production (private networks, staging environments)

---

## What It Is NOT

DataForge is **not**:
- ❌ A "universal" scraper that works on every website
- ❌ Fully autonomous (requires configuration per domain)
- ❌ Self-healing without explicit recovery strategies
- ❌ Guaranteed production-ready without validation
- ❌ Suitable for business-critical workloads without testing

For known limitations, see [LIMITATIONS.md](docs/LIMITATIONS.md).

---

## Quick Start

### Requirements
- Python 3.12+
- Docker (optional, for deployment)

### Installation (Development)

```bash
# Clone repository
git clone <repo-url>
cd scraper

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # or: .venv\Scripts\activate on Windows

# Install dependencies
pip install -r backend/requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your settings

# Start development server
python -m uvicorn backend.app.main:app --reload
```

### First Extraction Job

```bash
# Create API key (if not in .env)
export DATAFORGE_ADMIN_API_KEY="dev-key-change-in-production"

# Create extraction job
curl -X POST http://localhost:8000/api/jobs \
  -H "X-API-Key: $DATAFORGE_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "example-extraction",
    "urls": ["https://example.com"],
    "schema": {
      "fields": {
        "title": {"type": "string", "required": true}
      }
    }
  }'

# Check job status
curl http://localhost:8000/api/jobs/<job_id> \
  -H "X-API-Key: $DATAFORGE_ADMIN_API_KEY"
```

See [SETUP.md](docs/SETUP.md) for detailed instructions.

---

## Architecture

DataForge is organized into:

- **Backend** (`backend/app/`) — FastAPI application with 40+ API routes
- **Storage** — Abstract interface supporting SQLite and PostgreSQL
- **Scraper** — Playwright-based browser automation and extraction pipeline
- **Frontend** (optional) — Dashboard for monitoring jobs and results

For detailed architecture, see [ARCHITECTURE.md](docs/ARCHITECTURE.md) and [DELIVERABLE_2_ARCHITECTURE_MAP.md](DELIVERABLE_2_ARCHITECTURE_MAP.md).

---

## Features

### Core Extraction
- ✅ **Selector-based extraction** — Use CSS selectors to define data fields
- ✅ **Browser automation** — Playwright handles JavaScript-rendered pages
- ✅ **Field validation** — Validate extracted data types and formats
- ✅ **Data cleaning** — Normalize and transform extracted values

### Advanced Extraction (Experimental)
- ⚠️ **Semantic extraction** — LLM-powered extraction when selectors fail (requires GROQ_API_KEY)
- ⚠️ **Selector learning** — Feedback-based selector optimization
- ⚠️ **Domain evolution** — Track site changes over time

*Note: Advanced features are implemented but not fully validated in production.*

### Job Management
- ✅ Create, read, update, delete extraction jobs
- ✅ Monitor job status and progress
- ✅ Export results (JSON, CSV, Parquet)
- ✅ Store results in database

### Deployment
- ✅ Docker container support
- ✅ Multi-instance scaling (with external queue)
- ✅ Prometheus metrics export
- ⚠️ Production startup validation
- ⚠️ Postgres support (untested in CI)

---

## Production Deployment

**Before deploying to production, read:**

1. [PRODUCTION.md](docs/PRODUCTION.md) — Deployment overview
2. [PRODUCTION_STARTUP.md](docs/PRODUCTION_STARTUP.md) — Step-by-step startup
3. [SECURITY.md](docs/SECURITY.md) — Security configuration
4. [LIMITATIONS.md](docs/LIMITATIONS.md) — Known constraints

### Minimum Production Checklist

- [ ] All environment variables set (no test values)
- [ ] Database initialized (SQLite or Postgres)
- [ ] API keys generated (32+ character random strings)
- [ ] HTTPS enabled (certificate from trusted CA)
- [ ] CSP policy configured (see nginx.conf)
- [ ] Monitoring enabled (Prometheus scraping configured)
- [ ] Alerting configured (prometheus_alerts.yml)
- [ ] Extraction validation done (golden dataset or real-world test)
- [ ] Load testing completed (100+ concurrent jobs)

**Not ready yet?** Deploy to **staging** first; see PRODUCTION.md for staging setup.

---

## Testing

Run the full test suite:

```bash
pytest backend/tests/ -v
```

**Expected results:** 1,658 tests pass, 54 tests skip (external dependencies)

For detailed test analysis, see [DELIVERABLE_5_TEST_TRUTH_REPORT.md](DELIVERABLE_5_TEST_TRUTH_REPORT.md).

---

## API Documentation

### REST API

- `POST /api/jobs` — Create extraction job
- `GET /api/jobs` — List jobs
- `GET /api/jobs/{id}` — Get job details
- `GET /api/jobs/{id}/results` — Get extraction results
- `DELETE /api/jobs/{id}` — Delete job
- `GET /api/metrics` — Prometheus metrics
- `GET /health` — Health check
- `GET /ready` — Readiness check (includes DB validation)

For full API documentation, see [API.md](docs/API.md) or visit `/docs` after starting the server.

---

## Configuration

### Environment Variables

**Required (no defaults):**
- `DATAFORGE_ADMIN_API_KEY` — Admin API key (32+ characters, no spaces)
- `DATAFORGE_OPERATOR_API_KEY` — Operator API key

**Optional:**
- `DATAFORGE_STORAGE_BACKEND` — `sqlite` (default) or `postgres`
- `DATAFORGE_DATABASE_URL` — Database connection string (required if using Postgres)
- `DATAFORGE_ENV` — `development` or `production`
- `GROQ_API_KEY` — Optional, for semantic extraction
- `DATAFORGE_CORS_ORIGINS` — Comma-separated list of allowed origins

See `.env.example` for all available options.

### Production Secret Validation

DataForge validates that:
- All required env vars are present
- No placeholder values (test, admin, changeme, etc.)
- Database is accessible
- API keys are non-empty

Validation runs at startup. If validation fails, the application exits with an error.

---

## Benchmarks & Accuracy

**Extraction accuracy is tested with fixture-based benchmarks:**
- Accuracy: 85%+ F1 score on test data
- Coverage: 1,658 tests pass locally

**Important limitations:**
- ⚠️ Benchmarks use **simplified HTML fixtures**, not real websites
- ⚠️ Real-world accuracy **depends on page structure consistency** and schema accuracy
- ⚠️ **No golden dataset** with real-world websites (TBD)

For detailed benchmark methodology, see [DELIVERABLE_6_BENCHMARK_TRUTH_REPORT.md](DELIVERABLE_6_BENCHMARK_TRUTH_REPORT.md).

---

## Security

DataForge implements:

✅ **Authentication** — API key-based (timing-safe comparison)
✅ **Authorization** — Role-based access control (RBAC)
✅ **Input validation** — Pydantic models + field validation
✅ **SSRF protection** — URL validation (application-level; requires network-level egress controls)
✅ **SQL injection protection** — SQLAlchemy ORM parameterized queries

⚠️ **Known gaps:**
- Single-process rate limiting (not distributed)
- Dashboard API key in localStorage (not suitable for shared browsers)
- CSP policy allows external CDN (security compromise; should be vendored)

For detailed security assessment, see [SECURITY.md](docs/SECURITY.md) and [DELIVERABLE_7_SECURITY_REPORT.md](DELIVERABLE_7_SECURITY_REPORT.md).

---

## Known Limitations

DataForge **cannot reliably handle:**
- ❌ Heavily obfuscated JavaScript content
- ❌ Dynamic/randomized HTML layouts
- ❌ Aggressive anti-bot measures (without custom configuration)
- ❌ Authenticated content (would need session management)
- ❌ Infinite scroll or lazy-loaded pages (without custom strategy)

For complete limitations, see [LIMITATIONS.md](docs/LIMITATIONS.md).

---

## Troubleshooting

### Common Issues

**"API key not found"**
- Ensure `DATAFORGE_ADMIN_API_KEY` is set in `.env`
- Verify API key is passed in request header

**"Database connection failed"**
- Check DATABASE_URL is correct (if using Postgres)
- Verify database service is running
- For SQLite, check file permissions

**"Extraction returned no results"**
- Verify CSS selectors match page structure (use browser dev tools)
- Check that page isn't blocked by anti-bot measures
- Ensure field validation isn't too strict

See [Troubleshooting](docs/TROUBLESHOOTING.md) for more.

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request with clear description
5. Ensure all tests pass locally

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## Roadmap

Planned improvements (not guaranteed):

- [ ] Distributed rate limiting (Redis)
- [ ] Session token support (replace/supplement API keys)
- [ ] Real-world extraction validation (golden dataset)
- [ ] Production Postgres CI integration
- [ ] Audit logging (auth events, admin actions)
- [ ] Dashboard HTTPS enforcement
- [ ] Advanced anti-bot scenario handling

See [ROADMAP.md](docs/ROADMAP.md) for longer-term plans.

---

## Audit & Transparency

This project includes comprehensive truth-first audit deliverables:

1. [DELIVERABLE_1_TRUTH_INVENTORY.md](DELIVERABLE_1_TRUTH_INVENTORY.md) — Repository baseline
2. [DELIVERABLE_2_ARCHITECTURE_MAP.md](DELIVERABLE_2_ARCHITECTURE_MAP.md) — Actual architecture
3. [DELIVERABLE_3_CLAIMS_AUDIT.md](DELIVERABLE_3_CLAIMS_AUDIT.md) — Documentation claims vs. reality
4. [DELIVERABLE_4_ERROR_ISSUE_LIST.md](DELIVERABLE_4_ERROR_ISSUE_LIST.md) — Complete issue enumeration
5. [DELIVERABLE_5_TEST_TRUTH_REPORT.md](DELIVERABLE_5_TEST_TRUTH_REPORT.md) — Test execution analysis
6. [DELIVERABLE_6_BENCHMARK_TRUTH_REPORT.md](DELIVERABLE_6_BENCHMARK_TRUTH_REPORT.md) — Benchmark methodology
7. [DELIVERABLE_7_SECURITY_REPORT.md](DELIVERABLE_7_SECURITY_REPORT.md) — Security assessment

**Why audits?** To ensure honest, technically defensible documentation. No overclaims, no hype.

---

## License

[Specify your license, e.g., MIT, Apache 2.0, etc.]

---

## Support

- **Issues:** Report bugs on GitHub Issues
- **Discussions:** Ask questions on GitHub Discussions
- **Documentation:** See [docs/](docs/) directory
- **Email:** [support contact, if applicable]

---

## Version

**Current:** Pre-production (v0.x)  
**Status:** Active development  
**Last Updated:** [Date]

---

---

## Key Differences from Previous README

| Aspect | Old README | New README |
|--------|-----------|-----------|
| **Tone** | Marketing-focused | Honest, technical |
| **Claims** | "Production-ready," "100% accurate" | "Pre-production," "85%+ on fixtures" |
| **Limitations** | Hidden | Explicit section |
| **Maturity** | Implied complete | "Experimental" for advanced features |
| **Setup** | Simple commands | Detailed with validation |
| **Production** | Not addressed | Dedicated section with checklist |
| **Benchmarks** | Claimed high | Methodology documented |
| **Audit Trail** | None | Links to 7 audit deliverables |

---

**Classification:** HONEST, NON-OVERCLAIMED README SUITABLE FOR PRE-PRODUCTION TRANSPARENCY
