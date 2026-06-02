"""
Phase 68: Active Semantic Governance & Policy Enforcement Tests
==============================================================
LAW: All cognitive cycles must be bounded by governance policies.
"""

from app.graph_update_scheduler import GlobalCognitiveScheduler
from app.semantic_world_state import SemanticWorldState


def test_governance_guardrail_enforcement():
    """Verify that thermodynamic violations trigger emergency stabilization."""
    ws = SemanticWorldState(node_id="gov_test")
    ws.clear()
    scheduler = GlobalCognitiveScheduler(ws=ws)

    # Simulate high-pressure violation
    for _ in range(5):
        with ws.transaction("overload"):
            for i in range(10):
                ws._topology.add([f"role_{i}"], f"token_{i}", instability=1.0)
            ws._energy.update_from_regions(ws._topology._regions)

    # Check pressure is high enough for the TEST threshold
    pressure = ws.get_system_pressure()
    assert pressure > 0.4  # Threshold reached after smoothing

    # Temporarily lower the policy threshold for this test
    from app.policy_engine import get_policy_engine

    policy = get_policy_engine(ws=ws)
    old_threshold = policy.critical_entropy_threshold
    policy.critical_entropy_threshold = 0.4

    try:
        # 2. Run scheduler step (should trigger enforcement)
        scheduler.step(budget_ms=10.0)

        # 3. Verify emergency stabilization triggered via telemetry
        telemetry = ws.observability_telemetry
        events = [t["type"] for t in telemetry]
        assert "governance_enforcement" in events

        # Optional: check if pressure actually dropped (if smoothing allows)
        # new_pressure = ws.get_system_pressure()
        # assert new_pressure <= pressure

        print("\nGovernance Enforcement: Emergency stabilization successfully triggered.")

    finally:
        policy.critical_entropy_threshold = old_threshold


def test_community_density_quota():
    """Verify that community density violations are detected."""
    from app.policy_engine import get_policy_engine

    ws = SemanticWorldState(node_id="quota_test")
    ws.clear()
    policy = get_policy_engine(ws=ws)
    policy.max_community_density = 5  # Set low for test

    # 1. Create bloated community
    with ws.transaction("bloat"):
        roles = [f"role_{i}" for i in range(10)]
        for i, r in enumerate(roles):
            ws._topology.add([r], f"t_{i}")

        # Link all in one community via high cohesion
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                key = tuple(sorted([roles[i], roles[j]]))
                ws._topology.set_neighborhood_cohesion(key, 0.9)

    # 2. Refresh communities
    ws._topology.detect_communities()

    # 3. Validate health
    health = policy.validate_substrate_health()
    issues = [i for i in health["issues"] if i["policy"] == "community_density"]

    assert len(issues) > 0
    assert issues[0]["severity"] == "moderate"

    print("\nCommunity Density: Quota violation correctly detected.")
