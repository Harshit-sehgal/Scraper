# DataForge Scraper - File Inventory

_Generated: 2026-06-27T13:41:56+00:00 from `32408` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 32408 |
| Project-owned files | 1064 |
| Project-owned files deeply inspected | 1054 |
| Skipped generated/vendor/binary/cache/log/archive files | 31354 |
| Files needing follow-up | 7 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 264 | 264 | 264 | 0 |
| frontend_source | 96 | 96 | 96 | 0 |
| test | 472 | 472 | 472 | 0 |
| script | 49 | 49 | 49 | 0 |
| config | 57 | 57 | 54 | 3 |
| documentation | 103 | 103 | 103 | 0 |
| docker_deployment | 13 | 13 | 13 | 0 |
| database_migration | 3 | 3 | 3 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 232 | 0 | 0 | 232 |
| vendor | 17477 | 0 | 0 | 17477 |
| cache | 5941 | 0 | 0 | 5941 |
| binary | 1170 | 0 | 0 | 1170 |
| archive | 1 | 0 | 0 | 1 |
| log | 6523 | 0 | 0 | 6523 |
| unknown | 7 | 7 | 0 | 7 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `.venv/` | 11325 |
| `artifacts/` | 6584 |
| `node_modules/` | 6151 |
| `.git/` | 3333 |
| `backend/` | 2019 |
| `.mypy_cache/` | 1479 |
| `MagicMock/` | 967 |
| `frontend/` | 244 |
| `docs/` | 91 |
| `scripts/` | 75 |
| `.agents/` | 27 |
| `.ruff_cache/` | 21 |
| `playwright-report/` | 18 |
| `.github/` | 11 |
| `.aider.tags.cache.v4/` | 5 |
| `.pytest_cache/` | 5 |
| `grafana/` | 3 |
| `.claude/` | 2 |
| `data/` | 2 |
| `.aider.chat.history.md/` | 1 |
| `.aider.input.history/` | 1 |
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
| `.py` | 6937 |
| `.md` | 6752 |
| `(none)` | 4454 |
| `.js` | 2807 |
| `.pyc` | 2537 |
| `.json` | 2255 |
| `.pyi` | 1217 |
| `.db` | 1170 |
| `.ts` | 889 |
| `.cjs` | 534 |
| `.mjs` | 455 |
| `.map` | 397 |
| `.so` | 385 |
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
