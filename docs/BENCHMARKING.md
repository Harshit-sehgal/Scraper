# Benchmarking

Benchmark results must be labeled by methodology. Do not present simulated or fixture-only results as live website reliability.

## Current Benchmark Types

| Type | Files | Status |
| --- | --- | --- |
| Metric simulation | `backend/tests/test_accuracy.py`, part of `test_benchmark_suite.py` | Collected by pytest |
| Fixture benchmark | `backend/tests/test_benchmark_suite.py`, `test_benchmark_fixtures.py` | Collected by pytest |
| Manual hostile benchmark | `backend/tests/hostile_benchmarks.py` | Not collected |
| Manual live benchmark | `backend/tests/benchmark_smoke_test.py`, `scripts/live_benchmark.py` | Not collected; network-dependent |
| Replay/longevity benchmark | `backend/tests/replay_benchmark.py`, `longevity_run.py` | Not collected; synthetic |

## Accuracy Metric

The accuracy metric now penalizes:

- wrong field values
- missing expected fields
- extra extracted fields
- extra extracted records
- duplicate records
- schema mismatch
- placeholder/hallucination strings

This is a metric improvement, not proof that every extraction output is correct.

## Real Benchmark Requirements

A defensible scraper benchmark should include:

- deterministic HTML fixtures
- golden record-level expected outputs
- schema validation
- false-positive penalties
- false-negative penalties
- duplicate penalties
- malformed output penalties
- replayed network payloads when relevant
- separate live runs with date, target list, network conditions, and command

Live benchmarks should never be used as the only release gate.
