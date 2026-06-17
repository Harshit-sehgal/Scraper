# Latest Validation Summary

- generated_at: 2026-06-17T14:43:51.886360+00:00
- mode: full
- run_id: 20260617T143836Z_full
- archive_dir: `artifacts/validation/runs/20260617T143836Z_full`
- overall_status: failed
- passed: 19
- failed: 5
- skipped: 0
- timed_out: 0
- not_installed: 0
- next_recommended_action: Inspect failed command logs under artifacts/validation/commands/ and fix or document the failures.

## Commands

| Status | Required | Name | Exit | Log |
| --- | --- | --- | --- | --- |
| passed | true | required_paths | 0 | `artifacts/validation/commands/00_required_paths.md` |
| passed | true | python_version | 0 | `artifacts/validation/commands/01_python_version.md` |
| passed | false | git_commit | 0 | `artifacts/validation/commands/02_git_commit.md` |
| passed | false | git_status_short | 0 | `artifacts/validation/commands/03_git_status_short.md` |
| passed | false | node_version | 0 | `artifacts/validation/commands/04_node_version.md` |
| passed | false | npm_version | 0 | `artifacts/validation/commands/05_npm_version.md` |
| passed | true | compileall | 0 | `artifacts/validation/commands/06_compileall.md` |
| passed | true | architecture_validator | 0 | `artifacts/validation/commands/07_architecture_validator.md` |
| passed | true | research_boundary | 0 | `artifacts/validation/commands/08_research_boundary.md` |
| passed | true | dependency_bounds | 0 | `artifacts/validation/commands/09_dependency_bounds.md` |
| passed | true | url_and_research_smoke_tests | 0 | `artifacts/validation/commands/10_url_and_research_smoke_tests.md` |
| passed | true | p0_regression_tests | 0 | `artifacts/validation/commands/11_p0_regression_tests.md` |
| passed | true | openapi_spec | 0 | `artifacts/validation/commands/12_openapi_spec.md` |
| failed | true | backend_full_tests | 1 | `artifacts/validation/commands/13_backend_full_tests.md` |
| failed | true | ruff_check | 1 | `artifacts/validation/commands/14_ruff_check.md` |
| failed | true | pyflakes | 1 | `artifacts/validation/commands/15_pyflakes.md` |
| failed | true | mypy | 1 | `artifacts/validation/commands/16_mypy.md` |
| passed | true | bandit_backend | 0 | `artifacts/validation/commands/17_bandit_backend.md` |
| passed | true | pip_audit | 0 | `artifacts/validation/commands/18_pip_audit.md` |
| passed | true | prod_env_example_placeholder_check | 1 | `artifacts/validation/commands/19_prod_env_example_placeholder_check.md` |
| passed | true | npm_ci | 0 | `artifacts/validation/commands/20_npm_ci.md` |
| failed | true | frontend_tests | 1 | `artifacts/validation/commands/21_frontend_tests.md` |
| passed | true | frontend_lint_js | 0 | `artifacts/validation/commands/22_frontend_lint_js.md` |
| passed | true | frontend_lint_css | 0 | `artifacts/validation/commands/23_frontend_lint_css.md` |
