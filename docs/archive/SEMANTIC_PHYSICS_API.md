# Semantic Physics API — Guide to Dynamical Cognition

## Core Philosophy
This API does not return "classifications" or "matches". It returns the **Physical State** of a self-organizing semantic field. Meaning in this system is an emergent property of topological relaxation, energy minimization, and manifold alignment.

---

## Canonical Causal Variables

| Variable | Physical Meaning | Cognitive Meaning |
| --- | --- | --- |
| **Energy** | Motion Potential | Field Stress / Structural Activation |
| **Entropy** | Topological Disorder | Interpretation Uncertainty / Noise |
| **Integrity** | Potential Well Depth | Knowledge Stability / Persistence |
| **Pressure** | Gradient Force | Combined Stress + Disorder (Drives Evolution) |

---

## Key Endpoints

### 1. System Topology (`GET /api/system/topology`)
Returns the global physical state of the semantic manifold.
*   **metrics**: Global thermodynamic variables (Energy, Entropy, Integrity).
*   **global_communities**: High-level semantic components (groups of roles that co-exist).
*   **schema_patterns**: Recurring structural arrangements of roles.
*   **field_regions**: Active "basins" of semantic tension (where interpretation is currently settling).

### 2. Causal Explanation (`POST /api/explain`)
Provides a topological trace for a specific data assignment.
*   **manifold_compatibility**: Geometric distance between role and value.
*   **community_pull**: Stabilization force from macro-scale neighbors.
*   **schema_gravity**: Reinforcement from learned structural patterns.

---

## Field Laws

### LAW 1 — MEANING IS GEOMETRY
Semantics are defined by positions in a 16-dimensional Role Manifold. Distance is inversely proportional to compatibility.

### LAW 2 — ENERGY DRIVES MOTION
Field evolution follows energy gradients. High-energy zones (stress) restructure until they reach a local minimum (knowledge).

### LAW 3 — TOPOLOGICAL LOCALITY
Information only flows between immediate exclusivity neighbors. There is no global "controller".

### LAW 4 — THERMODYNAMIC GATING
Outputs are gated by field entropy. Records with high entropy are marked as `is_unstable` and require multi-step relaxation to resolve.

---

## Implementation Details

*   **Relaxation Trajectory**: The path a basin takes toward equilibrium.
*   **Solidification**: The process by which stable patterns develop hysteresis and resist decay.
*   **Stability Debt**: Accumulated unresolved tension that eventually triggers a sudden phase transition (restructuring).
