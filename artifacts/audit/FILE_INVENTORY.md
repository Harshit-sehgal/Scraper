# DataForge Scraper - File Inventory

_Generated: 2026-06-12T11:14:02+00:00 from `29148` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 29148 |
| Project-owned files | 821 |
| Project-owned files deeply inspected | 818 |
| Skipped generated/vendor/binary/cache/log/archive files | 28330 |
| Files needing follow-up | 17 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 265 | 265 | 265 | 0 |
| frontend_source | 41 | 41 | 41 | 0 |
| test | 339 | 339 | 338 | 1 |
| script | 44 | 44 | 44 | 0 |
| config | 40 | 40 | 38 | 2 |
| documentation | 79 | 79 | 79 | 0 |
| docker_deployment | 12 | 12 | 12 | 0 |
| database_migration | 1 | 1 | 1 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 117 | 0 | 0 | 117 |
| vendor | 19938 | 0 | 0 | 19938 |
| cache | 8129 | 0 | 0 | 8129 |
| binary | 2 | 0 | 0 | 2 |
| archive | 1 | 0 | 0 | 1 |
| log | 140 | 0 | 0 | 140 |
| unknown | 0 | 0 | 0 | 0 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `.venv/` | 11513 |
| `node_modules/` | 4989 |
| `.git/` | 4808 |
| `.kilo/` | 3438 |
| `backend/` | 1472 |
| `.ruff_cache/` | 1306 |
| `.mypy_cache/` | 1179 |
| `artifacts/` | 157 |
| `scripts/` | 65 |
| `docs/` | 64 |
| `frontend/` | 55 |
| `playwright-report/` | 34 |
| `.github/` | 10 |
| `Instructions_for_ai/` | 7 |
| `.pytest_cache/` | 5 |
| `grafana/` | 3 |
| `.coverage/` | 1 |
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
| `CODE_REVIEW_BUGS.md/` | 1 |
| `Dockerfile/` | 1 |
| `LICENSE/` | 1 |
| `Makefile/` | 1 |
| `PROJECT_STATUS.md/` | 1 |
| `README.md/` | 1 |
| `THIRD_PARTY_NOTICES.md/` | 1 |
| `alertmanager.yml/` | 1 |
| `architecture_validator.py/` | 1 |
| `coverage.json/` | 1 |
| `dataforge_denylist.sqlite/` | 1 |
| `docker-compose.override.yml/` | 1 |
| `docker-compose.prod.yml/` | 1 |
| `docker-compose.yml/` | 1 |
| `nginx.conf/` | 1 |
| `package-lock.json/` | 1 |
| `package.json/` | 1 |
| `postgres-queries.yaml/` | 1 |
| `prometheus.yml/` | 1 |
| `prometheus_alerts.yml/` | 1 |
| `prometheus_web.yml/` | 1 |
| `pyproject.toml/` | 1 |
| `uv.lock/` | 1 |
| `verify_compile.py/` | 1 |
| `.claude/` | 1 |
| `.vscode/` | 1 |
| `__pycache__/` | 1 |
| `test-results/` | 1 |

## Extension Counts (top 30)

| Extension | Files |
| --- | ---: |
| `(none)` | 7110 |
| `.py` | 6603 |
| `.js` | 2846 |
| `.pyc` | 2805 |
| `.ts` | 2232 |
| `.json` | 1559 |
| `.pyi` | 1187 |
| `.map` | 1172 |
| `.cjs` | 620 |
| `.md` | 514 |
| `.mjs` | 451 |
| `.so` | 383 |
| `.txt` | 187 |
| `.h` | 165 |
| `.cts` | 128 |
| `.log` | 126 |
| `.typed` | 106 |
| `.c` | 99 |
| `.html` | 76 |
| `.f90` | 61 |
| `.pxd` | 54 |
| `.jsonl` | 52 |
| `.yml` | 39 |
| `.pyx` | 37 |
| `.mts` | 35 |
| `.csv` | 34 |
| `.db` | 32 |
| `.sh` | 31 |
| `.pxi` | 29 |
| `.css` | 24 |

## Skip Policy

Deep inspection was skipped for vendor dependencies, virtualenv files, Git metadata, cache directories, generated reports, build outputs, runtime data, logs, archives, and binary files. Each skipped file still has a CSV/Markdown row with `skip_reason_if_any`.

## See Also

- `FILE_AUDIT_LEDGER.csv` - complete machine-readable per-file ledger.
- `FILE_AUDIT_LEDGER.md` - complete human-readable per-file ledger.
- `PROJECT_STRUCTURE_SUMMARY.md` - high-level repository map.
- `PROJECT_UNDERSTANDING.md` - product and codebase understanding.
- `VALIDATION_REPORT.md` - command evidence.
- `DOCS_TRUTH_CHECK.md` - docs-vs-code audit.
