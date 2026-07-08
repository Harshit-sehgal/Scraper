# ARCHITECTURE.md - Complete System Documentation

**Purpose**: Single source of truth for DataForge system architecture  
**Audience**: Engineers, operators, new team members  
**Status**: Phase 5 Complete + Production Hardening  
**Last Updated**: May 26, 2026

---

## Quick Start: System Overview

DataForge is a **self-adaptive web scraping infrastructure** with:
- **14 interconnected systems** (crawl, fetch, extract, recovery, memory, intelligence, telemetry, distributed)
- **4 continuous learning loops** (selectors, strategies, domain evolution, degradation prediction)
- **Predictive intelligence** (anticipates failures before they occur)
- **Autonomous adaptation** (adjusts without human intervention)
- **100% type-safe** (mypy clean across 103 files)
- **698 comprehensive tests** (0 failures)

---

## System Layers & Components

### Layer 1: Crawl Layer
**Responsibility**: URL discovery and frontier management

**Components**:
- `crawl_frontier.py`: URL priority queue, scheduling
- `crawl_policy.py`: Rate limiting, politeness
- Deduplication: URL history tracking

**Data Flow**:
```
Job Request
    ↓
Frontier Dequeues URL (per priority)
    ↓
Policy Checks Rate Limits & Politeness
    ↓
Pass to Fetch Layer
```

**Ownership**: URL orchestration  
**Dependencies**: History state, observability  
**Async Model**: Event-driven (URL → Fetch)  

---

### Layer 2: Fetch Layer
**Responsibility**: HTTP/Browser execution, strategy selection

**Components**:
- `browser_pool.py`: Playwright instance management
- `strategy_evolution.py`: Autonomous strategy selection per domain
- `anti_bot_engine.py`: Detection & evasion
- `proxy_manager.py`: IP rotation, anonymity

**Strategies Available** (6 total):
- `PLAYWRIGHT_FULL`: Full browser rendering (heavy JS)
- `PLAYWRIGHT_LIGHTWEIGHT`: Minimal JS execution (faster)
- `HTTPX_BASIC`: Plain HTTP, no JavaScript
- `HTTPX_WITH_UA`: HTTP with browser user-agent
- `HYBRID`: Try HTTPX first, fallback to Playwright
- `CACHED`: Use cached response from domain

**Data Flow**:
```
URL + Domain Context
    ↓
Strategy Evolution Engine Recommends Strategy
    (Per-domain learning: what works best?)
    ↓
Anti-Bot Engine Applies Evasion
    (Detect defense, respond)
    ↓
Proxy Manager Selects IP
    (Rotation, anonymity)
    ↓
Browser/HTTP Execution
    ↓
Response (HTML/JS-rendered)
```

**Ownership**: Remote resource fetching  
**Dependencies**: Strategy history, anti-bot patterns, proxy data  
**Async Model**: Concurrent with resource limits  
**Key Learning**: Strategy performance per domain  

---

### Layer 3: Extraction Layer
**Responsibility**: DOM parsing, selector application, value extraction

**Components**:
- `selector_engine.py`: CSS/XPath evaluation
- `selector_ml_optimizer.py`: Selector quality prediction
- `selector_decay_predictor.py`: Early warning for degrading selectors
- `selector_discovery.py`: Automated selector finding
- `selector_memory.py`: Learned selector patterns
- `field_validator.py`: Output correctness checking

**Data Flow**:
```
Rendered HTML/DOM
    ↓
Selector ML Optimizer Predicts Quality
    (Which selectors are reliable?)
    ↓
Selector Engine Applies Selectors
    (Extract values from DOM)
    ↓
Field Validator Checks Output
    (Is extracted data valid?)
    ↓
Decay Predictor Monitors Quality
    (Early warning if degrading)
    ↓
Extracted Fields
```

**Ownership**: DOM parsing and value extraction  
**Dependencies**: Selector memory, ML predictions, validation rules  
**Async Model**: Sequential per page  
**Key Learning**: Selector quality and patterns  

---

### Layer 4: Recovery Layer
**Responsibility**: Failure classification, recovery planning, action execution

**Components**:
- `failure_classification.py`: Categorize failures (hydration, selector decay, anti-bot, etc.)
- `recovery_strategies.py`: Generate recovery plans per failure type
- `recovery_handlers.py`: Execute recovery actions (retry, proxy rotate, selector rediscovery, etc.)
- `scraper_recovery_integration.py`: Recovery wrapper for extraction

**Failure Categories**:
- `HYDRATION_FAILURE`: JavaScript didn't render
- `SELECTOR_DECAY`: Selector no longer works
- `ANTI_BOT_BLOCK`: Site detected automation
- `TIMEOUT`: Request took too long
- `INVALID_RESPONSE`: Server returned error
- `NETWORK_ERROR`: Connection problem
- `RESOURCE_EXHAUSTED`: Browser/memory limit

**Data Flow**:
```
Extraction Fails
    ↓
Failure Classification Categorizes
    (What type of failure? Why?)
    ↓
Recovery Strategist Generates Plan
    (What should we try next?)
    ↓
Recovery Handlers Execute Actions
    - Increase hydration wait
    - Rotate proxy
    - Force selector rediscovery
    - Backoff and slow
    - Escalate to LLM
    ↓
Retry Extraction
```

**Ownership**: Failure handling and recovery  
**Dependencies**: Failure patterns, recovery actions, domain history  
**Async Model**: Retry loop with backoff  
**Key Learning**: Recovery effectiveness per failure type  

---

### Layer 5: Memory Layer
**Responsibility**: State management, learning signals, knowledge persistence

**Components**:
- `semantic_world_state.py`: Global knowledge base
- `selector_memory.py`: Learned selector patterns per domain
- `persistence_state.py`: Storage management
- `history_state.py`: Change tracking and audit log
- `domain_health_alerts.py`: Health monitoring per domain

**Learning Signals Flow**:
```
Extraction Result
    ↓
Quality Measurement (0-1 score)
    ↓
Update Selector Memory
    (This selector worked/failed)
    ↓
Update Domain Health
    (Domain trending up/down?)
    ↓
Feed ML Optimizers
    (Improve predictions)
    ↓
Persist State
    (Durable learning)
```

**Ownership**: State management and learning  
**Dependencies**: All systems (receives feedback)  
**Async Model**: Asynchronous writes to persistence  
**Key Learning**: Everything feeds here  

---

### Layer 6: Intelligence Layer
**Responsibility**: LLM reasoning, semantic understanding, structured synthesis

**Components**:
- `llm_bridge.py`: Claude API integration
- `semantic_pipeline.py`: Structured reasoning workflow
- `semantic_world_state.py`: Knowledge representation

**Use Cases**:
- Complex field extraction (multi-step reasoning)
- Schema inference (understand data structure)
- Quality validation (semantic correctness)
- Recovery escalation (when automated recovery insufficient)

**Data Flow**:
```
Complex Extraction Challenge
    ↓
LLM Bridge Formulates Query
    (Structure problem for Claude)
    ↓
Claude Provides Reasoning
    (Structured output)
    ↓
Results Integrated Back
    (Feed memory, validators)
```

**Ownership**: AI-powered reasoning  
**Dependencies**: Extracted data, domain context  
**Async Model**: On-demand (for difficult cases)  
**Key Learning**: Patterns of reasoning  

---

### Layer 7: Telemetry Layer
**Responsibility**: Observability, metrics propagation, diagnostics

**Components**:
- `observability.py`: Metrics collection and tracing
- `scrape_telemetry.py`: Extraction-specific metrics
- `domain_intelligence.py`: Per-domain analytics
- `scraper_diagnostics.py`: Health monitoring

**Metrics Tracked**:
- Extraction success rate per domain
- Selector quality trends
- Strategy effectiveness per domain
- Failure patterns and recovery rates
- Response times and resource usage
- Anti-bot escalation patterns

**Data Flow**:
```
All Systems
    ↓
Emit Events/Metrics
    ↓
Telemetry Layer Aggregates
    (Time series data)
    ↓
Domain Intelligence Analyzes
    (Per-domain patterns)
    ↓
Diagnostics Reports Health
    (What's working? What's not?)
```

**Ownership**: Observability and reporting  
**Dependencies**: All systems (observes everything)  
**Async Model**: Asynchronous metric writes  
**Key Learning**: System behavior patterns  

---

### Layer 8: Distributed Layer
**Responsibility**: Multi-node coordination, consensus, topology tracking

**Components**:
- `gossip_substrate.py`: Peer-to-peer communication
- `heartbeat_manager.py`: Liveness detection
- `topology_state.py`: Network topology tracking
- Consensus protocols: Distributed agreement on state

**Data Flow**:
```
State Change on Node A
    ↓
Gossip Substrate Broadcasts to Peers
    (Probabilistic propagation)
    ↓
Heartbeat Manager Monitors Liveness
    (Are nodes still alive?)
    ↓
Topology State Tracks Network
    (Which nodes know about which?)
    ↓
Consensus Protocol Agrees on State
    (Distributed knowledge)
```

**Ownership**: Multi-node coordination  
**Dependencies**: State changes from all layers  
**Async Model**: Continuous gossip and heartbeat  
**Key Learning**: Network topology and consensus  

---

## Data Flow: Complete Extraction Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    COMPLETE PIPELINE                        │
└─────────────────────────────────────────────────────────────┘

1. CRAWL LAYER
   Job Request
        ↓
   Frontier Dequeues URL
        ↓
   Policy Checks Politeness
        ↓
   ✓ Ready to Fetch

2. FETCH LAYER
   Strategy Evolution Recommends Strategy
        ↓
   Anti-Bot Engine Applies Evasion
        ↓
   Proxy Manager Selects IP
        ↓
   Browser/HTTP Executes
        ↓
   Response Received

3. EXTRACTION LAYER
   Selector ML Predicts Quality
        ↓
   Selector Engine Applies Selectors
        ↓
   Field Validator Checks Output
        ↓
   Decay Predictor Monitors
        ↓
   Fields Extracted

4. RECOVERY ON FAILURE
   Failure Classification Categorizes
        ↓
   Recovery Strategist Plans
        ↓
   Recovery Handlers Execute
        ↓
   Retry (Loop back to Fetch/Extract)

5. MEMORY & LEARNING
   Update Selector Memory
        ↓
   Update Domain Health
        ↓
   Feed ML Optimizers
        ↓
   Persist State

6. INTELLIGENCE (If Needed)
   Complex Fields → LLM Bridge
        ↓
   Claude Reasoning
        ↓
   Integrate Results

7. TELEMETRY
   All Events → Observability
        ↓
   Aggregate Metrics
        ↓
   Domain Intelligence
        ↓
   Diagnostics Reports

8. DISTRIBUTED (If Multi-Node)
   State Changes → Gossip
        ↓
   Heartbeat Monitoring
        ↓
   Consensus Agreement
```

---

## The Four Learning Loops

### Loop 1: Selector Quality Learning
**Frequency**: Per extraction attempt  
**Learning Mechanism**: Weight updates based on actual results

```
Extract with selector → Measure success/quality
    ↓
Compare to ML prediction → Calculate error
    ↓
Update predictor weights → Improve future predictions
    ↓
Store in selector memory → Per-domain pattern tracking
```

**Impact**: Selectors automatically improve over time

### Loop 2: Strategy Evolution
**Frequency**: Per fetch attempt  
**Learning Mechanism**: Performance tracking and recommendation

```
Execute with strategy → Record success/failure/time
    ↓
Compare performance across strategies → Score effectiveness
    ↓
Recommend best strategy → Update per-domain preference
    ↓
Auto-switch if degraded → Continuous optimization
```

**Impact**: Each domain learns its optimal strategy

### Loop 3: Domain Evolution
**Frequency**: Per domain (hourly/daily)  
**Learning Mechanism**: Mutation pattern analysis

```
Monitor selector success → Detect structure changes
    ↓
Track anti-bot patterns → Model escalation
    ↓
Calculate volatility index → Predict behavior
    ↓
Schedule proactively → Adjust crawl timing
```

**Impact**: Anticipate domain changes before failure

### Loop 4: Degradation Prediction
**Frequency**: Continuous  
**Learning Mechanism**: Trend analysis and early warning

```
Track quality trends → Detect degradation patterns
    ↓
Predict failure point → Calculate time to failure
    ↓
Generate early warning → Alert operators/systems
    ↓
Trigger proactive recovery → Before extraction breaks
```

**Impact**: Prevent failures rather than recover from them

---

## Async Boundaries & Concurrency Model

### Async Boundaries (Where async/await happens)

**1. Between Layers**:
```
Crawl → Fetch: Async (queue-based)
Fetch → Extract: Sync (waits for response)
Extract → Recovery: Sync (immediate handling)
Recovery → Crawl: Async (retry queued)
```

**2. Within Layers**:
```
Crawl: Async frontier operations
Fetch: Concurrent fetches with resource limits
Extract: Sequential per page (fast)
Recovery: Async handler execution
Memory: Async persistence
Telemetry: Async metric writes
Distributed: Continuous async gossip
```

**3. Learning Loops**:
```
ML Updates: Async (doesn't block extraction)
Domain Evolution: Async (batch updates)
Degradation Checks: Async (background monitoring)
```

---

## Dependency Graph

### Clean Dependency Flow (What depends on what)

```
Crawl Layer (independent)
    ↓
Fetch Layer (depends on: crawl signals)
    ↓
Extract Layer (depends on: fetch response)
    ↓
Recovery Layer (depends on: extract result)
    ↓
Memory Layer (depends on: all layers)
    ↓
(These can be parallel or sequential)
├─→ Intelligence Layer (depends on: extract)
├─→ Telemetry Layer (depends on: all)
└─→ Distributed Layer (depends on: memory)
```

### NO Circular Dependencies ✓

- Crawl does NOT depend on other layers
- Fetch does NOT depend on Extract
- Extract does NOT depend on Recovery feedback
- All asymmetric (unidirectional)

---

## Integration Points & Boundaries

### Hard Boundaries (Never crossed)
- Crawl ↔ Extract (only via Fetch)
- Crawl ↔ Recovery (only via Extraction failure)
- Memory ↔ Fetch (memory reads only, doesn't control fetch)

### Soft Boundaries (Interface-based)
- Fetch → Strategy Recommendation (via engine interface)
- Extract → Selector Quality (via ML interface)
- Recovery → Classification (via categorizer interface)

### Learning Points (Feedback)
- Extract → Memory (quality signals)
- Fetch → Strategy (performance data)
- Recovery → Classification (outcome data)
- Extract → Domain Health (metrics)

---

## State Management & Ownership

### Per-Component State

**Crawl Layer**:
- URL queue (frontier)
- Rate limit state
- Dedup cache

**Fetch Layer**:
- Browser instances
- Strategy history per domain
- Proxy state

**Extract Layer**:
- Current selectors
- Selector quality predictions
- Field validation rules

**Recovery Layer**:
- Recovery plans (generated per failure)
- Action history
- Backoff state

**Memory Layer** (Source of Truth):
- Selector patterns (learned)
- Domain health metrics
- Strategy effectiveness
- Historical outcomes

### State Consistency Model
- Optimistic (assume success)
- Recover on failure (via recovery layer)
- Durable writes (persist to storage)
- Eventually consistent (across distributed nodes)

---

## Performance Characteristics

### Latency Per Component

- **Crawl Layer**: <1ms (queue operation)
- **Fetch Layer**: 500-5000ms (network/rendering)
- **Extract Layer**: 50-200ms (DOM parsing)
- **Recovery Layer**: 100-5000ms (action dependent)
- **Memory Layer**: <10ms (async writes)
- **ML Decisions**: <5ms (per prediction)
- **Telemetry**: <1ms (async writes)

### Throughput

- **Crawls/second**: Limited by frontier throughput
- **Concurrent fetches**: Browser pool size (typically 10-50)
- **Extractions/second**: Sequential per page
- **Recovery actions/minute**: Limited by backoff

### Resource Usage

- **Memory**: ~100MB base + ~50MB per browser instance
- **CPU**: Low when fetching (wait for network), high when rendering
- **Network**: Depends on site bandwidth
- **Storage**: Metrics and learning data (minimal)

---

## Error Handling Strategy

### Hierarchy of Responses

```
1. Try primary strategy
   ↓ (Failure)
2. Recovery Layer: Generate recovery plan
   ↓ (Execute actions)
3. Try alternative strategy
   ↓ (Failure)
4. Increase backoff, try again
   ↓ (Repeated failures)
5. Escalate to intelligence layer (LLM)
   ↓ (Failure)
6. Mark domain as degraded
   ↓ (Continue with reduced expectations)
7. Manual operator intervention (if needed)
```

### Failure Classification

| Category | Trigger | Response |
|----------|---------|----------|
| Hydration | Timeout on JS | Increase wait |
| Selector Decay | Empty/wrong results | Rediscover |
| Anti-Bot Block | 403/429 status | Rotate proxy, backoff |
| Timeout | Slow response | Increase timeout |
| Network Error | Connection failed | Retry with backoff |
| Invalid Response | Wrong format | Escalate to LLM |

---

## Testing Strategy

### Unit Tests (400+ tests)
- Feature extraction
- ML prediction
- Strategy recommendation
- Recovery planning

### Integration Tests (200+ tests)
- Extraction pipeline end-to-end
- Recovery flow with failure injection
- Learning loop effectiveness
- Multi-component interactions

### Stress Tests (50+ tests)
- Concurrent extraction
- Resource limits
- Domain health degradation
- Recovery under load

### Validation (48+ tests)
- Type safety (mypy)
- Syntax (compilation)
- Regressions (continuous)

---

## Monitoring & Observability

### Key Metrics

**Extraction Quality**:
- Success rate per domain
- Selector quality trend
- Field correctness rate

**Strategy Performance**:
- Success rate per strategy per domain
- Time per strategy
- Strategy switch frequency

**Domain Health**:
- Health score (0-100)
- Trend (improving/degrading)
- Volatility index

**Recovery Effectiveness**:
- Recovery plan success rate
- Action effectiveness by type
- Backoff statistics

### Alerting Thresholds

- Success rate < 60%: WARNING
- Success rate < 30%: CRITICAL
- Selector quality < 0.5: WARNING
- Domain volatility spike: INVESTIGATE
- Recovery failure rate > 30%: REVIEW

---

## Future Enhancements

### Phase 5 (Current)
- [x] System topology visualization ✓
- [x] Dependency graph and data flow diagrams ✓
- [x] Architectural validation tests (40 tests passing) ✓
- [x] Chaos engineering framework (22 scenarios, 5 tests) ✓
- [x] Hard boundary enforcement ✓
- [x] Operational Intelligence (Week 9-12) ✓
  - Degradation predictor (6 failure patterns detected)
  - Operator mode switching (5 modes: production, benchmark, forensic, stealth, low_cost)
  - Frontend dashboard with health/predictions/mode controls
  - 35 tests (22 + 13), mypy clean
  - PLAYBOOKS.md with 6 issue resolution playbooks

### Phase 6 (Production Hardening — Complete)
- [x] Prometheus /metrics endpoint ✓
- [x] Admin API key for powerful routes ✓
- [x] Postgres world-state persistence ✓
- [x] Postgres-backed worker queue (multi-node capable) ✓
- [x] Role-based API keys (read-only, operator, admin) ✓
- [x] secrets.compare_digest for timing-attack resistance ✓
- [x] Rate limiter respects X-Forwarded-For header ✓
- [x] CI pipeline (lint, typecheck, test, arch-validation, Docker build) ✓

### Phase 7
- [ ] Production deployment guide
- [ ] Self-healing automation

---

## Glossary

**Strategy**: Fetch method (Playwright, HTTPX, etc.)  
**Selector**: CSS selector for extracting data  
**Domain**: Website being crawled  
**Volatility**: How often domain structure changes  
**Health**: Overall quality metric for a domain  
**Recovery Plan**: Sequence of actions to recover from failure  
**Learning Loop**: Feedback mechanism for model improvement  
**Async Boundary**: Point where async/await occurs  

---

## Quick Reference: Who Does What

| Component | Responsibility | Input | Output |
|-----------|-----------------|-------|--------|
| Crawl | URL discovery | Job specs | URL stream |
| Fetch | Remote execution | URL + strategy | HTML/DOM |
| Extract | Data parsing | HTML + selectors | Field values |
| Recovery | Failure handling | Failure type | Recovery plan |
| Memory | State storage | All signals | Learned patterns |
| Intelligence | AI reasoning | Complex fields | Structured output |
| Telemetry | Observability | All events | Metrics/alerts |
| Distributed | Node coordination | State changes | Consensus |

---

**End of ARCHITECTURE.md**

This document is the source of truth for DataForge system architecture.  
Keep it current as systems evolve.
