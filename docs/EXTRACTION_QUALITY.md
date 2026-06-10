# Extraction Quality & Benchmarking Documentation

## Overview

DataForge includes comprehensive benchmarking and quality tracking to monitor extraction performance and accuracy.

## Quality Metrics

### Core Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Success Rate | % of successful extractions | > 95% |
| Data Completeness | % of expected fields extracted | > 80% |
| Confidence Score | AI confidence in extraction | > 0.7 |
| Extraction Time | Time per extraction | < 30s |

### Anti-Bot Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Anti-Bot Score | Detected by anti-bot systems | < 0.3 |
| Stealth Success | Bypassed anti-bot measures | > 90% |
| Retries Needed | Attempts before success | < 3 |

### Data Quality Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Empty Fields | Fields with no data | < 10% |
| Malformed Data | Invalid data formats | < 5% |
| Duplicates | Duplicate records detected | < 2% |

## Benchmarking

### Running Benchmarks

```bash
# Run all benchmarks
pytest backend/benchmarks/ -v

# Run specific benchmark
pytest backend/benchmarks/benchmark_replay.py -v

# Run with live benchmarks (requires network)
DATAFORGE_RUN_LIVE_BENCHMARKS=true pytest backend/benchmarks/ -v

# Generate benchmark report
python3 scripts/generate_benchmark_report.py
```

### Benchmark Categories

| Category | Description | Location |
|----------|-------------|----------|
| Replay | Replays recorded HTTP responses | `benchmark_replay.py` |
| Longevity | Extended stability tests | `benchmark_longevity.py` |
| Hostile | Adversarial input tests | `benchmark_hostile.py` |
| Accuracy | Extraction accuracy validation | `app/benchmark_accuracy.py` |

### Benchmark Results

Results are stored in:
- `backend/data/benchmarks/` - Raw benchmark data
- `docs/BENCHMARK_REPORT.md` - Generated reports

## Quality Tracking

### Usage

```python
from app.utils.extraction_metrics import get_quality_tracker

tracker = get_quality_tracker()

# Start tracking
metrics = tracker.start_extraction(job_id="123", url="https://example.com")

# ... perform extraction ...

# End tracking
metrics.fields_extracted = 5
metrics.fields_expected = 6
metrics.confidence_score = 0.85
metrics.success = True
tracker.end_extraction(metrics)

# Get summary
summary = tracker.get_summary()
print(f"Success rate: {summary['success_rate']:.1%}")

# Get domain-specific metrics
domain_metrics = tracker.get_domain_metrics("example.com")
```

### Metrics Endpoint

```bash
# Get extraction metrics
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/scraper/telemetry

# Get performance report
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/scraper/stats
```

## Performance Monitoring

### Key Performance Indicators (KPIs)

| KPI | Description | Alert Threshold |
|-----|-------------|-----------------|
| Extraction Latency | Time per extraction | > 60s |
| Success Rate | % successful extractions | < 90% |
| Data Completeness | % fields extracted | < 70% |
| Error Rate | % failed extractions | > 10% |

### Monitoring Dashboard

The Grafana dashboard includes:
- Extraction success rate over time
- Average extraction time
- Data completeness trends
- Error rate by domain
- Anti-bot detection rates

### Alerting Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| High Error Rate | `error_rate > 0.1` for 5m | Warning |
| Slow Extraction | `avg_extraction_time > 60s` | Warning |
| Low Completeness | `avg_completeness < 0.7` | Warning |
| High Anti-Bot Detection | `anti_bot_score > 0.5` | Info |

## Accuracy Validation

### Golden Dataset

- Location: `backend/data/golden_dataset/`
- Purpose: Validate extraction accuracy against known-good data
- Run: `pytest -m golden_dataset`

### Accuracy Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Precision | Correct extractions / Total extractions | > 90% |
| Recall | Correct extractions / Expected extractions | > 85% |
| F1 Score | Harmonic mean of precision and recall | > 87% |

### Running Accuracy Tests

```bash
# Run accuracy validation
pytest backend/benchmarks/benchmark_accuracy.py -v

# Generate accuracy report
python3 scripts/generate_accuracy_report.py
```

## Best Practices

1. **Monitor regularly** - Check metrics daily
2. **Set up alerts** - Get notified of quality drops
3. **Review benchmarks** - Run benchmarks before releases
4. **Track trends** - Monitor metrics over time
5. **Investigate failures** - Root cause analysis for quality issues
6. **Update thresholds** - Adjust targets as system improves
