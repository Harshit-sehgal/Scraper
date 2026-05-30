# Deliverable 6: Benchmark Truth Report

**Date:** May 30, 2026
**Method:** Code inspection of each benchmark file in `backend/benchmarks/`.

---

## Benchmark Files

### 1. `backend/benchmarks/test_benchmark_smoke.py`
| Aspect | Assessment |
|--------|------------|
| What it claims | Manual live benchmark for extraction pipeline using public websites |
| What it actually measures | Extraction time and success for configured sites |
| Is it collected by pytest? | ❌ No (not named `test_*.py`) |
| Is it run in CI? | ❌ No evidence |
| Is it deterministic? | ⚠️ Partially — depends on network, site structure changes |
| Does it use real scraping? | ✅ Yes — hits live websites |
| Does it use fixture pages? | ❌ No — live only |
| Punishes false positives? | ❓ Unknown — needs code inspection |
| Punishes missing fields? | ❓ Unknown |
| Output quality checked? | ❓ Unknown |
| Reproducible? | ❌ No — depends on live websites |

**Verdict:** Useful but manual. Not automated. Results are environment-dependent.

### 2. `backend/benchmarks/test_benchmark_hostile.py`
| Aspect | Assessment |
|--------|------------|
| What it claims | Stress-testing suite simulating challenging conditions |
| What it actually measures | Response to malformed HTML, dynamic content, anti-bot signals |
| Is it collected by pytest? | ❌ No |
| Is it deterministic? | ✅ Yes — uses hardcoded simulation data |
| Does it use real scraping? | ❌ No — simulated data |
| Uses fixture pages? | ✅ Yes — generates its own test data |
| Punishes false positives? | ❓ Unknown |
| **Key issue** | Uses hardcoded `attempts = [False, True, True, True]` — tests metric calculation, not real recovery |

**Verdict:** Simulated benchmark. Tests metric math, not real extraction quality. Must be labeled "simulated."

### 3. `backend/benchmarks/test_benchmark_replay.py`
| Aspect | Assessment |
|--------|------------|
| What it claims | Measures deterministic state reconstruction performance |
| What it actually measures | Time to replay 10,000 transactions |
| Is it collected by pytest? | ❌ No |
| Is it deterministic? | ✅ Yes — generates its own test data |
| Does it test real scraper behavior? | ❌ No — tests state replay, not extraction |

**Verdict:** Valid performance benchmark for state replay. Not an extraction benchmark.

### 4. `backend/benchmarks/test_benchmark_longevity.py`
| Aspect | Assessment |
|--------|------------|
| What it claims | Long-running stability validation |
| What it actually measures | 100,000 cycles of entropy economics and causal graph growth |
| Is it collected by pytest? | ❌ No |
| Is it deterministic? | ⚠️ Partially, but uses `random` |
| Does it test real scraper behavior? | ❌ No — tests world state internals |

**Verdict:** Stress test for semantic world state internals. Not an extraction benchmark.

---

## Accuracy Metrics Assessment

The project has `benchmark_accuracy.py` which calculates precision, recall, and F1.

**Potential issues:**
- Needs verification that it punishes: extra records, wrong fields, missing fields, duplicates, schema mismatch
- If it can return perfect scores despite extra garbage records, it's weak
- Needs test verification

---

## Honest Summary

**There are no automated, CI-integrated extraction benchmarks.** The 4 benchmark files are manual scripts not collected by pytest. The most interesting one (`hostile.py`) uses simulated data. The only real extraction validation (`smoke.py`) depends on live websites and is not automated.

**What can be honestly claimed:**
- "Benchmark tooling exists for: simulated hostile conditions, state replay performance, long-running stability, and manual live extraction"
- "No benchmark is currently integrated into CI or automated test runs"
- "The simulated benchmark tests metric calculation, not real extraction quality"
- "A real extraction benchmark framework needs: fixture-based replay, CI integration, clear accuracy metrics that punish all error types"

**What must NOT be claimed:**
- "Benchmark-validated extraction accuracy"
- "Proven extraction quality"
- "Real-world benchmark results"
