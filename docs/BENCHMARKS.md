# Benchmarks

**Date:** 2026-05-31  
**Status:** Benchmark tooling exists, but real-world accuracy is not proven

## Current Verified Benchmark Command

```bash
PYTHONPATH=backend \
DATAFORGE_DOTENV_PATH=/dev/null \
DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m pytest -q backend/benchmarks -o addopts=
```

Latest verified result:

```text
1 passed in 1.20s
```

This is an offline smoke/config test. It does not run live extraction and does not prove real-world accuracy.

## Benchmark Categories

| Category | Status | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| Fixture extraction tests | Implemented | Regression behavior on controlled HTML fixtures | Live website accuracy |
| Hostile/recovery simulations | Simulated | Code behavior under generated conditions | Real anti-bot resilience |
| Replay/longevity modules | Simulated/manual | Internal state and workload behavior under controlled inputs | Production reliability |
| Golden dataset tests | Optional | Can support real-world validation once reviewed and populated | Accuracy by default |
| Live/manual scripts | Manual | Useful exploratory checks | Default test-suite health |

## Accuracy Rules

Do not claim:

- 100% accurate.
- Proven real-world accuracy.
- Anti-bot tested.
- Works on every website.
- Production benchmark complete.

Acceptable language:

> The project includes fixture-based and simulated benchmark tooling. These checks are useful for regression detection, but they do not prove real-world scraping accuracy. A reviewed golden dataset with expected outputs is required before making accuracy claims.

## Required Real Benchmark Report

A credible benchmark report must include:

- Dataset source and permission/legal notes.
- Number of sites and pages.
- Static versus JavaScript-rendered pages.
- Schemas used.
- Expected outputs.
- Extracted outputs.
- Precision, recall, and F1.
- Extra/missing records penalties.
- Extra/missing field penalties.
- Failure cases.
- Exact reproduction commands.
