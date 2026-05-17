# Semantic Field Architecture — Constitutional Laws

## Preamble
This system is a **topology-driven semantic dynamical system**, not a traditional NLP pipeline.
Meaning emerges from the interaction of field regions, energy gradients, and topological relaxation.
Any mechanism that reintroduces symbolic repair, hard-coded overrides, or centralized orchestration is a violation of the system's core laws and constitutes an architectural regression.

---

## LAW 1 — MEANING EMERGES FROM TOPOLOGY
Semantics are defined by the geometry of the field (Role Manifold, Cohesion, Tension).
No symbolic score lookups or hard-coded type-mapping dictionaries are permitted.
Role compatibility must be a geometric distance in embedding space.

## LAW 2 — NO SEMANTIC OVERRIDES
Subsystems may perturb, bias, or stabilize the field, but they may NEVER rewrite semantic truth directly.
The allocator (Proposal Generator) provides the only explicit assignment.
Topology guides the allocator via Bias and Damping.
**Forbidden:** `output[field] = corrected_value` after topology evaluation.

## LAW 3 — ENERGY IS CAUSAL
Energy is the DRIVER of motion, not just a descriptive metric.
Energy gradients produce relaxation; relaxation produces equilibrium.
**Forbidden:** `energy = equilibrium * constant`.
**Allowed:** `instability_change = -energy_gradient`.

## LAW 4 — ENFORCE LOCALITY
All field interactions must be local to topological neighbors.
Global O(N²) loops are prohibited.
Basins evolve autonomously and propagate tension only to their immediate exclusivity neighbors.
**Forbidden:** `redistribute_instability()` (global loop).
**Allowed:** `propagate_on_reinforce()` (neighbor-local).

## LAW 5 — NO FIXED EVOLUTION CADENCE
Basins and manifolds evolve based on field demand (tension, pressure, depth), not procedural loops.
**Forbidden:** `if counter % 3 != 0: return`.
**Allowed:** `evolution_rate = f(state)`.

## LAW 6 — OBSERVATION MUST NOT MUTATE STATE
Metric derivation and diagnostic snapshots must be read-only.
The observer does not participate in the dynamics.
State transitions must occur only within evolution stages.

## LAW 7 — GRACEFUL DEGRADATION
The system must never exhibit binary filtering behavior for semantic structure.
Weak evidence must enter the field as high-entropy, low-energy basins rather than being discarded.
Meaning settles through natural decay or reinforcement.

---

## ONTOLOGY MATRIX (Authority Model)

| Quantity | Stored? | Derived? | Authority |
| --- | --- | --- | --- |
| **Maturity** | No | Yes | Experience manifold (metrics) |
| **Pressure** | No | Yes | Field aggregate (energy + entropy) |
| **Energy** | Yes | Semi | Basin dynamics (potential well) |
| **Convergence**| Yes | Semi | Local attractor (stability debt) |
| **Entropy** | No | Yes | Instability distribution (disorder) |
| **Topology** | Stored | No | Physical structure (manifold + edges) |
