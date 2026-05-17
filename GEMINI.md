# Architecture & Ontology Rules

## Semantic Field Substrate
This project implements a topology-native dynamical system. 

### Core Laws:
1. **Meaning from Topology**: No symbolic score lookups. Role compatibility is a geometric distance in the **Role Manifold**. Interpretation settles via **Manifold Relaxation** (Contrastive Repulsion vs Affinity Attraction).
2. **Energy is Causal**: Energy gradients drive instability motion. Energy generates equilibrium, not vice versa. Potential energy includes structural tension and grounding violations.
3. **Flow-native Cognition**: Meaning emerges from continuous field relaxation. **Motif Gravity** pulls interpretation toward stable topological patterns.
4. **Metastability & Phase Transitions**: High-energy states use **Stability Debt** to escape local minima, triggering sudden restructuring of the field geometry.
5. **No Procedural Overrides**: Basins evolve probabilistically based on field demand. Global relaxation follows the law of **Topological Entropy** (Inertial decay).
6. **Cross-Scale Causality**: Macro schema instability (Schema Tension) builds from micro regional conflicts and biases future local interpretations.

## Metric Ecology & Ownership (The Ontology Matrix)

| Canonical Variable | State / Representation | Authority | Rule |
| --- | --- | --- | --- |
| **Maturity** | Derived (`metrics.maturity`) | EnergyState | Defined by experience manifold. Do NOT store. |
| **Pressure** | Derived (`metrics.field_pressure`) | EnergyState | Weighted blend of Energy and Entropy. Do NOT store. |
| **Energy** | Semi-Derived (`global_energy`, `local_energy`) | Basin Dynamics | Motion potential. Updates via gradient descent and cross-scale feedback. |
| **Convergence**| Mixed (`local_convergence`, `_convergence`) | Regions + Aggregate | Local attractor settling; feeds global manifold stability. |
| **Entropy** | Derived (`global_entropy`) | Instability Dist | Mean instability across all basins. Used to compute pressure. |
| **Topology** | Stored (`role_manifold`, `cohesion`) | World State | The physical structure of meaning. Evolves via relaxation. |

### Enforcing Metric Law
- **No dangling state**: Never store derived metrics loosely on subsystems (e.g., `SemanticWorldState` should never define `self.maturity` or `self.pressure`). Access them only from their owning class/property.
- **Canonical variables**: State must collapse toward three canonical domains: **Energy** (motion potential), **Topology** (semantic structure), and **Entropy** (disorder). All else is derived.