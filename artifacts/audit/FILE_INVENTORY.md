# DataForge Scraper - File Inventory

_Generated: 2026-06-26T05:55:33+00:00 from `27354` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 27354 |
| Project-owned files | 1002 |
| Project-owned files deeply inspected | 998 |
| Skipped generated/vendor/binary/cache/log/archive files | 26356 |
| Files needing follow-up | 0 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 254 | 254 | 254 | 0 |
| frontend_source | 97 | 97 | 97 | 0 |
| test | 429 | 429 | 428 | 1 |
| script | 49 | 49 | 49 | 0 |
| config | 55 | 55 | 52 | 3 |
| documentation | 102 | 102 | 102 | 0 |
| docker_deployment | 13 | 13 | 13 | 0 |
| database_migration | 3 | 3 | 3 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 92 | 0 | 0 | 92 |
| vendor | 15988 | 0 | 0 | 15988 |
| cache | 6058 | 0 | 0 | 6058 |
| binary | 38 | 0 | 0 | 38 |
| archive | 1 | 0 | 0 | 1 |
| log | 4175 | 0 | 0 | 4175 |
| unknown | 0 | 0 | 0 | 0 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `.venv/` | 9847 |
| `node_modules/` | 6140 |
| `artifacts/` | 4236 |
| `.git/` | 2156 |
| `backend/` | 1705 |
| `.mypy_cache/` | 1461 |
| `.ruff_cache/` | 1438 |
| `frontend/` | 115 |
| `docs/` | 91 |
| `scripts/` | 84 |
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
| `uv.lock/` | 1 |
| `.vscode/` | 1 |
| `__pycache__/` | 1 |
| `nginx/` | 1 |
| `test-results/` | 1 |

## Extension Counts (top 30)

| Extension | Files |
| --- | ---: |
| `.py` | 6884 |
| `(none)` | 4692 |
| `.md` | 4471 |
| `.js` | 2744 |
| `.json` | 2135 |
| `.pyi` | 1217 |
| `.pyc` | 981 |
| `.ts` | 888 |
| `.cjs` | 534 |
| `.mjs` | 454 |
| `.so` | 385 |
| `.map` | 333 |
| `.txt` | 187 |
| `.h` | 169 |
| `.typed` | 111 |
| `.c` | 99 |
| `.html` | 88 |
| `.f90` | 61 |
| `.yml` | 58 |
| `.pxd` | 54 |
| `.jsonl` | 52 |
| `.jst` | 50 |
| `.png` | 42 |
| `.cts` | 41 |
| `.pyx` | 37 |
| `.mts` | 37 |
| `.log` | 34 |
| `.csv` | 33 |
| `.db` | 32 |
| `.sh` | 32 |

## Skip Policy

Deep inspection was skipped for vendor dependencies, virtualenv files, Git metadata, cache directories, generated reports, build outputs, runtime data, logs, archives, and binary files. Each skipped file still has a CSV/Markdown row with `skip_reason_if_any`.

## See Also

- `FILE_AUDIT_LEDGER.csv` - complete machine-readable per-file ledger.
- `FILE_AUDIT_LEDGER.md` - complete human-readable per-file ledger.
- `PROJECT_STRUCTURE_SUMMARY.md` - high-level repository map.
- `PROJECT_UNDERSTANDING.md` - product and codebase understanding.
- `VALIDATION_REPORT.md` - command evidence.
- `DOCS_TRUTH_CHECK.md` - docs-vs-code audit.
