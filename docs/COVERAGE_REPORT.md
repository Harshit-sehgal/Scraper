# Coverage Report

**Generated:** 2026-06-10 09:03:49 UTC

## Summary

- **Total Coverage:** 78.8%
- **Lines Covered:** 23,736 / 30,118
- **Coverage Gaps:** 9 modules below threshold

## Coverage Gaps

| Module | Coverage | Threshold | Status |
|--------|----------|-----------|--------|
| `app/services/notifications.py` | 0.0% | 65% | ⚠️ Below threshold |
| `app/utils/env.py` | 0.0% | 60% | ⚠️ Below threshold |
| `app/utils/rate_limit.py` | 0.0% | 60% | ⚠️ Below threshold |
| `app/utils/log_redaction.py` | 48.0% | 60% | ⚠️ Below threshold |
| `app/routers/scraper.py` | 48.9% | 70% | ⚠️ Below threshold |
| `app/services/state.py` | 51.2% | 65% | ⚠️ Below threshold |
| `app/routers/experimental.py` | 55.6% | 70% | ⚠️ Below threshold |
| `app/routers/jobs_state.py` | 60.4% | 70% | ⚠️ Below threshold |
| `app/routers/system.py` | 63.3% | 70% | ⚠️ Below threshold |

## Recommendations

1. Add tests for modules below threshold
2. Focus on critical paths first (routers, services)
3. Use `# pragma: no cover` for intentionally uncovered code
4. Update MODULE_THRESHOLDS in this script as coverage improves
