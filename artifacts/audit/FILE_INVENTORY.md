# DataForge Scraper - File Inventory

_Generated: 2026-06-28T21:45:46+00:00 from `34648` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 34648 |
| Project-owned files | 1085 |
| Project-owned files deeply inspected | 1079 |
| Skipped generated/vendor/binary/cache/log/archive files | 33569 |
| Files needing follow-up | 2 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 269 | 269 | 269 | 0 |
| frontend_source | 96 | 96 | 96 | 0 |
| test | 491 | 491 | 490 | 1 |
| script | 51 | 51 | 51 | 0 |
| config | 57 | 57 | 54 | 3 |
| documentation | 103 | 103 | 103 | 0 |
| docker_deployment | 13 | 13 | 13 | 0 |
| database_migration | 3 | 3 | 3 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 255 | 0 | 0 | 255 |
| vendor | 17512 | 0 | 0 | 17512 |
| cache | 7262 | 0 | 0 | 7262 |
| binary | 158 | 0 | 0 | 158 |
| archive | 1 | 0 | 0 | 1 |
| log | 8375 | 0 | 0 | 8375 |
| unknown | 2 | 2 | 0 | 2 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `.venv/` | 11360 |
| `artifacts/` | 8434 |
| `node_modules/` | 6151 |
| `.git/` | 4583 |
| `backend/` | 1925 |
| `.mypy_cache/` | 1483 |
| `frontend/` | 244 |
| `MagicMock/` | 121 |
| `docs/` | 92 |
| `scripts/` | 79 |
| `.ruff_cache/` | 54 |
| `.agents/` | 39 |
| `playwright-report/` | 18 |
| `.github/` | 11 |
| `.pytest_cache/` | 5 |
| `grafana/` | 3 |
| `.claude/` | 2 |
| `.dockerignore/` | 1 |
| `.env/` | 1 |
| `.env.example/` | 1 |
| `.env.production/` | 1 |
| `.env.production.example/` | 1 |
| `.env.production.local/` | 1 |
| `.env.test/` | 1 |
| `.gitignore/` | 1 |
| `.pre-commit-config.yaml/` | 1 |
| `.prettierignore/` | 1 |
| `.prettierrc/` | 1 |
| `.stylelintrc.json/` | 1 |
| `AGENTS.md/` | 1 |
| `CHANGELOG.md/` | 1 |
| `Dockerfile/` | 1 |
| `LICENSE/` | 1 |
| `Makefile/` | 1 |
| `README.md/` | 1 |
| `THIRD_PARTY_NOTICES.md/` | 1 |
| `alertmanager.yml/` | 1 |
| `architecture_validator.py/` | 1 |
| `auth/` | 1 |
| `blackbox.yml/` | 1 |
| `dataforge_denylist.sqlite/` | 1 |
| `docker-compose.override.local.yml/` | 1 |
| `docker-compose.override.yml/` | 1 |
| `docker-compose.prod.yml/` | 1 |
| `docker-compose.yml/` | 1 |
| `eslint.config.js/` | 1 |
| `nginx.conf/` | 1 |
| `nginx.local.conf/` | 1 |
| `package-lock.json/` | 1 |
| `package.json/` | 1 |
| `postgres-queries.yaml/` | 1 |
| `prometheus.yml/` | 1 |
| `prometheus_alerts.yml/` | 1 |
| `prometheus_web.yml/` | 1 |
| `pyproject.toml/` | 1 |
| `setup/` | 1 |
| `uv.lock/` | 1 |
| `.vscode/` | 1 |
| `__pycache__/` | 1 |
| `logs/` | 1 |
| `nginx/` | 1 |

## Extension Counts (top 30)

| Extension | Files |
| --- | ---: |
| `.md` | 8506 |
| `.py` | 6956 |
| `(none)` | 5736 |
| `.js` | 2807 |
| `.pyc` | 2610 |
| `.json` | 2379 |
| `.pyi` | 1217 |
| `.ts` | 889 |
| `.cjs` | 534 |
| `.mjs` | 455 |
| `.map` | 397 |
| `.so` | 385 |
| `.txt` | 187 |
| `.h` | 169 |
| `.db` | 145 |
| `.typed` | 111 |
| `.c` | 99 |
| `.html` | 94 |
| `.f90` | 61 |
| `.yml` | 58 |
| `.pxd` | 54 |
| `.jsonl` | 52 |
| `.jst` | 50 |
| `.png` | 42 |
| `.cts` | 41 |
| `.pyx` | 37 |
| `.mts` | 37 |
| `.log` | 35 |
| `.csv` | 33 |
| `.sh` | 33 |

## Skip Policy

Deep inspection was skipped for vendor dependencies, virtualenv files, Git metadata, cache directories, generated reports, build outputs, runtime data, logs, archives, and binary files. Each skipped file still has a CSV/Markdown row with `skip_reason_if_any`.

## See Also

- `FILE_AUDIT_LEDGER.csv` - complete machine-readable per-file ledger.
- `FILE_AUDIT_LEDGER.md` - complete human-readable per-file ledger.
- `PROJECT_STRUCTURE_SUMMARY.md` - high-level repository map.
- `PROJECT_UNDERSTANDING.md` - product and codebase understanding.
- `VALIDATION_REPORT.md` - command evidence.
- `DOCS_TRUTH_CHECK.md` - docs-vs-code audit.
