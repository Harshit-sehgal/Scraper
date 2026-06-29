# DataForge Scraper - File Inventory

_Generated: 2026-06-29T21:34:10+00:00 from `35237` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 35237 |
| Project-owned files | 1291 |
| Project-owned files deeply inspected | 1283 |
| Skipped generated/vendor/binary/cache/log/archive files | 33954 |
| Files needing follow-up | 4 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 275 | 275 | 275 | 0 |
| frontend_source | 96 | 96 | 96 | 0 |
| test | 678 | 678 | 677 | 1 |
| script | 51 | 51 | 51 | 0 |
| config | 57 | 57 | 54 | 3 |
| documentation | 113 | 113 | 113 | 0 |
| docker_deployment | 14 | 14 | 14 | 0 |
| database_migration | 3 | 3 | 3 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 383 | 0 | 0 | 383 |
| vendor | 17225 | 0 | 0 | 17225 |
| cache | 5668 | 0 | 0 | 5668 |
| binary | 653 | 0 | 0 | 653 |
| archive | 1 | 0 | 0 | 1 |
| log | 10016 | 0 | 0 | 10016 |
| unknown | 4 | 4 | 0 | 4 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `.venv/` | 11073 |
| `artifacts/` | 10048 |
| `node_modules/` | 6151 |
| `.git/` | 2637 |
| `backend/` | 2559 |
| `.mypy_cache/` | 1415 |
| `MagicMock/` | 572 |
| `frontend/` | 366 |
| `docs/` | 101 |
| `.agents/` | 81 |
| `scripts/` | 79 |
| `.ruff_cache/` | 59 |
| `playwright-report/` | 18 |
| `.github/` | 11 |
| `data/` | 8 |
| `.pytest_cache/` | 5 |
| `logs/` | 4 |
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
| `setup/` | 1 |
| `test_js_sdk.mjs/` | 1 |
| `uv.lock/` | 1 |
| `.vscode/` | 1 |
| `__pycache__/` | 1 |
| `nginx/` | 1 |

## Extension Counts (top 30)

| Extension | Files |
| --- | ---: |
| `.md` | 10071 |
| `.py` | 7140 |
| `(none)` | 3797 |
| `.js` | 2868 |
| `.pyc` | 2678 |
| `.json` | 2417 |
| `.pyi` | 1217 |
| `.ts` | 889 |
| `.db` | 656 |
| `.cjs` | 534 |
| `.mjs` | 457 |
| `.map` | 457 |
| `.so` | 385 |
| `.txt` | 187 |
| `.h` | 169 |
| `.typed` | 111 |
| `.html` | 99 |
| `.c` | 99 |
| `.f90` | 61 |
| `.log` | 60 |
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
