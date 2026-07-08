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
#   make logs          Tail logs
#   make shell         Open shell in running container
#   make test          Run tests inside container
#   make lint          Run linters inside container
#   make prod          Start production stack
#   make clean         Remove containers, volumes, and images
# =============================================================================

.DEFAULT_GOAL := help

DC := docker compose
DCF := docker compose -f docker-compose.prod.yml
SERVICE := dataforge

.PHONY: help build up down logs shell test lint prod clean ps

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

shell: ## Open bash in the app container
	$(DC) exec $(SERVICE) bash

exec: ## Run a command in the app container (usage: make exec CMD="python -c ...")
	$(DC) exec $(SERVICE) $(CMD)

# ─── Testing ────────────────────────────────────────────────────────────────

test: ## Run all tests (excluding API-dependent)
	$(DC) exec $(SERVICE) python -m pytest -q --tb=short -k "not test_scrape_url_end_to_end_multiple_records"

test-all: ## Run all tests (including API-dependent, requires GROQ_API_KEY)
	$(DC) exec $(SERVICE) python -m pytest -q --tb=short

test-file: ## Run tests in a specific file (usage: make test-file FILE=test_foo.py)
	$(DC) exec $(SERVICE) python -m pytest -q --tb=short backend/tests/$(FILE)

# ─── Linting ────────────────────────────────────────────────────────────────

lint: ## Run all linters
	$(DC) exec $(SERVICE) python -m pyflakes backend/app backend/tests

mypy: ## Run mypy type checker
	$(DC) exec $(SERVICE) python -m mypy backend/app --ignore-missing-imports

lint-all: lint mypy ## Run pyflakes + mypy

# ─── Production ─────────────────────────────────────────────────────────────

prod: ## Start production stack
	$(DCF) up -d

prod-down: ## Stop production stack
	$(DCF) down

prod-logs: ## Tail production logs
	$(DCF) logs -f

# ─── Cleanup ────────────────────────────────────────────────────────────────

clean: ## Remove containers, volumes, and dangling images
	$(DC) down -v --remove-orphans 2>/dev/null || true
	docker image prune -f 2>/dev/null || true
	@echo "Cleaned up development resources."

clean-all: clean ## Remove everything including production resources
	$(DCF) down -v --remove-orphans 2>/dev/null || true
	docker system prune -af --volumes 2>/dev/null || true
	@echo "Cleaned up all Docker resources."

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
