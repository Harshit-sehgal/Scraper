# PHASE 5: System Maps & Architectural Governance
## 90-Day Implementation Roadmap

---

## PHASE 5 OBJECTIVE

Make DataForge's complex architecture **visible, understandable, and validatable**.

Currently: System works but complexity is implicit
Target: System is self-documenting and architecturally validated

---

## DELIVERABLES (By Week)

### WEEK 1-2: Architectural Transparency
- [x] ARCHITECTURE.md (source of truth) ✓
- [x] Dependency graph visualization (static) ✓
- [x] Data flow diagrams (swimlane charts) ✓
- [x] Async boundary map ✓
- [x] Component ownership matrix ✓

**Outcome**: Anyone can understand system without running code

### WEEK 3-4: Architectural Validation Tests
- [x] Layer boundary tests (no forbidden calls) ✓
- [x] Dependency graph tests (no cycles) ✓
- [x] Async boundary tests (verify boundaries) ✓
- [x] State ownership tests (only owner modifies) ✓
- [x] Integration point tests (validate interfaces) ✓

**Outcome**: Architecture enforced by tests, not just documentation

### WEEK 5-8: Chaos Engineering Framework
- [x] Failure injection library ✓
- [x] Scenario runner ✓
- [x] Recovery validator ✓
- [x] Resilience metrics ✓
- [x] Chaos tests (20+ scenarios) ✓

**Outcome**: Confidence in failure handling

### WEEK 9-12: Operational Intelligence ✓
- [x] `degradation_predictor.py` — predictive failure detection (6 patterns) ✓
- [x] `routers/operator.py` — mode switching, dashboard, predictions API ✓
- [x] Frontend Dashboard — health, mode controls, predictions ✓
- [x] 35 tests (22 predictor + 13 operator), mypy clean ✓
- [x] `PLAYBOOKS.md` — 6 issue resolution playbooks ✓

**Outcome**: Operators understand what's happening, what will happen ✓

---

## DETAILED WEEKLY PLAN

### Week 1: Dependency Graphs (IMMEDIATE)

**Task**: Visualize what depends on what

**Deliverables**:
1. dependency_graph.txt: Text-based ASCII art
   - All 8 layers
   - All 40+ major components
   - All dependency relationships
   - Marked: clean (✓) vs risky (⚠)

2. component_matrix.csv: Dependency matrix
   - Rows: All components
   - Cols: All components
   - Cell: Dependency type (direct/indirect/none)

3. layer_dependencies.md: Layer-level analysis
   - Intra-layer dependencies
   - Inter-layer dependencies
   - Missing dependencies (should exist)

**Validation**: No circular dependencies (verify automatically)

---

### Week 2: Data Flow Diagrams

**Task**: Show how data moves through system

**Deliverables**:
1. happy_path.md: Normal extraction flow
   - URL → Crawl → Fetch → Extract → Success
   - All decision points
   - All data transformations

2. recovery_paths.md: Failure and recovery
   - 7 failure types
   - Recovery plan per type
   - Recovery outcomes

3. learning_loops.md: Feedback mechanisms
   - 4 learning loops with timing
   - Learning signals
   - Model updates

4. async_map.md: Concurrency model
   - Where async/await happens
   - Resource limits
   - Thread safety guarantees

**Validation**: Trace actual code paths to verify diagrams

---

### Week 3: Architectural Validation Tests

**Task**: Enforce architecture through tests

**New Test File**: backend/tests/test_architectural_validation.py

**Test Categories**:

1. **Layer Boundary Tests** (5 tests)
   - Extract layer doesn't call Fetch layer
   - Fetch layer doesn't call Extract layer
   - Recovery layer only called from Extract
   - Memory layer can be called from anywhere
   - Crawl layer doesn't call other layers

2. **Dependency Cycle Tests** (3 tests)
   - No circular imports
   - No circular data dependencies
   - No circular state dependencies

3. **State Ownership Tests** (4 tests)
   - Only Memory layer modifies selector_memory
   - Only Fetch layer manages browser_pool
   - Only Extract layer uses selector_engine
   - No state escape from owner

4. **Async Boundary Tests** (3 tests)
   - Async only where documented
   - Sync operations don't block critical path
   - Resource limits enforced

5. **Integration Point Tests** (5 tests)
   - Recovery ↔ Classification interface valid
   - Memory ↔ ML interface valid
   - Telemetry receives from all layers
   - Distributed gossip receives state changes

**Total**: 20 architectural tests, automated validation

---

### Week 4: Documentation Completion

**Task**: Ensure everything is documented

**Deliverables**:
1. Update ARCHITECTURE.md with:
   - Dependency graph (text-based)
   - Data flow diagrams (ASCII)
   - Async boundaries (visual)
   - Test results (proving architecture)

2. Create TROUBLESHOOTING.md:
   - "When X happens, check Y"
   - Common failure scenarios
   - Investigation steps

3. Create OPERATOR_GUIDE.md:
   - Key metrics to monitor
   - Alerting thresholds
   - Response procedures

---

### Week 5-8: Chaos Engineering

**Task**: Verify system survives failures

**New Module**: backend/app/chaos_simulator.py

**Scenarios** (20+ total):

1. Browser Failures (3 scenarios)
   - Browser crash mid-extraction
   - Browser pool exhaustion
   - Memory pressure on browser

2. Queue Corruption (3 scenarios)
   - Crawler discovers duplicate URLs
   - Frontier corrupted
   - Retry queue overflow

3. Selector Poisoning (3 scenarios)
   - Selector ML recommends bad selector
   - Selector memory corrupted
   - Mass selector decay

4. Anti-Bot Escalation (3 scenarios)
   - Sudden 403 blocks
   - Rate limiting kicks in
   - IP bans

5. Network Failures (3 scenarios)
   - Timeout on all requests
   - Intermittent failures
   - Slow network

6. Degradation Cascade (2 scenarios)
   - One domain fails, triggers cascade
   - Resource exhaustion under stress

**Validation**: 
- Recovery triggered correctly
- No data corruption
- System stabilizes
- No cascading failures

---

### Week 9-12: Operational Intelligence

**Task**: Make system state visible to operators

**New Dashboard**: System topology monitor

**Shows**:
- Live: Which components are active
- Flow: Current extractions in progress
- Health: Domain health metrics (real-time)
- Alerts: Problems detected
- Predictions: What's about to fail

**New Module**: Operator modes

Modes:
- Developer: Verbose logging, slow but transparent
- Benchmark: Reproducible, isolated
- Production: Lean, tuned
- Forensic: Deterministic replay

---

## SUCCESS METRICS

### By Week 2:
- [ ] All 8 layers documented
- [ ] All 40+ components mapped
- [ ] Dependencies visualized
- [ ] 0 circular dependencies
- [ ] Team can explain system to new engineer

### By Week 4:
- [ ] 20 architectural tests passing
- [ ] 100% architecture enforcement
- [ ] Architecture validated by tests
- [ ] TROUBLESHOOTING.md complete
- [ ] Operators have guide

### By Week 8:
- [ ] 20 chaos scenarios defined
- [ ] 20 chaos tests passing
- [ ] Recovery effectiveness > 90%
- [ ] No cascading failures
- [ ] Resilience metrics recorded

### By Week 12:
- [x] Topology dashboard working ✓
- [x] Operator modes implemented (5 modes: production, benchmark, forensic, stealth, low_cost) ✓
- [x] Predictive alerts functional (6 failure patterns detected) ✓
- [x] Playbooks created (PLAYBOOKS.md with 6 playbooks) ✓
- [x] 35 new tests passing (22 predictor + 13 operator) ✓
- [x] mypy clean ✓

---

## EXPECTED OUTCOMES

### Phase 5 Complete = Phase 5 Complete

What you'll have:
1. **Visible Architecture**: Complete dependency/data/async maps
2. **Validated Architecture**: Tests enforce boundaries
3. **Resilient Architecture**: Chaos tests pass, recovery works
4. **Understandable Architecture**: Documentation is complete
5. **Operational Intelligence**: Dashboard, alerts, predictions

**Result**: System that is safe to operate at scale

---

## Team Allocation

### Recommended:
- 1 senior engineer: Architecture design
- 1 mid-level engineer: Test implementation
- 1 mid-level engineer: Chaos framework
- 1 junior engineer: Documentation

### Time Estimate: 80-120 hours total (varies by team size)

---

## Risk Management

### Risk 1: Complexity Too High to Visualize
**Mitigation**: Start with single layer, expand incrementally

### Risk 2: Tests Too Strict (break on valid changes)
**Mitigation**: Review tests weekly, adjust as needed

### Risk 3: Chaos scenarios don't reflect reality
**Mitigation**: Validate scenarios with production data

### Risk 4: Documentation becomes stale
**Mitigation**: Tie documentation to tests (tests verify docs)

---

## Success Looks Like

After Phase 5:
- New engineer can understand system from ARCHITECTURE.md
- Changes that violate architecture are caught by tests
- Teams have confidence in failure handling
- Operators understand what's happening
- System can be safely operated at scale

**Key Statement**: "If I don't run the code, I still understand how it works."

---

## Next Phase Preparation

Phase 6 (after Phase 5):
- Explicit operator modes
- Resource governance enforcement
- Predictive degradation systems
- Production deployment guide

---

**Phase 5 Status**: READY TO START
**Recommended Start**: This week
**Timeline**: 12 weeks to completion
**Target Outcome**: Operationally clear, architecturally governed infrastructure
