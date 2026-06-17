# Latest Validation Summary

- generated_at: 2026-06-16T20:02:54.883229+00:00
- mode: full
- run_id: 20260616T195747Z_full
- archive_dir: `artifacts/validation/runs/20260616T195747Z_full`
- overall_status: failed
- passed: 21
- failed: 1
- skipped: 0
- timed_out: 0
- not_installed: 0
- next_recommended_action: Inspect failed command logs under artifacts/validation/commands/ and fix or document the failures.

## Commands

| Status | Required | Name | Exit | Log |
| --- | --- | --- | --- | --- |
| passed | true | required_paths | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/00_required_paths.md` |
| passed | true | python_version | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/01_python_version.md` |
| passed | false | git_commit | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/02_git_commit.md` |
| passed | false | git_status_short | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/03_git_status_short.md` |
| passed | false | node_version | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/04_node_version.md` |
| passed | false | npm_version | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/05_npm_version.md` |
| passed | true | compileall | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/06_compileall.md` |
| passed | true | architecture_validator | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/07_architecture_validator.md` |
| passed | true | research_boundary | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/08_research_boundary.md` |
| passed | true | dependency_bounds | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/09_dependency_bounds.md` |
| passed | true | url_and_research_smoke_tests | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/10_url_and_research_smoke_tests.md` |
| passed | true | p0_regression_tests | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/11_p0_regression_tests.md` |
| passed | true | backend_full_tests | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/12_backend_full_tests.md` |
| failed | true | ruff_check | 1 | `artifacts/validation/runs/20260616T195747Z_full/commands/13_ruff_check.md` |
| passed | true | pyflakes | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/14_pyflakes.md` |
| passed | true | mypy | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/15_mypy.md` |
| passed | true | bandit_backend | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/16_bandit_backend.md` |
| passed | true | pip_audit | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/17_pip_audit.md` |
| passed | true | prod_env_example_placeholder_check | 1 | `artifacts/validation/runs/20260616T195747Z_full/commands/18_prod_env_example_placeholder_check.md` |
| passed | true | npm_ci | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/19_npm_ci.md` |
| passed | true | frontend_tests | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/20_frontend_tests.md` |
| passed | true | frontend_lint_js | 0 | `artifacts/validation/runs/20260616T195747Z_full/commands/21_frontend_lint_js.md` |
