# DataForge Scraper - File Inventory

_Generated: 2026-07-01T20:50:25+00:00 from `45907` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 45907 |
| Project-owned files | 7784 |
| Project-owned files deeply inspected | 2315 |
| Skipped generated/vendor/binary/cache/log/archive files | 43592 |
| Files needing follow-up | 5455 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 301 | 301 | 301 | 0 |
| frontend_source | 98 | 98 | 98 | 0 |
| test | 700 | 700 | 699 | 1 |
| script | 56 | 56 | 56 | 0 |
| config | 388 | 388 | 380 | 8 |
| documentation | 694 | 694 | 694 | 0 |
| docker_deployment | 69 | 69 | 69 | 0 |
| database_migration | 18 | 18 | 18 | 0 |
| asset | 5 | 5 | 0 | 5 |
| generated | 624 | 0 | 0 | 624 |
| vendor | 16000 | 0 | 0 | 16000 |
| cache | 8596 | 0 | 0 | 8596 |
| binary | 1857 | 0 | 0 | 1857 |
| archive | 6 | 0 | 0 | 6 |
| log | 11040 | 0 | 0 | 11040 |
| unknown | 5455 | 5455 | 0 | 5455 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `artifacts/` | 10983 |
| `.venv/` | 9848 |
| `.claude/` | 8089 |
| `node_modules/` | 6151 |
| `.git/` | 3910 |
| `backend/` | 2988 |
| `.mypy_cache/` | 1561 |
| `MagicMock/` | 1345 |
| `frontend/` | 608 |
| `docs/` | 101 |
| `.agents/` | 81 |
| `scripts/` | 79 |
| `.ruff_cache/` | 67 |
| `playwright-report/` | 18 |
| `.github/` | 11 |
| `data/` | 9 |
| `logs/` | 6 |
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
| `Dockerfile/` | 1 |
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
| `.py` | 11626 |
| `.md` | 11522 |
| `(none)` | 5185 |
| `.json` | 4191 |
| `.js` | 3440 |
| `.db` | 1677 |
| `.pyc` | 1513 |
| `.pyi` | 1217 |
| `.ts` | 889 |
| `.map` | 577 |
| `.cjs` | 534 |
| `.html` | 509 |
| `.mjs` | 482 |
| `.so` | 385 |
| `.png` | 217 |
| `.txt` | 200 |
| `.yml` | 174 |
| `.h` | 169 |
| `.log` | 147 |
| `.typed` | 111 |
| `.c` | 99 |
| `.sh` | 98 |
| `.css` | 77 |
| `.f90` | 61 |
| `.pxd` | 54 |
| `.jsonl` | 52 |
| `.jst` | 50 |
| `.cts` | 41 |
| `.csv` | 38 |
| `.pyx` | 37 |

## Skip Policy

Deep inspection was skipped for vendor dependencies, virtualenv files, Git metadata, cache directories, generated reports, build outputs, runtime data, logs, archives, and binary files. Each skipped file still has a CSV/Markdown row with `skip_reason_if_any`.

## See Also

- `FILE_AUDIT_LEDGER.csv` - complete machine-readable per-file ledger.
- `FILE_AUDIT_LEDGER.md` - complete human-readable per-file ledger.
- `PROJECT_STRUCTURE_SUMMARY.md` - high-level repository map.
- `PROJECT_UNDERSTANDING.md` - product and codebase understanding.
- `VALIDATION_REPORT.md` - command evidence.
- `DOCS_TRUTH_CHECK.md` - docs-vs-code audit.
