# =============================================================================
# DataForge Scraper — Makefile
# =============================================================================
# Common development, test, and deployment commands.
#
# Usage:
#   make help          Show this help
#   make build         Build Docker image
#   make up            Start development stack
#   make down          Stop development stack
#   make logs          Tail all logs
#   make shell         Open bash in running container
#   make test          Run tests inside container
#   make lint          Run ruff lint + format inside container
#   make mypy          Run mypy type checker
#   make boundary      Run the research-shell boundary check (CI invariant)
#   make deps-check    Validate pyproject.toml dependency bounds
#   make lint-all      Run lint + mypy + boundary + deps-check
#   make validate      Run quick local validation (does not require Docker)
#   make prod          Start production stack
#   make clean         Remove containers, volumes, and dangling images
# =============================================================================

.DEFAULT_GOAL := help

DC := docker compose
DCF := docker compose -f docker-compose.prod.yml
SERVICE := dataforge

# Guard: check that the Docker container is running before exec-ing into it.
# Targets that use docker compose exec should depend on _need-container.
_need-container:
	@$(DC) ps -q $(SERVICE) 2>/dev/null | grep -q . || \
		{ echo "Error: $(SERVICE) container is not running. Run 'make up' first, or use 'make validate' for local checks." >&2; exit 1; }

.PHONY: help build up down logs shell test lint prod clean ps boundary deps-check lint-all validate validate-full validate-backend validate-frontend validate-security doctor api-docs api-docs-check test-coverage test-coverage-report test-flaky test-reliability _need-container

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Build ──────────────────────────────────────────────────────────────────

build: ## Build Docker image (dev target)
	$(DC) build

build-prod: ## Build Docker image (production target)
	DOCKER_BUILDKIT=1 docker build --target production -t dataforge:latest .

# ─── Development ────────────────────────────────────────────────────────────

up: ## Start development stack (detached)
	$(DC) up -d
	@echo "API:       http://localhost:${PORT:-8000}"
	@echo "Dashboard: http://localhost:${PORT:-8000}/app"
	@echo "Docs:      http://localhost:${PORT:-8000}/docs"

down: ## Stop development stack
	$(DC) down

restart: down up ## Restart development stack

logs: ## Tail all logs
	$(DC) logs -f $(filter-out $@,$(MAKECMDGOALS))

ps: ## List containers
	$(DC) ps

# ─── Container Interaction ──────────────────────────────────────────────────

shell: _need-container ## Open bash in the app container
	$(DC) exec $(SERVICE) bash

exec: _need-container ## Run a command in the app container (usage: make exec CMD="python -c ...")
	$(DC) exec $(SERVICE) $(CMD)

# ─── Testing ────────────────────────────────────────────────────────────────

test: _need-container ## Run all tests (excluding flaky live-network end-to-end)
	# Excludes test_scrape_url_end_to_end_multiple_records: that test
	# hits a live target and is environment-flaky in CI. Use
	# `make test-all` to include it (requires a reachable network).
	$(DC) exec $(SERVICE) python -m pytest -q --tb=short -k "not test_scrape_url_end_to_end_multiple_records"

test-all: _need-container ## Run all tests (including API-dependent, requires GROQ_API_KEY)
	$(DC) exec $(SERVICE) python -m pytest -q --tb=short

test-file: _need-container ## Run tests in a specific file (usage: make test-file FILE=test_foo.py)
	$(DC) exec $(SERVICE) python -m pytest -q --tb=short backend/tests/$(FILE)

test-coverage: _need-container ## Run tests with coverage report
	$(DC) exec $(SERVICE) python -m pytest --cov=backend/app --cov-report=term-missing --cov-report=html:coverage_html --cov-fail-under=60 -q --tb=short

test-coverage-report: _need-container ## Generate and open coverage HTML report
	$(DC) exec $(SERVICE) python -m pytest --cov=backend/app --cov-report=html:coverage_html --cov-fail-under=60 -q --tb=short
	@echo "Coverage report generated at coverage_html/index.html"

test-flaky: _need-container ## Run tests 3 times to detect flaky tests
	$(DC) exec $(SERVICE) python -m pytest --count=3 --timeout=30 -q --tb=short -x

test-reliability: _need-container ## Run full test suite with reliability checks
	$(DC) exec $(SERVICE) python -m pytest --timeout=30 -q --tb=short --reruns=2 --reruns-delay=1

test-telegram: ## Print the current Telegram notifier status
	@PYTHONPATH=backend python3 scripts/send_telegram.py --status || true
	@echo "(exit code 0 = fully configured; non-zero = disabled or misconfigured)"

test-telegram-ping: ## Send a one-off test message via the configured bot
	@PYTHONPATH=backend python3 scripts/send_telegram.py --enable \
		"🔔 DataForge test ping — sent at $(date -u +%FT%TZ)"

test-telegram-summary: ## Send a fake pass/fail summary via the bot (override RESULT/COUNT via env)
	@PYTHONPATH=backend python3 scripts/send_telegram.py --enable --summary \
		--suite "manual-summary" --result "$${RESULT:-PASSED}" \
		--passed "$${PASSED:-120}" --failed "$${FAILED:-0}" --skipped "$${SKIPPED:-3}"

test-notify: _need-container ## Run all tests with Telegram notifications enabled
	# Convenience wrapper: forces TELEGRAM_ENABLED=true for this run so the
	# pytest conftest hooks send start/end/failure notifications.
	$(DC) exec -e TELEGRAM_ENABLED=true $(SERVICE) \
		python -m pytest -q --tb=short -k "not test_scrape_url_end_to_end_multiple_records"

# ─── CI Pipeline Helpers ───────────────────────────────────────────────────

ci-check-python: ## Check Python version compatibility (CI gate)
	@python3 --version | grep -q "3\.12" || { echo "❌ Python 3.12 required"; exit 1; }
	@echo "✅ Python 3.12"

ci-install-all: ## Install all CI dependencies (Python + Node + Playwright)
	python3 -m pip install --upgrade pip
	pip install -e ".[dev]"
	pip install types-beautifulsoup4 types-openpyxl types-requests types-html5lib types-webencodings
	npm ci
	python3 -m playwright install chromium --with-deps 2>/dev/null || true

ci-validate-local: ## Run the full local validation matching CI gates
	python3 scripts/validate_local.py --full

ci-status: ## Print CI workflow status (requires GitHub CLI)
	@gh run list --workflow=ci.yml --branch=main --limit=3 --json headBranch,status,conclusion,createdAt

ci-open-latest: ## Open the latest CI run in browser
	@gh run view --workflow=ci.yml --web 2>/dev/null || \
		echo "Run: gh run list --workflow=ci.yml --limit=1"

# ─── Linting ────────────────────────────────────────────────────────────────

lint: _need-container ## Run all linters (ruff lint + format)
	$(DC) exec $(SERVICE) python -m ruff check backend/app backend/tests
	$(DC) exec $(SERVICE) python -m ruff format --check backend/app backend/tests

mypy: _need-container ## Run mypy type checker
	$(DC) exec $(SERVICE) python -m mypy backend/app backend/tests --check-untyped-defs

boundary: ## Run the research-shell boundary check (CI invariant)
	PYTHONPATH=backend python3 scripts/check_research_boundary.py

deps-check: ## Validate pyproject.toml dependency bounds (single source of truth)
	python3 scripts/validate_dependency_bounds.py

lint-all: lint mypy boundary deps-check ## Run full lint + type + boundary + deps suite

# Local validation with bounded logs (does not require Docker).
# `make validate` is the default quality gate and runs the full suite so
# that no "quick passed" / "full failed" gap can sneak in locally. If
# you only want the bounded gate (faster, no full backend pytest / ruff
# / bandit), call `validate-quick` explicitly. Both write fresh
# artifacts under ``artifacts/validation/`` and ``artifacts/validation/runs/``.
validate: ## Run full local validation and write artifacts/validation logs (default gate)
	python3 scripts/validate_local.py --full

validate-quick: ## Run quick local validation only (subset of the full gate)
	python3 scripts/validate_local.py --quick

validate-full: ## Alias for ``validate`` — explicit form for clarity
	python3 scripts/validate_local.py --full

validate-backend: ## Run backend validation and full backend tests
	python3 scripts/validate_local.py --backend

validate-frontend: ## Run frontend install, tests, and lint
	python3 scripts/validate_local.py --frontend

validate-security: ## Run local security-oriented checks
	python3 scripts/validate_local.py --security

# ─── Bootstrap gate (Phase 0) ───────────────────────────────────────────────

doctor: ## Run the repository health check (Python, venv, lockfiles, Playwright, pytest probe)
	python3 scripts/doctor.py

doctor-json: ## Emit doctor output as JSON for CI consumption
	python3 scripts/doctor.py --json

# ─── API docs split (Phase 0, C1) ───────────────────────────────────────────

api-docs: ## Regenerate stable vs experimental API inventory docs
	python3 scripts/route_inventory_split.py --write

api-docs-check: ## Diff-check stable API inventory without writing
	python3 scripts/route_inventory_split.py > /dev/null

# ─── Production ─────────────────────────────────────────────────────────────

prod: ## Start production stack
	$(DCF) up -d

prod-down: ## Stop production stack
	$(DCF) down

prod-logs: ## Tail production logs
	$(DCF) logs -f

# ─── Docker Smoke ─────────────────────────────────────────────────────────

docker-smoke: ## Verify production image builds and /ready responds
	@echo "=== Docker Smoke Test ==="
	@echo "Building production image..."
	docker build --target production -t dataforge:smoke-test .
	@echo "Build complete."
	@echo "Starting smoke container..."
	@docker rm -f dataforge-smoke 2>/dev/null || true
	docker run -d --name dataforge-smoke \
		-e DATAFORGE_ENV=production \
		-e DATAFORGE_STORAGE_BACKEND=sqlite \
		-e DATAFORGE_SMOKE_TEST_MODE=true \
		-e DATAFORGE_ALLOWED_INTERNAL_HOSTS=localhost,127.0.0.1 \
		-p 8001:8000 \
		dataforge:smoke-test
	@echo ""
	@echo "Waiting for /ready endpoint..."
	@sleep 5
	@for i in 1 2 3 4 5; do \
		status=$$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/ready 2>/dev/null || echo "000"); \
		if [ "$$status" = "200" ]; then \
			echo "SMOKE PASS: /ready returned 200"; \
			docker rm -f dataforge-smoke > /dev/null 2>&1; \
			docker image rm dataforge:smoke-test > /dev/null 2>&1 || true; \
			exit 0; \
		fi; \
		echo "Waiting... (attempt $$i, status=$$status)"; \
		sleep 3; \
	done; \
	echo "SMOKE FAIL: /ready did not return 200 within timeout"; \
	docker logs dataforge-smoke --tail 20 2>/dev/null || true; \
	docker rm -f dataforge-smoke > /dev/null 2>&1; \
	docker image rm dataforge:smoke-test > /dev/null 2>&1 || true; \
	exit 1

.PHONY: docker-smoke

# ─── Cleanup ────────────────────────────────────────────────────────────────

clean: ## Remove containers, volumes, and dangling images
	$(DC) down -v --remove-orphans 2>/dev/null || true
	docker image prune -f 2>/dev/null || true
	@echo "Cleaned up development resources."

clean-all: clean ## Remove everything including production resources
	$(DCF) down -v --remove-orphans 2>/dev/null || true
	docker system prune -af --volumes 2>/dev/null || true
	@echo "Cleaned up all Docker resources."

clean-local: ## Remove gitignored runtime artifacts (replay buffer, caches, logs)
	rm -rf backend/data/replay_buffer/
	rm -rf backend/data/benchmarks/
	rm -rf backend/data/checkpoints/
	rm -rf backend/data/governance/
	rm -rf backend/data/results/
	rm -rf backend/logs/
	find . -type d -name __pycache__ -not -path './.git/*' -exec rm -rf {} + 2>/dev/null
	find . -type f -name '*.pyc' -not -path './.git/*' -delete 2>/dev/null
	@echo "Cleaned local runtime artifacts (replay buffer, caches, logs, .pyc files)."

# ─── Utility ────────────────────────────────────────────────────────────────

health: ## Check container health
	@echo "App:"
	$(DC) ps --filter "status=running" --format "table {{.Names}}\t{{.Status}}"
	@echo ""
	@echo "Ports:"
	@echo "  Development: http://localhost:${PORT:-8000}"
	@echo "  API Docs:    http://localhost:${PORT:-8000}/docs"

# Allow passing arguments to targets
%:
	@:
