# DataForge Scraper - File Inventory

_Generated: 2026-06-23T22:17:50+00:00 from `24353` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 24353 |
| Project-owned files | 938 |
| Project-owned files deeply inspected | 934 |
| Skipped generated/vendor/binary/cache/log/archive files | 23419 |
| Files needing follow-up | 0 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 252 | 252 | 252 | 0 |
| frontend_source | 97 | 97 | 97 | 0 |
| test | 378 | 378 | 377 | 1 |
| script | 44 | 44 | 44 | 0 |
| config | 52 | 52 | 49 | 3 |
| documentation | 100 | 100 | 100 | 0 |
| docker_deployment | 13 | 13 | 13 | 0 |
| database_migration | 2 | 2 | 2 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 101 | 0 | 0 | 101 |
| vendor | 15988 | 0 | 0 | 15988 |
| cache | 4380 | 0 | 0 | 4380 |
| binary | 38 | 0 | 0 | 38 |
| archive | 1 | 0 | 0 | 1 |
| log | 2907 | 0 | 0 | 2907 |
| unknown | 0 | 0 | 0 | 0 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `.venv/` | 9847 |
| `node_modules/` | 6140 |
| `artifacts/` | 2965 |
| `backend/` | 1551 |
| `.mypy_cache/` | 1455 |
| `.ruff_cache/` | 1437 |
| `.git/` | 594 |
| `frontend/` | 116 |
| `docs/` | 90 |
| `scripts/` | 76 |
| `playwright-report/` | 18 |
| `.github/` | 11 |
| `.pytest_cache/` | 5 |
| `grafana/` | 3 |
| `.claude/` | 2 |
| `data/` | 2 |
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
| `uv.lock/` | 1 |
| `.vscode/` | 1 |
| `__pycache__/` | 1 |
| `logs/` | 1 |
| `test-results/` | 1 |

## Extension Counts (top 30)

| Extension | Files |
| --- | ---: |
| `.py` | 6827 |
| `.md` | 3191 |
| `(none)` | 3134 |
| `.js` | 2744 |
| `.json` | 2047 |
| `.pyi` | 1217 |
| `.ts` | 888 |
| `.pyc` | 872 |
| `.cjs` | 534 |
| `.mjs` | 454 |
| `.so` | 385 |
| `.map` | 333 |
| `.txt` | 187 |
| `.h` | 169 |
| `.log` | 126 |
| `.typed` | 111 |
| `.c` | 99 |
| `.html` | 88 |
| `.f90` | 61 |
| `.yml` | 57 |
| `.pxd` | 54 |
| `.jsonl` | 52 |
| `.jst` | 50 |
| `.png` | 42 |
| `.cts` | 41 |
| `.pyx` | 37 |
| `.mts` | 37 |
| `.db` | 35 |
| `.csv` | 33 |
| `.css` | 31 |

## Skip Policy

Deep inspection was skipped for vendor dependencies, virtualenv files, Git metadata, cache directories, generated reports, build outputs, runtime data, logs, archives, and binary files. Each skipped file still has a CSV/Markdown row with `skip_reason_if_any`.

## See Also

- `FILE_AUDIT_LEDGER.csv` - complete machine-readable per-file ledger.
- `FILE_AUDIT_LEDGER.md` - complete human-readable per-file ledger.
- `PROJECT_STRUCTURE_SUMMARY.md` - high-level repository map.
- `PROJECT_UNDERSTANDING.md` - product and codebase understanding.
- `VALIDATION_REPORT.md` - command evidence.
- `DOCS_TRUTH_CHECK.md` - docs-vs-code audit.
