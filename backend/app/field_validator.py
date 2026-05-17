"""Runtime field state validation — catches structural drift before it propagates."""

import math


def validate_world_state(ws) -> list:
    """Validate world state integrity. Returns list of issues found (empty = clean)."""
    issues = []
    view = ws.get_topology_view()
    regions = view.all_regions()

    # 1. NaN/Inf energy values
    if math.isnan(ws.metrics.global_energy) or math.isinf(ws.metrics.global_energy):
        issues.append("global_energy is NaN or Inf")
    if math.isnan(ws.metrics.global_entropy) or math.isinf(ws.metrics.global_entropy):
        issues.append("global_entropy is NaN or Inf")

    # 2. Orphan regions (regions with no competing roles)
    for i, r in enumerate(regions):
        if not r.competing_roles:
            issues.append(f"Orphan region {i}: token={r.token} has no competing_roles")
        if math.isnan(r.instability) or math.isinf(r.instability):
            issues.append(f"Region {i}: token={r.token} has NaN instability")

    # 3. Instability out of bounds
    for i, r in enumerate(regions):
        if not (0.0 <= r.instability <= 1.0):
            issues.append(f"Region {i}: instability={r.instability} out of bounds [0,1]")

    # 4. Energy out of bounds
    for i, r in enumerate(regions):
        if not (0.0 <= r.local_energy <= 10.0):
            issues.append(f"Region {i}: local_energy={r.local_energy} out of bounds [0,10]")

    # 5. Exclusion bounds
    for key, val in ws.learned_exclusions.items():
        if not (0.0 <= val <= 1.0):
            issues.append(f"Exclusion {key}={val} out of bounds [0,1]")

    # 6. Metric bounds
    if not (0.0 <= ws.metrics.global_energy <= 10.0):
        issues.append(f"global_energy={ws.metrics.global_energy} out of bounds [0,10]")
    if not (0.0 <= ws.metrics.global_entropy <= 1.0):
        issues.append(f"global_entropy={ws.metrics.global_entropy} out of bounds [0,1]")

    # 7. Memory bounds
    if len(ws.decision_history) > 5000:
        issues.append(f"decision_history={len(ws.decision_history)} > 5000 entries")
    if view.region_count() > 500:
        issues.append(f"field_regions={view.region_count()} > 500 — possible bloat")
    if len(ws.learned_exclusions) > 500:
        issues.append(f"learned_exclusions={len(ws.learned_exclusions)} > 500 — possible bloat")

    # 8. Integrity bounds
    for i, r in enumerate(regions):
        if not (0.0 <= r.integrity <= 1.0):
            issues.append(f"Region {i}: integrity={r.integrity} out of bounds [0,1]")

    return issues
