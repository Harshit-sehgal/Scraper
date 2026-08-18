# DataForge Scraper - File Inventory

_Generated: 2026-08-18T15:38:21+00:00 from `41037` files in the current checkout._

This inventory accounts for every file found by `os.walk()` from the repository root. Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.

## Required Field Coverage

The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. The Markdown ledger mirrors those rows for human review.

## Summary

| Metric | Count |
| --- | ---: |
| Total files inventoried | 41037 |
| Project-owned files | 1359 |
| Project-owned files deeply inspected | 1352 |
| Skipped generated/vendor/binary/cache/log/archive files | 39685 |
| Files needing follow-up | 3 |

## By Classification

| Classification | Total | Project-owned | Deep-inspected | Skipped |
| --- | ---: | ---: | ---: | ---: |
| backend_source | 299 | 299 | 299 | 0 |
| frontend_source | 99 | 99 | 99 | 0 |
| test | 712 | 712 | 711 | 1 |
| script | 52 | 52 | 52 | 0 |
| config | 57 | 57 | 54 | 3 |
| documentation | 121 | 121 | 121 | 0 |
| docker_deployment | 14 | 14 | 14 | 0 |
| database_migration | 2 | 2 | 2 | 0 |
| asset | 0 | 0 | 0 | 0 |
| generated | 925 | 0 | 0 | 925 |
| vendor | 17221 | 0 | 0 | 17221 |
| cache | 8226 | 0 | 0 | 8226 |
| binary | 642 | 0 | 0 | 642 |
| archive | 1 | 0 | 0 | 1 |
| log | 12663 | 0 | 0 | 12663 |
| unknown | 3 | 3 | 0 | 3 |

## Top-Level Counts

| Top-level path | Files |
| --- | ---: |
| `artifacts/` | 12677 |
| `.venv/` | 11069 |
| `node_modules/` | 6151 |
| `.git/` | 4923 |
| `backend/` | 3241 |
| `.mypy_cache/` | 1571 |
| `frontend/` | 913 |
| `docs/` | 109 |
| `scripts/` | 82 |
| `.agents/` | 81 |
| `MagicMock/` | 71 |
| `.ruff_cache/` | 70 |
| `.github/` | 11 |
| `data/` | 10 |
| `.pytest_cache/` | 5 |
| `.claude/` | 3 |
| `grafana/` | 3 |
| `logs/` | 2 |
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
| `.md` | 12544 |
| `.py` | 7194 |
| `(none)` | 6090 |
| `.js` | 3143 |
| `.pyc` | 2779 |
| `.json` | 2722 |
| `.pyi` | 1217 |
| `.ts` | 889 |
| `.map` | 729 |
| `.db` | 659 |
| `.cjs` | 534 |
| `.mjs` | 457 |
| `.so` | 385 |
| `.txt` | 189 |
| `.h` | 169 |
| `.typed` | 111 |
| `.html` | 99 |
| `.c` | 99 |
| `.log` | 82 |
| `.f90` | 61 |
| `.yml` | 59 |
| `.pxd` | 54 |
| `.jsonl` | 53 |
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
