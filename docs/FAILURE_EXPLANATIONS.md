# Failure Explanations

**Date:** 2026-06-13
**Status:** Implemented

---

## Overview

Maps technical failure signals to actionable user messages.

## Failure Types

| Type | User Message | Recommended Action |
|------|-------------|------------------|
| `login_required` | "This page requires a login. Please create an Auth Profile to access it." | Create an Auth Profile |
| `session_expired` | "Your session for this website has expired. Please reconnect this Auth Profile." | Reconnect Auth Profile |
| `session_url` | "This URL appears to use a temporary session. Direct scraping may not work reliably." | Use Workflow Replay |
| `selector_not_found` | "The page structure has changed and the expected data cannot be found." | Repair mapping |
| `blocked_or_challenge` | "The website is showing a challenge or blocking automated access." | Pause/retry later |
| `timeout` | "The page took too long to load." | Increase wait or reduce scope |
| `network_error` | "Could not reach the website." | Check URL, retry later |
| `no_records_found` | "No data records were found on this page." | Verify selectors |
| `quota_exceeded` | "You have reached your usage limit for this plan." | Upgrade plan |
| `domain_blocked` | "This website is not allowed for scraping." | Review AUP |

## Usage

```python
from app.failure_explainer import detect_failure, explain_failure

# Automatic detection
explanation = detect_failure(http_status=401)

# Manual lookup
explanation = explain_failure("login_required")
```

## Tests

`backend/tests/test_extraction_depth.py`
