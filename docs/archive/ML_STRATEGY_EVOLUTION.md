# ML-Driven Selector Optimization and Autonomous Strategy Evolution

This document describes the intelligent systems that enable DataForge to learn and adapt extraction strategies automatically.

---

## Overview

DataForge now includes two core ML-driven systems:

1. **Selector ML Optimizer** — Predicts CSS selector quality and generates optimization recommendations
2. **Strategy Evolution Engine** — Learns optimal fetch strategies per domain and evolves them autonomously

Together, these systems enable DataForge to:
- Learn which CSS selectors work best for each domain
- Automatically switch fetch strategies when performance degrades
- Improve extraction accuracy through continuous feedback
- Adapt to anti-bot defenses and DOM changes
- Reduce manual tuning and maintenance overhead

---

## Architecture Philosophy

### Principle 1: Lightweight ML (No External Dependencies)

We use **weighted feature models** instead of external ML libraries (scikit-learn, TensorFlow):

**Why?**
- Keeps the system portable and minimal
- Reduces runtime dependencies
- Makes models interpretable and inspectable
- Enables safe model updates in production
- Allows online learning without retraining

**How?**
- Extract features from selectors/strategies (specificity, stability, success rate, etc.)
- Apply weighted linear combinations to score quality
- Update weights based on actual feedback
- Models are simple, fast, and transparent

### Principle 2: Domain-Specific Learning

Both systems track performance **per domain**:

```python
# Example: Different domains need different strategies
amazon.com   → PLAYWRIGHT_FULL (heavy JS rendering)
quotes.com   → HTTPX_BASIC (simple HTML)
news.site    → HYBRID (fallback strategy)
```

This means:
- No global "best strategy"
- Each domain has its own learning history
- Recommendations adapt to domain characteristics
- Anti-bot defenses are learned locally

### Principle 3: Continuous Feedback Loop

Systems improve through actual extraction results:

```
Extract → Measure Quality → Record Result → Update Model → Improve Prediction
  ↓                                                              ↑
  └──────────────────────────────────────────────────────────────┘
        (Continuous Learning Cycle)
```

---

## Component 1: Selector ML Optimizer

### Purpose

Predict CSS selector quality and recommend improvements, helping DataForge:
- Identify selectors likely to fail
- Generate mutation suggestions
- Track feature importance
- Learn from historical success/failure

### Core Components

#### 1.1 SelectorFeatureExtractor

Extracts 12+ predictive features from CSS selectors:

```python
features = SelectorFeatureExtractor.extract_features(".product-title > span")
```

**Features extracted:**

| Feature | Type | Meaning | Impact |
|---------|------|---------|--------|
| `specificity_score` | float [0-1] | How specific the selector is | Higher = more targeted |
| `stability_score` | float [0-1] | Resistance to DOM changes | Higher = more stable |
| `class_count` | int | Number of CSS classes used | More = less stable |
| `id_count` | int | Number of IDs used | More = more stable |
| `tag_count` | int | Number of tag selectors | More = more targeted |
| `pseudo_class_count` | int | `:nth-child`, `:hover`, etc. | Higher = less stable |
| `attribute_count` | int | `[attr]` selectors | More = more complex |
| `descendant_depth` | int | Nesting depth (capped at 5) | Deeper = more fragile |
| `wildcard_usage` | bool | Uses `*` selector | Present = very generic |
| `uses_text_node` | bool | Uses `:text` or `text()` | Present = fragile |
| `has_nth_child` | bool | Position-based selectors | Present = unstable |
| `has_attribute_match` | bool | `[attr~=val]` style matching | Present = complex |

**Example extraction:**

```python
selector = "div.container > p.text"

features = SelectorFeatureExtractor.extract_features(selector)
# SelectorFeatures(
#   selector="div.container > p.text",
#   specificity_score=0.45,
#   stability_score=0.85,
#   class_count=2,
#   id_count=0,
#   tag_count=2,
#   descendant_depth=1,
#   wildcard_usage=False,
#   ...
# )
```

#### 1.2 SelectorQualityPredictor

Uses weighted features to predict selector quality:

```python
predictor = SelectorQualityPredictor()
features = SelectorFeatureExtractor.extract_features(".product-name")
prediction = predictor.predict(features)
```

**Quality Score Formula:**

```
quality = 0.5 (base score)
  + 0.8 × specificity_score        (specific selectors work better)
  + 0.9 × stability_score          (stable selectors work better)
  + 0.1 × class_count              (more classes = less stable)
  + 0.2 × id_count                 (IDs are good)
  + 0.3 × tag_count                (tags are moderately good)
  - 0.3 × pseudo_class_count       (pseudo-classes hurt)
  - 0.1 × descendant_depth         (deep nesting hurts)
  - 0.5 × wildcard_usage           (wildcards are bad)
  - 0.3 × uses_text_node           (text nodes are fragile)
  - 0.6 × has_nth_child            (position-based is fragile)
  + 0.1 × has_attribute_match      (attribute matching is okay)

Clamped to [0.0, 1.0]
```

**Prediction output:**

```python
prediction = SelectorPrediction(
    selector=".product-name",
    predicted_quality=0.82,           # Expected success rate
    confidence=0.75,                   # Confidence in prediction
    recommendation="keep",             # "keep" | "improve" | "replace"
    suggested_mutations=[              # Alternatives to try
        ".product-name > span",
        ".product",
        ".name",
    ],
    feature_importance={               # Which features matter most
        "stability_score": 0.18,
        "specificity_score": 0.16,
        "class_count": 0.02,
        ...
    }
)
```

**Recommendation Logic:**

- `"keep"`: quality ≥ 0.75 (high quality)
- `"improve"`: 0.50 ≤ quality < 0.75 (moderate, consider alternatives)
- `"replace"`: quality < 0.50 (low quality, should be replaced)

#### 1.3 SelectorOptimizationEngine

Orchestrates optimization and learning:

```python
engine = SelectorOptimizationEngine()

# Optimize all selectors for a domain
report = engine.optimize_selectors(
    domain="amazon.com",
    selectors={
        "title": ".product-title",
        "price": ".product-price",
        "rating": "span[data-rating]",
    },
)

# Learn from actual results
engine.learn_from_results(
    domain="amazon.com",
    selector=".product-title",
    actual_quality=0.95,  # 95% of extractions successful
)
```

**Optimization Report:**

```python
{
    "domain": "amazon.com",
    "timestamp": 1716241234.56,
    "original_count": 3,
    "summary": {
        "total_quality": 0.83,      # Average quality across all selectors
        "keep": 2,                   # High quality
        "improve": 1,                # Moderate quality
        "replace": 0,                # Low quality
    },
    "optimizations": [
        {
            "field_name": "title",
            "selector": ".product-title",
            "predicted_quality": 0.88,
            "recommendation": "keep",
            "suggested_mutations": [...],
            "features": {...},
        },
        ...
    ]
}
```

### Usage Patterns

#### Pattern 1: Optimize selectors before extraction

```python
from app.selector_ml_optimizer import get_selector_optimizer

optimizer = get_selector_optimizer()

# Before extraction, check selector quality
report = optimizer.optimize_selectors(
    domain="example.com",
    selectors=extraction_config["selectors"],
)

# Replace "replace" recommendations
for optimization in report["optimizations"]:
    if optimization["recommendation"] == "replace":
        # Use suggested mutation instead
        new_selector = optimization["suggested_mutations"][0]
        logger.warning(f"Selector degraded, using: {new_selector}")
```

#### Pattern 2: Learn from extraction success

```python
# After successful extraction
extraction_quality = measure_extraction_quality(results)

optimizer.learn_from_results(
    domain="example.com",
    selector=used_selector,
    actual_quality=extraction_quality,  # 0.0-1.0
)
```

#### Pattern 3: Detect selector decay

```python
history = optimizer.get_optimization_history(
    domain="example.com",
    limit=10,  # Last 10 optimizations
)

# Track average quality over time
recent_quality = [h["summary"]["total_quality"] for h in history[-5:]]
quality_trend = recent_quality[-1] - recent_quality[0]

if quality_trend < -0.1:  # Quality dropped by 10%
    logger.warning("Selector decay detected, triggering rediscovery")
    trigger_selector_rediscovery()
```

### Weight Updates (Learning)

The predictor learns by updating feature weights:

```python
# Collect feedback from extraction results
feedback = [
    (features_1, actual_quality_1),
    (features_2, actual_quality_2),
    (features_3, actual_quality_3),
]

# Update weights to fit observed results
predictor.update_weights(feedback, learning_rate=0.01)
```

**How learning works:**

```
For each (features, actual_quality):
    1. Predict quality with current weights
    2. Calculate error = actual_quality - predicted_quality
    3. For each feature:
        adjustment = learning_rate × error × feature_value
        weight += adjustment
```

This is simple gradient descent—selectors that perform better than predicted increase their feature weights, improving future predictions.

---

## Component 2: Strategy Evolution Engine

### Purpose

Autonomously select and evolve fetch strategies per domain:

```python
# System learns that amazon.com needs Playwright
# for JavaScript rendering, while quotes.com
# works fine with httpx for faster extraction
```

### Core Components

#### 2.1 FetchStrategy Enum

Available strategies:

```python
class FetchStrategy(str, Enum):
    PLAYWRIGHT_FULL = "playwright_full"           # Full browser, all JS
    PLAYWRIGHT_LIGHTWEIGHT = "playwright_lightweight"  # Minimal JS
    HTTPX_BASIC = "httpx_basic"                   # Plain HTTP, no JS
    HTTPX_WITH_UA = "httpx_with_ua"               # HTTP + browser UA
    HYBRID = "hybrid"                              # Try HTTPX first, fallback
    CACHED = "cached"                              # Use cached response
```

**Strategy characteristics:**

| Strategy | Speed | JS Support | Stealth | Cost | Use Case |
|----------|-------|-----------|---------|------|----------|
| Playwright Full | Slow | Full | Low | High | Heavy JS |
| Playwright Lightweight | Medium | Partial | Low | Medium | Light JS |
| HTTPX Basic | Fast | None | Medium | Low | Static HTML |
| HTTPX + UA | Fast | None | High | Low | User-Agent needed |
| Hybrid | Medium | Full | High | Medium | Unknown |
| Cached | Instant | N/A | N/A | None | Reuse |

#### 2.2 StrategyPerformance

Tracks per-strategy performance on a domain:

```python
perf = StrategyPerformance(
    domain="amazon.com",
    strategy=FetchStrategy.PLAYWRIGHT_FULL,
    success_count=85,
    failure_count=15,
    total_time_ms=42500.0,
    avg_quality=0.92,
    consecutive_failures=0,
)

print(f"Success rate: {perf.success_rate:.1%}")  # 85.0%
print(f"Avg time: {perf.avg_time_ms:.0f}ms")     # 500ms
print(f"Health: {'healthy' if perf.is_healthy else 'degraded'}")
```

**Health assessment:**

- `is_healthy`: success_rate ≥ 80% AND no failure streaks
- `is_degraded`: success_rate < 60% OR consecutive_failures ≥ 3

#### 2.3 DomainStrategyState

Tracks all strategies for a domain:

```python
state = DomainStrategyState(domain="amazon.com")

# Record attempts
state.record_attempt(
    strategy=FetchStrategy.PLAYWRIGHT_FULL,
    success=True,
    time_ms=450.0,
    quality=0.95,
)

# Get best performing strategy
best = state.get_best_strategy()
# → FetchStrategy.PLAYWRIGHT_FULL
```

#### 2.4 StrategyEvolutionEngine

Recommends and evolves strategies:

```python
from app.strategy_evolution import get_strategy_evolution_engine

engine = get_strategy_evolution_engine()

# Record a fetch attempt
engine.record_fetch_attempt(
    domain="amazon.com",
    strategy=FetchStrategy.PLAYWRIGHT_FULL,
    success=True,
    time_ms=450.0,
    quality=0.95,
)

# Get recommendation for next attempt
recommendation = engine.recommend_strategy("amazon.com")

print(f"Use: {recommendation.recommended_strategy}")
print(f"Confidence: {recommendation.confidence:.1%}")
print(f"Alternatives: {recommendation.alternatives}")
print(f"Reason: {recommendation.reason}")
```

**Output example:**

```
Use: FetchStrategy.PLAYWRIGHT_FULL
Confidence: 92.0%
Alternatives: [PLAYWRIGHT_LIGHTWEIGHT, HTTPX_WITH_UA]
Reason: High performance: 88.0% success rate
```

### Strategy Scoring

When multiple strategies have data, the engine scores them:

```
score = (success_rate × 100) + max(0, 50 - avg_time_ms/10)
      = Prioritize success, with speed as secondary factor
```

**Examples:**

| Strategy | Success | Time | Score | Rank |
|----------|---------|------|-------|------|
| PLAYWRIGHT_FULL | 88% | 450ms | 93.5 | 1st |
| HTTPX_WITH_UA | 82% | 120ms | 94.0 | 1st tied |
| PLAYWRIGHT_LIGHTWEIGHT | 75% | 300ms | 80.0 | 3rd |

### Usage Patterns

#### Pattern 1: Record fetch attempts

```python
# During extraction
start_time = time.time()
try:
    result = fetch_with_strategy(domain, strategy)
    success = check_quality(result)
    quality = measure_quality(result)
except Exception as e:
    success = False
    quality = 0.0

time_ms = (time.time() - start_time) * 1000

# Record for learning
engine.record_fetch_attempt(
    domain=domain,
    strategy=strategy,
    success=success,
    time_ms=time_ms,
    quality=quality,
    failure_reason=e.reason if not success else None,
)
```

#### Pattern 2: Get strategy recommendations

```python
# Before fetch attempt
recommendation = engine.recommend_strategy(domain)

if recommendation.confidence > 0.8:
    # Use recommended strategy
    strategy = recommendation.recommended_strategy
else:
    # Insufficient data, use default
    strategy = FetchStrategy.PLAYWRIGHT_FULL

# Execute fetch with selected strategy
result = fetch_with_strategy(domain, strategy)
```

#### Pattern 3: Switch on degradation

```python
# After several failed attempts
if engine.should_switch_strategy(domain):
    # Current strategy is degraded
    new_strategy = engine.evolve_strategy(domain)

    logger.info(
        f"Strategy switch for {domain}: "
        f"{old_strategy} → {new_strategy}"
    )

    # Try again with new strategy
    result = fetch_with_strategy(domain, new_strategy)
```

#### Pattern 4: Generate reports

```python
# Domain-specific analysis
domain_report = engine.get_domain_strategy_report("amazon.com")

print(f"Current strategy: {domain_report['current_strategy']}")
print(f"Strategy switches: {domain_report['strategy_switches']}")
print(f"Total attempts: {domain_report['total_attempts']}")

for strategy_info in domain_report["strategies"]:
    print(f"  {strategy_info['strategy']}: "
          f"{strategy_info['success_rate']:.1%} success "
          f"({strategy_info['success_count']} successes)")

# System-wide analysis
system_report = engine.get_all_domains_strategy_report()

print(f"Total domains: {system_report['total_domains']}")
print(f"Average success rate: {system_report['avg_success_rate']:.1%}")

# Find best/worst performing domains
for domain_info in system_report["domains"][:5]:
    print(f"  {domain_info['domain']}: "
          f"{domain_info['success_rate']:.1%} with "
          f"{domain_info['best_strategy']}")
```

---

## Integration with Recovery Framework

Both ML systems integrate with the existing recovery framework:

```
Recovery Flow:
┌─────────────┐
│  Extraction │
│   Attempt   │
└──────┬──────┘
       │
       ├─→ Selector Optimization:
       │   "Is this selector degrading?"
       │
       ├─→ Strategy Evolution:
       │   "Is this strategy working?"
       │
       ├─→ Failure Classification:
       │   "What went wrong?"
       │
       ├─→ Recovery Strategies:
       │   "How do we recover?"
       │
       └─→ Learning:
           "Update models with result"
```

### Example: Integrated Recovery

```python
# 1. Extraction fails
result = extract_with_current_selector()

# 2. Classify failure
classification = classify_failure(result)

# 3. Check selector health
optimizer = get_selector_optimizer()
selector_report = optimizer.optimize_selectors(
    domain=domain,
    selectors=current_selectors,
)

# 4. If selectors are degrading
if selector_report["summary"]["total_quality"] < 0.6:
    # Trigger rediscovery with recovery system
    recovery_plan = recovery_strategist.generate_recovery_plan(
        FailureClassification(
            category=FailureCategory.SELECTOR_DECAY,
            confidence=0.95,
        ),
        attempt_number=1,
    )
    # Execute recovery actions...

# 5. Check strategy health
evolution_engine = get_strategy_evolution_engine()
if evolution_engine.should_switch_strategy(domain):
    # Evolve to better strategy
    new_strategy = evolution_engine.evolve_strategy(domain)
    # Retry with new strategy...

# 6. Learn from result
optimizer.learn_from_results(
    domain=domain,
    selector=used_selector,
    actual_quality=final_quality,
)

engine.record_fetch_attempt(
    domain=domain,
    strategy=used_strategy,
    success=success,
    time_ms=elapsed_time,
    quality=final_quality,
)
```

---

## API Endpoints

### Selector ML Endpoints

**POST `/api/scraper/ml/optimize/domain/{domain}`**

Optimize all selectors for a domain.

```bash
curl -X POST http://localhost:8000/api/scraper/ml/optimize/domain/amazon.com \
  -H "Content-Type: application/json" \
  -d '{
    "selectors": {
      "title": ".product-title",
      "price": ".product-price"
    }
  }'
```

Response:
```json
{
  "domain": "amazon.com",
  "timestamp": 1716241234.56,
  "summary": {
    "total_quality": 0.85,
    "keep": 1,
    "improve": 1,
    "replace": 0
  },
  "optimizations": [...]
}
```

**GET `/api/scraper/ml/optimize/domain/{domain}/history`**

Get optimization history for domain.

```bash
curl http://localhost:8000/api/scraper/ml/optimize/domain/amazon.com/history?limit=10
```

**POST `/api/scraper/ml/learn`**

Record selector performance feedback.

```bash
curl -X POST http://localhost:8000/api/scraper/ml/learn \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "amazon.com",
    "selector": ".product-title",
    "actual_quality": 0.95
  }'
```

### Strategy Evolution Endpoints

**GET `/api/scraper/strategy/recommend/{domain}`**

Get strategy recommendation for domain.

```bash
curl http://localhost:8000/api/scraper/strategy/recommend/amazon.com
```

Response:
```json
{
  "recommended_strategy": "playwright_full",
  "confidence": 0.92,
  "estimated_success_rate": 0.88,
  "reason": "High performance: 88.0% success rate",
  "alternatives": ["playwright_lightweight", "httpx_with_ua"]
}
```

**POST `/api/scraper/strategy/record`**

Record strategy attempt result.

```bash
curl -X POST http://localhost:8000/api/scraper/strategy/record \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "amazon.com",
    "strategy": "playwright_full",
    "success": true,
    "time_ms": 450.0,
    "quality": 0.95
  }'
```

**GET `/api/scraper/strategy/domain/{domain}`**

Get detailed strategy analysis for domain.

```bash
curl http://localhost:8000/api/scraper/strategy/domain/amazon.com
```

**GET `/api/scraper/strategy/report`**

Get system-wide strategy report.

```bash
curl http://localhost:8000/api/scraper/strategy/report
```

---

## Testing

### Selector ML Tests (31 tests)

```bash
pytest backend/tests/test_selector_ml_optimizer.py -v
```

Tests cover:
- Feature extraction correctness
- Quality prediction accuracy
- Mutation suggestions
- Weight updates and learning
- Batch operations
- Integration workflows

### Strategy Evolution Tests (33 tests)

```bash
pytest backend/tests/test_strategy_evolution.py -v
```

Tests cover:
- Strategy performance tracking
- Recommendation logic
- Strategy switching
- Degradation detection
- Learning and adaptation
- Multi-domain independence
- Report generation

---

## Best Practices

### 1. Continuous Feedback

Always record results, even failures:

```python
# Good: Records both success and failure
engine.record_fetch_attempt(
    domain=domain,
    strategy=strategy,
    success=success,  # Boolean
    time_ms=time_ms,
    quality=quality if success else 0.0,
)
```

### 2. Domain-Specific Tuning

Different domains need different strategies:

```python
# Bad: Global strategy for all domains
strategy = FetchStrategy.PLAYWRIGHT_FULL  # Same for everything

# Good: Per-domain strategy
recommendation = engine.recommend_strategy(domain)
strategy = recommendation.recommended_strategy
```

### 3. Sufficient Data Before Trusting Predictions

Don't trust recommendations until you have enough attempts:

```python
recommendation = engine.recommend_strategy(domain)

if recommendation.confidence < 0.5:
    # Not enough data yet, use default
    strategy = FetchStrategy.PLAYWRIGHT_FULL
else:
    # Enough data, trust recommendation
    strategy = recommendation.recommended_strategy
```

### 4. Monitor Degradation

Watch for selector and strategy decay:

```python
# Track selector quality over time
history = optimizer.get_optimization_history(domain, limit=10)
recent_quality = [h["summary"]["total_quality"] for h in history[-5:]]

if recent_quality[-1] < 0.7:
    logger.warning("Selector quality degrading")
    trigger_rediscovery()

# Track strategy health
if engine.should_switch_strategy(domain):
    logger.warning("Strategy degraded")
    new_strategy = engine.evolve_strategy(domain)
```

### 5. Batch Learning

Update models with multiple data points for better learning:

```python
# Good: Batch learning
feedback = [
    (features1, quality1),
    (features2, quality2),
    (features3, quality3),
]
predictor.update_weights(feedback, learning_rate=0.01)
```

---

## Performance Characteristics

### Selector ML Optimizer

- **Feature extraction**: ~0.1ms per selector
- **Quality prediction**: ~0.05ms per selector
- **Batch optimization**: ~5ms for 50 selectors
- **Weight update**: ~0.2ms per feedback sample

### Strategy Evolution Engine

- **Recommendation**: ~0.1ms per domain
- **Recording attempt**: ~0.05ms per attempt
- **Report generation**: ~1ms per domain

Both systems are designed for production use with negligible overhead.

---

## Future Enhancements

1. **Temporal modeling**: Track how strategy effectiveness changes over time
2. **Anti-bot learning**: Detect anti-bot escalation patterns
3. **Selector cross-domain transfer**: Learn from similar domains
4. **Strategy ensembles**: Combine multiple strategies probabilistically
5. **Reinforcement learning**: More sophisticated strategy evolution
6. **Predictive degradation**: Anticipate failures before they happen

---

## Summary

The ML and Strategy Evolution systems represent a major step toward **autonomous, self-improving extraction**:

- **Selector ML** helps identify and fix degraded selectors
- **Strategy Evolution** learns which approach works best per domain
- **Together** they create a feedback loop that continuously improves extraction quality
- **Integration** with recovery makes DataForge more resilient and self-healing

This moves DataForge from a **static configuration system** toward **adaptive intelligence**.
