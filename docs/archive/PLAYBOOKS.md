# DataForge Operations Playbooks
## Common Issue Resolution Guides

**Version:** 1.0
**Last Updated:** 2026-05-21
**Audience:** Operators, SREs, on-call engineers

---

## Table of Contents

1. [System Health Checks](#system-health-checks)
2. [Degradation & Prediction Playbooks](#degradation--prediction-playbooks)
3. [Recovery Playbooks](#recovery-playbooks)
4. [Anti-Bot Escalation Playbooks](#anti-bot-escalation-playbooks)
5. [Resource Governance Playbooks](#resource-governance-playbooks)
6. [Cognition & Semantic State Playbooks](#cognition--semantic-state-playbooks)
7. [Browser & Fetch Playbooks](#browser--fetch-playbooks)
8. [Emergency Procedures](#emergency-procedures)
9. [Operator Mode Reference](#operator-mode-reference)
10. [Monitoring & Alerting](#monitoring--alerting)

---

## How to Use These Playbooks

Each playbook follows the same structure:

1. **Symptoms** — What you'll observe
2. **Check** — Quick diagnostics to confirm the issue
3. **Immediate Actions** — What to do right now (minutes)
4. **Follow-up** — What to do after stabilization (hours)
5. **Prevention** — How to prevent recurrence (days)

Start with **System Health Checks** for any new issue.

---

## System Health Checks

### Quick Health Check (30 seconds)

```bash
# 1. Check API status
curl -s http://localhost:8000/api/operator/health | python3 -m json.tool

# Expected: status="healthy", success_rate >= 0.6
# If degraded, continue to Step 2

# 2. Check system status
curl -s http://localhost:8000/api/system/status | python3 -m json.tool

# Expected: status="online", active jobs not stuck

# 3. Check dashboard
curl -s http://localhost:8000/api/operator/dashboard | python3 -m json.tool

# 4. Check predictions
curl -s http://localhost:8000/api/operator/predictions | python3 -m json.tool

# 5. Check logs
tail -100 backend/logs/scraper.log | grep -i "error\|critical\|exception"
```

### Full Health Assessment (5 minutes)

```bash
# 1. Run the benchmark smoke test
cd backend && python3 -m pytest tests/benchmark_smoke_test.py -v --tb=short

# 2. Run architecture validation
cd backend && python3 architecture_validator.py validate --all

# 3. Run chaos survival test
cd backend && python3 -m pytest tests/test_chaos_engineering.py -v --tb=short
```

---

## Degradation & Prediction Playbooks

### P1: Degradation Predictor Flags a "Critical" Risk

**Symptoms:**
- `/api/operator/predictions` shows `risk_level: "critical"` for one or more domains
- Dashboard shows degrading/unhealthy domains
- Extraction success rate falling for affected domains

**Check:**
```bash
# Get detailed predictions
curl -s "http://localhost:8000/api/operator/predictions?min_confidence=0.7" \
  | python3 -m json.tool | head -80

# Check domain health
curl -s http://localhost:8000/api/operator/dashboard \
  | python3 -m json.tool | grep -A 2 "domains"
```

**Immediate Actions:**
1. **Switch to forensic mode** for the affected domain:
   ```bash
   curl -X POST http://localhost:8000/api/operator/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "forensic"}'
   ```

2. **Run a diagnostic scrape** on the domain:
   ```bash
   curl -X POST http://localhost:8000/api/url/analyze \
     -H "Content-Type: application/json" \
     -d '{"url": "https://critical-domain.com/page"}'
   ```

3. **Check recovery logs** for the domain:
   ```bash
   tail -200 backend/logs/scraper.log | grep "critical-domain"
   ```

**Follow-up:**
- Review if the domain structure has changed
- Check if anti-bot measures have escalated
- Update selectors if needed
- Consider pausing extraction from the domain

**Prevention:**
- Enable proactive selector rediscovery for volatile domains
- Set up alerts when domain health drops below 40
- Review DegradationPredictor confidence thresholds

---

### P2: Multiple Domains Showing "Declining" Health Trend

**Symptoms:**
- Several domains show `health_score_trend: "declining"`
- Overall success rate dropping
- Recovery attempts becoming more frequent

**Check:**
```bash
# Check overall trend
curl -s http://localhost:8000/api/operator/predictions \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Systemic risk: {d[\"systemic_risk_level\"]}')
print(f'Critical: {d[\"summary\"][\"critical\"]}, High: {d[\"summary\"][\"high\"]}')
"

# Check if it's a systemic issue (proxy pool, browser pool, etc.)
curl -s http://localhost:8000/api/operator/dashboard \
  | python3 -m json.tool
```

**Immediate Actions:**
1. **Check if the browser pool is healthy**:
   ```bash
   # Browser metrics are in the dashboard
   curl -s http://localhost:8000/api/operator/dashboard \
     | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('browser', {}))"
   ```

2. **Rotate proxy pool** if IP reputation is dropping:
   ```bash
   # Check proxy health first
   # Consider adding fresh proxies
   ```

3. **Switch to low-cost mode** if resource usage is high:
   ```bash
   curl -X POST http://localhost:8000/api/operator/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "low_cost"}'
   ```

**Follow-up:**
- Monitor for 30 minutes after actions
- If trend continues, investigate upstream dependencies
- Review if a site-wide change is affecting multiple domains

---

### P3: "Selector Decay" Predictions Active

**Symptoms:**
- `predicted_failure_type: "selector_decay"` in predictions
- Empty or partial extraction results for specific domains
- Increasing recovery attempts with `SELECTOR_DECAY` classification

**Check:**
```bash
# Get selector-specific predictions
curl -s "http://localhost:8000/api/operator/predictions" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d.get('predictions', []):
    if p.get('predicted_failure_type') == 'selector_decay':
        print(f\"{p['domain']}: {p['risk_level']} ({p.get('health_score_current', '?')}/100)\")
"
```

**Immediate Actions:**
1. **Force selector rediscovery** for the affected domain:
   - This happens automatically in forensic mode
   - Or trigger a fresh URL analyze to discover new selectors

2. **Run a diagnostic URL analyze**:
   ```bash
   curl -X POST http://localhost:8000/api/url/analyze \
     -H "Content-Type: application/json" \
     -d '{"url": "https://affected-domain.com/page"}'
   ```

**Follow-up:**
- Update schema with new selectors from analysis
- Check if website redesign is the root cause
- Review selector decay acceleration pattern

---

## Recovery Playbooks

### P4: Recovery Attempts Failing Repeatedly

**Symptoms:**
- Recovery actions running but not succeeding
- Same URLs going through multiple recovery cycles
- `failure_rate` over 80% for a domain

**Check:**
```bash
# Check recent telemetry for the domain
curl -s http://localhost:8000/api/scraper/telemetry/recent?n=50 \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for t in d:
    if t.get('url', '').find('problem-domain') >= 0:
        print(t.get('failure_category'), t.get('fallback_triggered'))
"
```

**Immediate Actions:**
1. **Pause extraction** from the problem domain:
   - Stop any running jobs targeting this domain
   - Let recovery cycles complete naturally

2. **Switch to forensic mode** to debug:
   ```bash
   curl -X POST http://localhost:8000/api/operator/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "forensic"}'
   ```

3. **Check if anti-bot escalation is the root cause**:
   ```bash
   tail -100 backend/logs/scraper.log | grep -i "anti.bot\|block\|429\|403"
   ```

**Follow-up:**
- After stabilization, switch back to production mode
- Review recovery strategy success rates
- Consider updating recovery thresholds for extreme cases

---

### P5: Browser Pool Exhaustion

**Symptoms:**
- Dashboard shows `active_contexts` near `total_contexts`
- New extraction requests hanging or timing out
- Browser-related errors in logs

**Check:**
```bash
# Browser metrics
curl -s http://localhost:8000/api/operator/dashboard \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('browser', {}))"

# Check for stuck browsers
tail -50 backend/logs/scraper.log | grep -i "browser_pool\|timeout\|stuck"
```

**Immediate Actions:**
1. **Reduce concurrency** by switching to low_cost mode:
   ```bash
   curl -X POST http://localhost:8000/api/operator/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "low_cost"}'
   ```

2. **Force browser cleanup**:
   ```bash
   # Kill any orphaned browser processes
   pkill -f "playwright" || true
   pkill -f "chromium" || true
   ```

3. **Restart the scraper service** if browsers are unrecoverable:
   ```bash
   docker-compose restart scraper
   ```

**Follow-up:**
- Review browser pool size configuration
- Check if memory limits are sufficient
- Consider adding more browser pool capacity

---

## Anti-Bot Escalation Playbooks

### P6: Anti-Bot Score Spiking Across Multiple Domains

**Symptoms:**
- Sudden increase in anti_bot_score across domains
- Multiple 403/429 responses
- Proxy pool draining quickly

**Check:**
```bash
# Check anti-bot scores in recent scrapes
tail -100 backend/logs/scraper.log | grep -oP '"anti_bot_score":\d+\.\d+' | sort -t: -k2 -n | tail -10
```

**Immediate Actions:**
1. **Rotate proxy pool globally**:
   ```bash
   curl -X POST http://localhost:8000/api/operator/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "stealth"}'
   ```

2. **Increase request intervals** (done automatically in stealth mode)

3. **Check if IP range is blacklisted** by major sites

**Follow-up:**
- Review proxy provider health
- Consider adding residential proxies
- Rotate User-Agent strings more aggressively

---

## Resource Governance Playbooks

### P7: Token Spend Exceeding Budget

**Symptoms:**
- `token_spend_dollars` growing faster than expected
- AI structuring calls may be failing due to rate limits
- Economic tracking shows poor efficiency

**Check:**
```bash
# Check current spend
curl -s http://localhost:8000/api/operator/dashboard \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'Token spend: \${d[\"governor\"][\"token_spend_dollars\"]:.3f}')"

# Check LLM usage
tail -100 backend/logs/scraper.log | grep -i "llm\|token\|cost"
```

**Immediate Actions:**
1. **Switch to low_cost mode** to reduce AI usage:
   ```bash
   curl -X POST http://localhost:8000/api/operator/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "low_cost"}'
   ```

2. **Reduce AI structuring** for non-critical fields

3. **Increase minimum quality threshold** to skip low-value extractions

**Follow-up:**
- Review per-domain token consumption
- Consider caching AI responses for repeated patterns
- Adjust budget allocation per domain priority

---

### P8: Queue Shedding / Resource Pressure

**Symptoms:**
- Dashboard shows `queue_sheds` or `browser_prunes` increasing
- Jobs taking longer than expected
- Resource governor actively throttling

**Check:**
```bash
# Check governor metrics
curl -s http://localhost:8000/api/operator/dashboard \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('governor', {}))"
```

**Immediate Actions:**
1. **Reduce load** by switching to production or low_cost mode:
   ```bash
   curl -X POST http://localhost:8000/api/operator/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "low_cost"}'
   ```

2. **Cancel non-critical jobs** from the dashboard

3. **Check memory usage** on the host:
   ```bash
   free -h
   top -b -n 1 | head -20
   ```

**Follow-up:**
- Review resource governor thresholds
- Consider scaling horizontally if sustained load is expected
- Add monitoring alerts for resource pressure

---

## Cognition & Semantic State Playbooks

### P9: Semantic State Integrity Dropping

**Symptoms:**
- `integrity_score` in Cognition view dropping
- Increased conflict basins (high entropy zones)
- Exclusion learning slowing or becoming erratic

**Check:**
```bash
# Check full cognition state
curl -s http://localhost:8000/api/system/topology \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
m = d.get('metrics', {})
print(f'Integrity: {m.get(\"integrity_score\", 0):.3f}')
print(f'Pressure: {m.get(\"field_pressure\", 0):.3f}')
print(f'Energy: {m.get(\"global_energy\", 0):.3f}')
print(f'Exclusions: {m.get(\"exclusion_count\", 0)}')
print(f'Basins: {m.get(\"region_count\", 0)}')
"
```

**Immediate Actions:**
1. **Let the system stabilize** — transient entropy is normal:
   - The semantic world state has self-healing through crystalline record formation

2. **Check for conflicting schemas** that might be causing instability

3. **Trigger manifold compression** if integrity is persistently low:
   ```bash
   curl -X POST http://localhost:8000/api/system/refactor/compress
   ```

**Follow-up:**
- Review recent extraction patterns that introduced conflicting data
- Consider resetting the semantic state if recovery is impossible
- Monitor for recurrence of the same conflict patterns

---

### P10: Crystalline Records Stagnating

**Symptoms:**
- Crystalline record count not growing
- Knowledge export showing limited synthesis
- Learning loops running but not producing new insights

**Check:**
```bash
# Check crystalline records
curl -s http://localhost:8000/api/system/crystalline \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'Records: {d.get(\"count\", 0)}')"

# Check learning count
curl -s http://localhost:8000/api/system/topology \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'Learning: {d[\"metrics\"].get(\"learning_count\", 0)}')"
```

**Immediate Actions:**
1. **Force a cognitive processing step**:
   ```bash
   curl -X POST "http://localhost:8000/api/system/scheduler/step?budget_ms=500"
   ```

2. **Feed diverse data** — crystalline records require varied, high-quality inputs

3. **Check if the system is saturated** with existing knowledge

**Follow-up:**
- Review domain diversity in recent extractions
- Consider adding new domains to stimulate learning
- Check that telemetry signals are reaching the world state

---

## Browser & Fetch Playbooks

### P11: Browser Crashes During Extraction

**Symptoms:**
- Logs show `BROWSER_CRASH` entries
- Recovery system activating
- Extraction throughput dropping

**Check:**
```bash
# Check recent crash events
tail -100 backend/logs/scraper.log | grep -i "browser.*crash\|BROWSER_CRASH"

# Check current browser pool metrics
curl -s http://localhost:8000/api/operator/dashboard \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('browser', {}))"
```

**Immediate Actions:**
1. **Let recovery handle it** — the system automatically recycles crashed browser instances
2. **If crashes are frequent**, reduce concurrency:
   ```bash
   curl -X POST http://localhost:8000/api/operator/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "low_cost"}'
   ```
3. **Check memory pressure** on the host

**Follow-up:**
- Review memory limits per browser instance
- Check if specific sites are triggering crashes
- Consider updating Playwright/browser versions

---

## Emergency Procedures

### E1: Complete System Unresponsive

**Symptoms:**
- API returning 5xx errors
- Health check failing
- All metrics showing zero/error

**Immediate Actions:**

```bash
# 1. Check if the process is running
ps aux | grep -i scraper | grep -v grep

# 2. Check Docker status if containerized
docker ps | grep scraper
docker logs --tail 100 scraper

# 3. Restart the service
docker-compose restart scraper

# 4. Verify recovery
sleep 5 && curl -s http://localhost:8000/api/system/status | python3 -m json.tool
```

**If the process won't start:**
```bash
# Check for corrupted state file
cat backend/state/dataforge_state.json | python3 -m json.tool 2>&1 | head -20

# If corrupted, restore from backup
cp backend/state/dataforge_state.json.bak backend/state/dataforge_state.json

# Start in recovery mode
cd backend && python3 -c "
from app.state_store import load_state, get_state_file_path
import json
try:
    jobs, recycle, world = load_state()
    print(f'State loaded: {len(jobs)} jobs, {len(recycle)} recycled, world={world is not None}')
except Exception as e:
    print(f'State corrupt: {e}')
"
```

---

### E2: Data Corruption / Wrong Extraction Results

**Symptoms:**
- Extracted records contain incorrect data
- Field values mismatched or swapped
- Results not matching expected schema

**Immediate Actions:**
1. **Stop any running extractions** targeting the affected job
2. **Export known-good data** from previous successful runs
3. **Review the extraction schema** for recent changes
4. **Run a manual URL analyze** on the source page to verify fields:
   ```bash
   curl -X POST http://localhost:8000/api/url/analyze \
     -H "Content-Type: application/json" \
     -d '{"url": "https://source-domain.com/page"}'
   ```

**Follow-up:**
- Review schema field mappings
- Check if the source site changed its HTML structure
- Use AI re-clean on affected data (from the dashboard)

---

## Operator Mode Reference

| Mode | Use When | Characteristics | Impact |
|------|----------|----------------|---------|
| **production** | Normal operation | High-yield throughput, stable settings | Standard performance |
| **benchmark** | Running benchmarks | Hostile validation, full telemetry | Slower but thorough |
| **forensic** | Debugging failures | Deep diagnostics, verbose logging | Fastest, lightest |
| **stealth** | Anti-bot evasion | Max camouflage, slow and careful | Slowest, highest safety |
| **low_cost** | Budget/resource constrained | Resource conservation, minimal AI | Lowest cost |

**Quick switch commands:**
```bash
# Switch mode
curl -X POST http://localhost:8000/api/operator/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "production"}'

# Check current mode
curl -s http://localhost:8000/api/operator/mode | python3 -m json.tool
```

---

## Monitoring & Alerting

### Key Metrics to Watch

| Metric | Warning | Critical | Check Interval |
|--------|---------|----------|----------------|
| Success Rate | < 60% | < 30% | 1 min |
| Domain Health Score | < 50 | < 25 | 5 min |
| Browser Active Contexts | > 80% pool | > 95% pool | 1 min |
| Degradation Predictions | Any "high" | Any "critical" | 5 min |
| Token Spend | > $0.50/hr | > $2.00/hr | 10 min |
| Recovery Failure Rate | > 30% | > 60% | 5 min |
| Integrity Score | < 0.7 | < 0.4 | 5 min |

### Recommended Alert Channels

- **P1 (Critical):** PagerDuty / Slack @on-call
- **P2 (High):** Slack channel notification
- **P3 (Medium):** Email digest
- **Info:** Dashboard only

### Health Check Endpoint (for external monitoring)

```bash
# Simple health check that returns 200 if healthy
curl -s http://localhost:8000/api/operator/health

# Expected response:
# {
#   "status": "healthy",
#   "mode": "production",
#   "success_rate": 0.85,
#   "active_browsers": 3,
#   "domains_degraded": 0,
#   "domains_monitored": 5,
#   "recent_scrapes": 20
# }
```

### Dashboard API Endpoints

| Endpoint | Description | Frequency |
|----------|-------------|-----------|
| `GET /api/operator/health` | Lightweight health overview | Every 30s |
| `GET /api/operator/dashboard` | Full system dashboard | Every 60s |
| `GET /api/operator/predictions` | Degradation predictions | Every 5 min |
| `GET /api/operator/mode` | Current operator mode | On demand |

---

## Playbook Testing Checklist

After any infrastructure change, verify playbooks still work:

- [ ] `GET /api/operator/health` returns valid response
- [ ] `GET /api/operator/mode` shows current mode
- [ ] `POST /api/operator/mode` switches modes correctly
- [ ] `GET /api/operator/dashboard` returns all sections
- [ ] `GET /api/operator/predictions` returns predictions
- [ ] Browser pool recovers after crash
- [ ] Recovery system activates on extraction failure
- [ ] Resource governor throttles under load
- [ ] Semantic state self-heals after corruption
- [ ] Operator can understand system status at a glance

---

**End of Playbooks**

*These playbooks are living documents. Update them as you discover new failure patterns and recovery techniques.*
