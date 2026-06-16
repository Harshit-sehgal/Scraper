# DataForge Scraper - File Inventory

_Generated: 2026-06-16T07:55:39+00:00 from `32788` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 32788 |
| Project-owned files | 878 |
| Project-owned files deeply inspected | 861 |
| Skipped generated/vendor/binary/cache/log/archive files | 31927 |
| Files needing follow-up | 31 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 276 | 276 | 276 | 0 |
| frontend_source | 42 | 42 | 42 | 0 |
| test | 335 | 335 | 334 | 1 |
| script | 49 | 49 | 49 | 0 |
| config | 41 | 41 | 39 | 2 |
| documentation | 108 | 108 | 108 | 0 |
| docker_deployment | 12 | 12 | 12 | 0 |
| database_migration | 1 | 1 | 1 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 143 | 0 | 0 | 143 |
| vendor | 19938 | 0 | 0 | 19938 |
| cache | 10060 | 0 | 0 | 10060 |
| binary | 2 | 0 | 0 | 2 |
| archive | 1 | 0 | 0 | 1 |
| log | 1766 | 0 | 0 | 1766 |
| unknown | 14 | 14 | 0 | 14 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `.venv/` | 11513 |
| `.git/` | 6661 |
| `node_modules/` | 4989 |
| `.kilo/` | 3438 |
| `artifacts/` | 1811 |
| `backend/` | 1533 |
| `.ruff_cache/` | 1313 |
| `.mypy_cache/` | 1205 |
| `docs/` | 90 |
| `scripts/` | 75 |
| `frontend/` | 57 |
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
| `test-results/` | 1 |

## Extension Counts (top 30)

| Extension | Files |
| --- | ---: |
| `(none)` | 8970 |
| `.py` | 6626 |
| `.pyc` | 2850 |
| `.js` | 2847 |
| `.ts` | 2232 |
| `.md` | 2091 |
| `.json` | 1688 |
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
| `.html` | 78 |
| `.f90` | 61 |
| `.pxd` | 54 |
| `.jsonl` | 52 |
| `.yml` | 39 |
| `.pyx` | 37 |
| `.csv` | 36 |
| `.mts` | 35 |
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
