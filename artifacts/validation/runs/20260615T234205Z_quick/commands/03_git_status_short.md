# git_status_short

- status: passed
- command: `git status --short`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-15T23:42:05.931256+00:00
- end_time: 2026-06-15T23:42:05.937909+00:00
- duration_seconds: 0.01
- exit_code: 0
- timeout_seconds: 30
- required: false
- redaction_applied: false

## stdout

```text
 M .env.production.example
 M .github/workflows/ci.yml
 M AGENTS.md
 M Makefile
 M artifacts/audit/FINAL_EVIDENCE_REPORT.md
 M artifacts/audit/ROUTE_AUTH_MATRIX.json
 M artifacts/audit/ROUTE_INVENTORY.json
 M artifacts/validation/commands/00_required_paths.md
 M artifacts/validation/commands/01_python_version.md
 M artifacts/validation/commands/02_git_commit.md
 D artifacts/validation/commands/03_git_status_short.md
 D artifacts/validation/commands/04_node_version.md
 D artifacts/validation/commands/05_npm_version.md
 D artifacts/validation/commands/06_compileall.md
 D artifacts/validation/commands/07_architecture_validator.md
 D artifacts/validation/commands/08_research_boundary.md
 D artifacts/validation/commands/09_dependency_bounds.md
 D artifacts/validation/commands/10_url_and_research_smoke_tests.md
 D artifacts/validation/commands/11_p0_regression_tests.md
 M artifacts/validation/latest_summary.json
 M artifacts/validation/latest_summary.md
 M backend/.bandit
 M backend/app/auth/session.py
 M backend/app/config/_jobs.py
 M backend/app/config/_security.py
 M backend/app/extraction_orchestrator.py
 M backend/app/failure_explainer.py
 M backend/app/job_store.py
 M backend/app/main.py
 M backend/app/middlewares.py
 M backend/app/models.py
 M backend/app/pagination_executor.py
 M backend/app/routers/auth_profiles.py
 M backend/app/routers/exports.py
 M backend/app/routers/jobs_write.py
 M backend/app/routers/scraper.py
 M backend/app/routers/workflow.py
 M backend/app/scraper.py
 M backend/app/selector_engine.py
 M backend/app/strategy_evolution.py
 M backend/app/url_analyzer.py
 M backend/app/url_safety.py
 M backend/app/utils/encryption.py
 M backend/app/utils/usage_ledger.py
 M backend/app/visualization.py
 M backend/app/workflow_executor.py
 M backend/app/zero_result_classifier.py
 M backend/benchmarks/benchmark_report.json
 M backend/benchmarks/test_benchmark_enforceable.py
R  backend/tests/manual_test_api.py -> backend/manual/manual_api.py
R  backend/tests/manual_test_app_scrape.py -> backend/manual/manual_app_scrape.py
R  backend/tests/manual_test_chennai.py -> backend/manual/manual_chennai.py
R  backend/tests/manual_test_extract.py -> backend/manual/manual_extract.py
R  backend/tests/manual_test_flights_e2e.py -> backend/manual/manual_flights_e2e.py
R  backend/tests/manual_test_hn.py -> backend/manual/manual_hn.py
R  backend/tests/manual_test_insight.py -> backend/manual/manual_insight.py
R  backend/tests/manual_test_modes.py -> backend/manual/manual_modes.py
R  backend/tests/manual_test_pollinations.py -> backend/manual/manual_pollinations.py
R  backend/tests/manual_test_providers.py -> backend/manual/manual_providers.py
R  backend/tests/manual_test_real_scrape.py -> backend/manual/manual_real_scrape.py
R  backend/tests/manual_test_threebestrated.py -> backend/manual/manual_threebestrated.py
R  backend/tests/manual_test_workflow.py -> backend/manual/manual_workflow.py
 M backend/tests/conftest.py
 M backend/tests/test_auth_profiles.py
 M backend/tests/test_extraction_depth.py
 M backend/tests/test_extraction_orchestrator.py
 M backend/tests/test_extraction_precision.py
 M backend/tests/test_governance_visualization.py
 M backend/tests/test_manual_tests.py
 M backend/tests/test_playwright_browser_e2e.py
 M backend/tests/test_postgres_integration.py
 M backend/tests/test_route_auth_matrix_generator.py
 M backend/tests/test_session_auth.py
 M backend/tests/test_storage_migrations.py
 M backend/tests/test_strategy_evolution.py
 M backend/tests/test_url_safety.py
 M backend/tests/test_zero_result_classifier.py
 M docs/AGENT_TRUTH.md
 M docs/API.md
 M docs/API_EXPERIMENTAL.md
 M docs/API_EXPERIMENTAL_DIFF.md
 M docs/API_STABLE.md
 M docs/ENV_VARIABLES.md
 M docs/ROUTE_AUTH_MATRIX.md
 M docs/ROUTE_INVENTORY.md
 M docs/SECURITY_MODEL.md
 M frontend/app.js
 M frontend/index.html
 M frontend/js/form.js
 M frontend/js/views.js
 M frontend/playwright.config.mjs
 M frontend/styles.css
 M pyproject.toml
 M scripts/generate_route_inventory.py
 M scripts/validate_local.py
?? CODE_SCAN_RESULTS.md
?? artifacts/audit/PIP_AUDIT_OFFLINE_TRIAGE.md
?? artifacts/validation/runs/20260612T214855Z_quick/
?? artifacts/validation/runs/20260612T215845Z_quick/
?? artifacts/validation/runs/20260612T220020Z_quick/
?? artifacts/validation/runs/20260612T220138Z_quick/
?? artifacts/validation/runs/20260612T220402Z_quick/
?? artifacts/validation/runs/20260612T220502Z_quick/
?? artifacts/validation/runs/20260612T220828Z_quick/
?? artifacts/validation/runs/20260612T221056Z_full/
?? artifacts/validation/runs/20260612T222122Z_quick/
?? artifacts/validation/runs/20260612T222154Z_full/
?? artifacts/validation/runs/20260612T222629Z_full/
?? artifacts/validation/runs/20260612T223727Z_full/
?? artifacts/validation/runs/20260612T224403Z_quick/
?? artifacts/validation/runs/20260612T224509Z_full/
?? artifacts/validation/runs/20260613T013007Z_full/
?? artifacts/validation/runs/20260613T022038Z_full/
?? artifacts/validation/runs/20260613T022952Z_quick/
?? artifacts/validation/runs/20260613T023157Z_quick/
?? artifacts/validation/runs/20260613T023217Z_full/
?? artifacts/validation/runs/20260613T024305Z_quick/
?? artifacts/validation/runs/20260613T024349Z_quick/
?? artifacts/validation/runs/20260613T024517Z_quick/
?? artifacts/validation/runs/20260613T024921Z_quick/
?? artifacts/validation/runs/20260613T025035Z_quick/
?? artifacts/validation/runs/20260613T030243Z_quick/
?? artifacts/validation/runs/20260613T030412Z_quick/
?? artifacts/validation/runs/20260613T030540Z_full/
?? artifacts/validation/runs/20260613T031259Z_quick/
?? artifacts/validation/runs/20260613T031432Z_quick/
?? artifacts/validation/runs/20260613T031529Z_quick/
?? artifacts/validation/runs/20260613T031656Z_quick/
?? artifacts/validation/runs/20260613T031904Z_quick/
?? artifacts/validation/runs/20260613T031954Z_quick/
?? artifacts/validation/runs/20260613T032051Z_quick/
?? artifacts/validation/runs/20260613T032427Z_quick/
?? artifacts/validation/runs/20260613T032554Z_quick/
?? artifacts/validation/runs/20260613T034341Z_quick/
?? artifacts/validation/runs/20260613T034908Z_quick/
?? artifacts/validation/runs/20260613T035422Z_quick/
?? artifacts/validation/runs/20260613T035525Z_quick/
?? artifacts/validation/runs/20260613T035716Z_quick/
?? artifacts/validation/runs/20260613T035838Z_quick/
?? artifacts/validation/runs/20260613T040047Z_quick/
?? artifacts/validation/runs/20260613T040141Z_full/
?? artifacts/validation/runs/20260613T040742Z_quick/
?? artifacts/validation/runs/20260613T041017Z_quick/
?? artifacts/validation/runs/20260613T181253Z_quick/
?? artifacts/validation/runs/20260613T181348Z_quick/
?? artifacts/validation/runs/20260613T181420Z_full/
?? artifacts/validation/runs/20260613T182420Z_full/
?? artifacts/validation/runs/20260613T183052Z_full/
?? artifacts/validation/runs/20260613T183745Z_full/
?? artifacts/validation/runs/20260613T185128Z_quick/
?? artifacts/validation/runs/20260613T185157Z_full/
?? artifacts/validation/runs/20260613T190810Z_full/
?? artifacts/validation/runs/20260613T191901Z_quick/
?? artifacts/validation/runs/20260614T054907Z_full/
?? artifacts/validation/runs/20260614T070537Z_quick/
?? artifacts/validation/runs/20260615T230157Z_full/
?? artifacts/validation/runs/20260615T232504Z_full/
?? artifacts/validation/runs/20260615T233015Z_quick/
?? artifacts/validation/runs/20260615T233602Z_full/
?? artifacts/validation/runs/20260615T234205Z_quick/
?? backend/app/billing/
?? backend/app/plan_enforcer.py
?? backend/app/routers/user_data.py
?? backend/manual/README.md
?? backend/manual/__init__.py
?? backend/tests/fixtures/pages/8eac6ed02543.html
?? backend/tests/fixtures/pages/d25db134477a.html
?? backend/tests/test_encryption_rotation.py
?? backend/tests/test_pagination_async.py
?? backend/tests/test_user_data.py
?? docs/INDEX.md
?? frontend/e2e/global-setup.mjs
?? frontend/js/auth-profiles.js

```

## stderr

```text

```
