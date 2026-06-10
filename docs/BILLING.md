# Billing & Usage Documentation

## Overview

DataForge includes a usage ledger and quota system for tracking API usage and enforcing limits.

## Usage Tracking

### Usage Types

| Type | Description | Unit |
|------|-------------|------|
| `job_created` | Jobs created | Per job |
| `job_completed` | Jobs completed | Per job |
| `page_fetched` | Pages fetched | Per page |
| `ai_structuring` | AI structuring calls | Per call |
| `export_generated` | Export files generated | Per export |
| `api_request` | API requests | Per request |

### Recording Usage

```python
from app.utils.usage_ledger import get_usage_ledger, UsageType

ledger = get_usage_ledger()

# Record usage
ledger.record_usage(
    user_id="user123",
    usage_type=UsageType.PAGE_FETCHED,
    quantity=10,
    metadata={"url": "https://example.com"}
)
```

### Querying Usage

```python
from app.utils.usage_ledger import get_usage_ledger, UsageType

ledger = get_usage_ledger()

# Get all usage for a user
usage = ledger.get_usage("user123")

# Get usage by type
page_fetches = ledger.get_usage("user123", usage_type=UsageType.PAGE_FETCHED)

# Get usage summary
summary = ledger.get_usage_summary("user123")
print(summary)
# {
#   "user_id": "user123",
#   "period": {"start": null, "end": null},
#   "usage": {
#     "job_created": {"count": 5, "total_quantity": 5},
#     "page_fetched": {"count": 100, "total_quantity": 1000},
#     ...
#   }
# }
```

## Quota System

### Setting Quotas

```python
from app.utils.usage_ledger import get_usage_ledger, UsageType, QuotaPeriod

ledger = get_usage_ledger()

# Set monthly quota for page fetches
ledger.set_quota(
    user_id="user123",
    usage_type=UsageType.PAGE_FETCHED,
    limit=10000,
    period=QuotaPeriod.MONTHLY
)
```

### Checking Quotas

```python
from app.utils.usage_ledger import get_usage_ledger, UsageType

ledger = get_usage_ledger()

# Check if user has quota available
has_quota, quota = ledger.check_quota("user123", UsageType.PAGE_FETCHED)

if has_quota:
    # Allow the operation
    pass
else:
    # Quota exceeded
    print(f"Quota exceeded: {quota.current_usage}/{quota.limit}")
```

### Quota Enforcement

```python
from app.utils.usage_ledger import get_usage_ledger, UsageType

ledger = get_usage_ledger()

def process_request(user_id: str, pages: int):
    # Check quota
    has_quota, quota = ledger.check_quota(user_id, UsageType.PAGE_FETCHED)
    if not has_quota:
        raise QuotaExceededError(f"Page fetch quota exceeded: {quota.current_usage}/{quota.limit}")

    # Process request
    result = fetch_pages(pages)

    # Record usage
    ledger.record_usage(user_id, UsageType.PAGE_FETCHED, quantity=pages)

    return result
```

## Pricing Tiers

### Free Tier

| Feature | Limit |
|---------|-------|
| Jobs per month | 10 |
| Pages per month | 1,000 |
| AI structuring | 100 calls |
| Exports | 50 per month |
| API requests | 1,000 per month |

### Pro Tier ($29/month)

| Feature | Limit |
|---------|-------|
| Jobs per month | 100 |
| Pages per month | 10,000 |
| AI structuring | 1,000 calls |
| Exports | 500 per month |
| API requests | 10,000 per month |

### Enterprise Tier ($99/month)

| Feature | Limit |
|---------|-------|
| Jobs per month | Unlimited |
| Pages per month | 100,000 |
| AI structuring | 10,000 calls |
| Exports | Unlimited |
| API requests | 100,000 per month |

## Billing Integration

### Stripe Integration (Planned)

```python
# Future integration
from stripe import Customer

def create_customer(user_id: str, email: str):
    customer = Customer.create(
        email=email,
        metadata={"user_id": user_id}
    )
    return customer

def create_subscription(customer_id: str, price_id: str):
    subscription = Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
        metadata={"user_id": customer_id}
    )
    return subscription
```

### Usage-Based Billing

```python
# Calculate monthly bill
def calculate_bill(user_id: str, month: int, year: int):
    ledger = get_usage_ledger()

    # Get usage for the month
    start_date = datetime(year, month, 1)
    end_date = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)

    summary = ledger.get_usage_summary(user_id, start_date, end_date)

    # Calculate costs based on pricing tiers
    costs = {
        "page_fetched": summary["usage"]["page_fetched"]["total_quantity"] * 0.001,
        "ai_structuring": summary["usage"]["ai_structuring"]["total_quantity"] * 0.01,
    }

    return {
        "user_id": user_id,
        "month": f"{year}-{month:02d}",
        "usage": summary["usage"],
        "costs": costs,
        "total": sum(costs.values()),
    }
```

## API Endpoints

### Usage Summary

```bash
# Get usage summary
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/usage/summary

# Get usage by type
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/usage?type=page_fetched
```

### Quota Status

```bash
# Get quota status
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/quota
```

## Monitoring

### Usage Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `dataforge_usage_total` | Counter | user_id, type | Total usage |
| `dataforge_quota_usage` | Gauge | user_id, type | Current quota usage |
| `dataforge_quota_limit` | Gauge | user_id, type | Quota limit |

### Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| High Usage | `usage > 80% of quota` | Warning |
| Quota Exceeded | `usage >= quota` | Critical |
| Unusual Spike | `usage > 2x average` | Info |

## Best Practices

1. **Record all billable events** - Ensure every usage is tracked
2. **Check quotas before operations** - Prevent overages
3. **Reset quotas monthly** - Use scheduled jobs
4. **Monitor usage patterns** - Detect anomalies
5. **Provide usage dashboards** - Let users see their usage
6. **Send quota warnings** - Alert users before limits

## Future Enhancements

1. **Real-time usage dashboard** - Live usage visualization
2. **Usage alerts** - Notify users at 80% and 100%
3. **Overage handling** - Automatic plan upgrades
4. **Usage export** - CSV/JSON export for accounting
5. **Multi-currency support** - International billing
6. **Team billing** - Usage aggregation for teams
