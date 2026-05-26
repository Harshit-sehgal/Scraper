# Release Notes — DataForge Scraper v1.0.0-hardened

DataForge Scraper **`v1.0.0-hardened`** is a certified SRE release candidate, specifically hardened against security vulnerabilities, runtime pathing errors, configuration syntax regressions, and release-process gaps.

This staging candidate is **officially frozen**. Do not apply any further patches unless a post-deployment staging gate fails.

---

## 🛠️ Summary of Changes

### 1. Security & Architectural Hardening
* **Unsafe eval() Removal**: Completely eliminated unsafe dynamic string evaluations inside `backend/app/topology_state.py`. Replaced with safe AST evaluation (`ast.literal_eval()`) coupled with strict 2-tuple validation checks for serialized keys.
* **CORS Allowlist Security**: Set up tight browser origin mappings in Nginx, allowing only localhost/loopback by default, and provided clear, commented configuration templates inside `nginx.conf` for production domain migration.
* **metrics Endpoint Leak Protection**: Nginx has been aligned to return an immediate `404` publicly on requests to `/metrics`, completely eliminating the risk of internal timed data, queue backlog, or service timings leaking through cloud load balancers. Prometheus continues to securely scrape internal container metrics directly at `dataforge:8000/metrics`.
* **Safe Request Body Limits**: Tightened global Nginx request body limits to `10m` to align with the application limit and prevent oversized payload SRE exhaustion.
* **Git Hygiene**: Cleaned out committed SQLite databases and JSON lock artifacts from tracking, and defined precise `.gitignore` rules targeting sqlite and json locks without ignoring structural dependency locks (such as `poetry.lock`).

### 2. CI/CD & SRE Validation Gates
* **Expanded GHA Triggers**: Automated GitHub Actions runs on pushes to `main`, `fix/deep-scan-hardening`, and `v*` tags.
* **CI Config Syntax Validation**: Added automated containerized syntax verification for Nginx and Prometheus configurations in GHA runners:
  ```bash
  nginx -t
  promtool check config
  ```
* **Repeatable SRE Quick Check Script**: Created and automated `scripts/sre_quick_check.sh` inside CI. It compiles all source directories, verifies FastAPI path imports, checks startup script bash syntax, scans for `eval()` regressions, runs the `architecture_validator.py`, and executes the complete `pytest` suite.
* **Declared Dependencies**: Formally declared `PyYAML>=6.0.0` and `pyflakes>=3.2.0` under development dependencies in `requirements-dev.txt` to prevent GHA runner script failures.

---

## 📊 Verification & Test Integrity

* **Python Compilation**: 100% of Python sources compile cleanly (`compileall`).
* **Source Code Lints**: Zero warnings reported via `pyflakes app tests`.
* **Import Boundaries check**: Zero imports of test logic or mock fixtures inside `backend/app/` production code.
* **SSRF & DNS-Independent Testing**: Mapped mock DNS resolutions (retaining public vs private IP assertions) to keep the production security test suite robustly executing in offline/sandboxed SRE testing containers.
* **Telemetry Regression Coverage**: Comprehensive API metrics and Bearer token auth validation inside `test_metrics.py`.
* **Full Test Suite Results**:
  ```
  1584 passed, 37 skipped, 1 warning in 115.68s (100% success)
  ```

---

## 🚀 Deployment Prerequisites & Staging Verification

### 1. Prerequisites (Prior to Deploy)
1. **Configure CORS**: Open `nginx.conf` and uncomment/add your active production domains inside the CORS origin map:
   ```nginx
   "https://yourdomain.com" $http_origin;
   ```
2. **Setup Metrics Token**: Ensure the environment variable `METRICS_TOKEN` is defined on your staging host to protect raw `/metrics` telemetry.

### 2. Checkout & Launch
Deploy the exact release tag to your staging host:
```bash
git checkout v1.0.0-hardened
docker compose -f docker-compose.prod.yml up -d
```

### 3. Post-Deployment Verification
Verify liveness and boundaries:
- `GET /health` -> Expects `200`
- `GET /ready` -> Expects `200` (durable storage connection alive)
- `GET /metrics` -> Expects `404` from Nginx (public-blocked)
- `GET /metrics` on internal port `8000` -> Expects `200` (internal scraping allowed)
