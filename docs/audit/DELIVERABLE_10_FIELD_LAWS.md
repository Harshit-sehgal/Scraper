# Deliverable 10: Field Laws — Formal Constraints & Validation

**Purpose:** Document the physical/topological field constants, exclusivity constraints, and runtime validation rules that govern the semantic field behavior.  

**Source files:**
- `backend/app/field_laws.py` — Foundational constants (zero upward dependencies)
- `backend/app/field_validator.py` — Runtime world-state integrity checks

**Status:** ✅ COMPLETE — Laws documented from source code

---

## 1. Propagation & Stability Constants

Defined in `backend/app/field_laws.py`. These govern how instability, energy, and coupling flow through the semantic field.

| Constant | Value | Description |
|----------|-------|-------------|
| `PROPAGATION_DECAY_FLOOR` | `0.3` | Basins propagate only to direct neighbors; values below this floor decay to zero |
| `MAX_COUPLING_TRANSFER` | `0.3` | Maximum instability flow per interaction between coupled basins |
| `MAX_INSTABILITY_FLUX` | `0.2` | Maximum per-step instability change per basin (dampens oscillation) |
| `MAX_ATTRACTOR_PULL` | `2.0` | Maximum convergence-driven energy reduction per attractor interaction |

### Rationale
- **Decay floor** prevents unbounded propagation across distant regions
- **Coupling transfer** limits how much instability a single interaction can transfer
- **Instability flux** prevents chaotic oscillations in a single time step
- **Attractor pull** caps energy reduction to prevent runaway convergence

---

## 2. Thermodynamic Constants

These scale the free-energy-gradient-driven redistribution of instability across the field.

| Constant | Value | Description |
|----------|-------|-------------|
| `COUPLING_COEFFICIENT` | `0.05` | Scales `flow = conductance * free_energy_gradient * COUPLING_COEFFICIENT`. Higher = faster equilibration; lower = more conservative |
| `FREE_ENERGY_CLAMP` | `2.0` | Maximum free energy gradient per redistribution step. Prevents chaotic oscillations from extreme gradient differentials |

### Usage
The coupling coefficient is applied in redistribution calculations (see `semantic_allocation_engine.py`):
```
instability_flow = conductance * gradient * COUPLING_COEFFICIENT
```
The free energy clamp is applied as a saturating ceiling:
```
clamped_gradient = min(abs(gradient), FREE_ENERGY_CLAMP) * sign(gradient)
```

---

## 3. Exclusivity Constraints

These define which schema fields and semantic needs **must not** align to the same slot during allocation.

### Role Exclusivity (bootstrap seeds)
```python
ROLE_EXCLUSIVITY = [
    ("origin", "destination"),
    ("departure", "arrival"),
    ("start", "end"),
    ("price", "cost"),
]
```

These pairs are **always** exclusive — they cannot share the same allocation slot. They are hardcoded as bootstrap seeds and never unlearned.

### Semantic Need Exclusivity
```python
SEMANTIC_NEED_EXCLUSIVITY = [
    ("status", "date"),
    ("seller", "location"),
]
```

These represent semantic needs that conflict in typical extraction contexts:
- `status` and `date` shouldn't align to the same field (a status value and a date value are semantically distinct)
- `seller` and `location` shouldn't align to the same field (a person/entity vs a place)

### Dynamic Exclusion Learning
Beyond the hardcoded seeds, exclusions are learned dynamically at runtime:
```python
# From semantic_allocation_engine.py
ws.learned_exclusions: dict[tuple[str, str], float]  # (need_a, need_b) → exclusion_strength
```

Each learned exclusion has a strength `0.0–1.0` indicating how strongly the two needs should be kept apart.

---

## 4. Runtime Validation (`validate_world_state`)

The function `validate_world_state(ws: SemanticWorldState) -> list` performs integrity checks on the semantic field and returns a list of issue strings (empty list = clean).

### Validation Rules

| # | Check | Condition | Action |
|---|-------|-----------|--------|
| 1 | Global energy NaN/Inf | `math.isnan` or `math.isinf` on `ws.metrics.global_energy` / `global_entropy` | Report |
| 2 | Orphan regions | A region with `competing_roles == []` | Report "Orphan region" |
| 3 | Region instability bounds | `0.0 <= instability <= 1.0` | Report out-of-bounds |
| 4 | Region local energy bounds | `0.0 <= local_energy <= 10.0` | Report out-of-bounds |
| 5 | Learned exclusion bounds | `0.0 <= strength <= 1.0` | Report out-of-bounds |
| 6 | Global metric bounds | Energy: `[0, 10]`, Entropy: `[0, 1]` | Report out-of-bounds |
| 7 | Memory caps | `decision_history > 5000`, `field_regions > 500`, `learned_exclusions > 500` | Report possible bloat |
| 8 | Region integrity bounds | `0.0 <= integrity <= 1.0` | Report out-of-bounds |

### Call Sites
`validate_world_state` is called from:
- `semantic_allocation_engine.py` — After each allocation step
- `topology_api.py` — On-demand via system endpoints

### Threshold Rationale
| Threshold | Rationale |
|-----------|-----------|
| Energy `[0, 10]` | Basins with energy > 10 are considered over-saturated and should redistribute |
| Entropy `[0, 1]` | Normalized to 1.0 max; values above indicate instability overflow |
| `decision_history > 5000` | Imposes a practical memory cap to prevent unbounded growth |
| `field_regions > 500` | Hard limit on region count; above this indicates allocation bloat |
| `integrity [0, 1]` | Normalized health score for each region |

---

## 5. Invariant Firewall

The `invariant_firewall.py` module enforces invariants at the field level:

- **Energy conservation**: Sum of energy changes across all regions should approximate zero (within floating-point tolerance)
- **Instability conservation**: Total instability should not increase above the injected amount
- **Exclusion symmetry**: If A excludes B, B should exclude A (symmetric constraint)

These invariants are checked during allocation and redistribution operations.

---

## 6. Field Validation Test Coverage

Tests for field laws and validation exist in:

| Test File | Coverage |
|-----------|----------|
| `tests/test_field_validator.py` | Runtime validation checks (15 tests) |
| `tests/test_semantic_invariants.py` | Invariant enforcement (23 tests) |
| `tests/test_field_adversarial_stress.py` | Edge case stress tests (3 tests) |
| `tests/test_edge_field_model.py` | Field model edge cases (2 tests) |

**Total: ~43 tests covering field validation and invariants**

---

## Summary

The field laws layer provides:

- ✅ **Foundational constants** — Zero upward dependencies, independently auditable
- ✅ **Exclusivity constraints** — Bootstrap seeds prevent common allocation conflicts
- ✅ **Dynamic exclusion learning** — Runtime adaptation beyond hardcoded rules
- ✅ **Runtime validation** — `validate_world_state` catches structural drift before propagation
- ✅ **Invariant enforcement** — Energy/instability conservation checks via firewall
- ✅ **Tested** — 43+ tests covering validation, invariants, and edge cases

**Status:** Documented from source code. Laws are stable and actively enforced at runtime.

---

**Classification:** FIELD LAWS DOCUMENTED — Foundational constants, exclusivity constraints, and validation rules verified against source
