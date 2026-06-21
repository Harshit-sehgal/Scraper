# DataForge Scraper - File Inventory

_Generated: 2026-06-17T07:27:22+00:00 from `28512` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 28512 |
| Project-owned files | 899 |
| Project-owned files deeply inspected | 896 |
| Skipped generated/vendor/binary/cache/log/archive files | 27616 |
| Files needing follow-up | 17 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 279 | 279 | 279 | 0 |
| frontend_source | 55 | 55 | 55 | 0 |
| test | 350 | 350 | 349 | 1 |
| script | 51 | 51 | 51 | 0 |
| config | 41 | 41 | 39 | 2 |
| documentation | 110 | 110 | 110 | 0 |
| docker_deployment | 12 | 12 | 12 | 0 |
| database_migration | 1 | 1 | 1 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 154 | 0 | 0 | 154 |
| vendor | 19938 | 0 | 0 | 19938 |
| cache | 4550 | 0 | 0 | 4550 |
| binary | 2 | 0 | 0 | 2 |
| archive | 1 | 0 | 0 | 1 |
| log | 2968 | 0 | 0 | 2968 |
| unknown | 0 | 0 | 0 | 0 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `.venv/` | 11513 |
| `node_modules/` | 4989 |
| `.kilo/` | 3438 |
| `artifacts/` | 3015 |
| `backend/` | 1537 |
| `.ruff_cache/` | 1321 |
| `.mypy_cache/` | 1217 |
| `.git/` | 1130 |
| `docs/` | 91 |
| `scripts/` | 79 |
| `frontend/` | 71 |
| `test-results/` | 22 |
| `playwright-report/` | 19 |
| `.github/` | 10 |
| `Instructions_for_ai/` | 7 |
| `.pytest_cache/` | 5 |
| `grafana/` | 3 |
| `.commandcode/` | 2 |
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
| `CODE_SCAN_RESULTS.md/` | 1 |
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

## Extension Counts (top 30)

| Extension | Files |
| --- | ---: |
| `.py` | 6630 |
| `(none)` | 3444 |
| `.md` | 3239 |
| `.js` | 2860 |
| `.pyc` | 2851 |
| `.ts` | 2232 |
| `.json` | 1765 |
| `.pyi` | 1187 |
| `.map` | 1172 |
| `.cjs` | 620 |
| `.mjs` | 452 |
| `.so` | 383 |
| `.txt` | 187 |
| `.h` | 165 |
| `.cts` | 128 |
| `.log` | 126 |
| `.typed` | 106 |
| `.c` | 99 |
| `.html` | 79 |
| `.f90` | 61 |
| `.pxd` | 54 |
| `.jsonl` | 52 |
| `.yml` | 39 |
| `.pyx` | 37 |
| `.csv` | 36 |
| `.mts` | 35 |
| `.db` | 33 |
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
