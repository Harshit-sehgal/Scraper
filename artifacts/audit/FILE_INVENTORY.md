# DataForge Scraper - File Inventory

_Generated: 2026-07-02T15:18:46+00:00 from `40868` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 40868 |
| Project-owned files | 1338 |
| Project-owned files deeply inspected | 1332 |
| Skipped generated/vendor/binary/cache/log/archive files | 39536 |
| Files needing follow-up | 3 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 300 | 300 | 300 | 0 |
| frontend_source | 98 | 98 | 98 | 0 |
| test | 702 | 702 | 701 | 1 |
| script | 50 | 50 | 50 | 0 |
| config | 56 | 56 | 54 | 2 |
| documentation | 113 | 113 | 113 | 0 |
| docker_deployment | 14 | 14 | 14 | 0 |
| database_migration | 2 | 2 | 2 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 696 | 0 | 0 | 696 |
| vendor | 17221 | 0 | 0 | 17221 |
| cache | 7407 | 0 | 0 | 7407 |
| binary | 2004 | 0 | 0 | 2004 |
| archive | 1 | 0 | 0 | 1 |
| log | 12201 | 0 | 0 | 12201 |
| unknown | 3 | 3 | 0 | 3 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `artifacts/` | 12117 |
| `.venv/` | 11069 |
| `node_modules/` | 6151 |
| `.git/` | 4146 |
| `backend/` | 3110 |
| `MagicMock/` | 1620 |
| `.mypy_cache/` | 1561 |
| `frontend/` | 668 |
| `docs/` | 101 |
| `.agents/` | 81 |
| `scripts/` | 78 |
| `.ruff_cache/` | 67 |
| `playwright-report/` | 18 |
| `.github/` | 11 |
| `data/` | 9 |
| `logs/` | 6 |
| `.pytest_cache/` | 5 |
| `grafana/` | 3 |
| `.claude/` | 2 |
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
| `Dockerfile/` | 1 |
| `Dockerfile.smoke/` | 1 |
| `LICENSE/` | 1 |
| `Makefile/` | 1 |
| `README.md/` | 1 |
| `THIRD_PARTY_NOTICES.md/` | 1 |
| `alertmanager.yml/` | 1 |
| `architecture_validator.py/` | 1 |
| `blackbox.yml/` | 1 |
| `dataforge_denylist.sqlite/` | 1 |
| `docker-compose.dev.yml/` | 1 |
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
| `test_js_sdk.mjs/` | 1 |
| `uv.lock/` | 1 |
| `.vscode/` | 1 |
| `__pycache__/` | 1 |
| `nginx/` | 1 |

## Extension Counts (top 30)

| Extension | Files |
| --- | ---: |
| `.md` | 12029 |
| `.py` | 7189 |
| `(none)` | 5313 |
| `.js` | 3020 |
| `.pyc` | 2750 |
| `.json` | 2671 |
| `.db` | 2021 |
| `.pyi` | 1217 |
| `.ts` | 889 |
| `.map` | 607 |
| `.cjs` | 534 |
| `.mjs` | 457 |
| `.so` | 385 |
| `.txt` | 189 |
| `.log` | 176 |
| `.h` | 169 |
| `.typed` | 111 |
| `.html` | 99 |
| `.c` | 99 |
| `.f90` | 61 |
| `.yml` | 59 |
| `.pxd` | 54 |
| `.jsonl` | 52 |
| `.jst` | 50 |
| `.png` | 42 |
| `.cts` | 41 |
| `.pyx` | 37 |
| `.mts` | 37 |
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
