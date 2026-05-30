import pytest
from app.semantic_os import get_semantic_os


def test_substrate_branching_isolation():
    sos = get_semantic_os()
    sos.ws.clear()

    # 1. Setup main state
    sos.ws._manifold.set_manifold_vector("r1", [0.1] * 16)

    # 2. Branch
    branch_sos = sos.branch_substrate("experiment-1")
    assert branch_sos.ws.node_id != sos.ws.node_id

    # 3. Mutate branch
    branch_sos.ws._manifold.set_manifold_vector("r1", [0.9] * 16)
    branch_sos.ws._manifold.set_manifold_vector("new_role", [0.5] * 16)

    # 4. Verify isolation
    assert sos.ws._manifold.get_manifold_vector("r1")[0] == 0.1
    assert not sos.ws._manifold.has_manifold_role("new_role")

    assert branch_sos.ws._manifold.get_manifold_vector("r1")[0] == 0.9
    assert branch_sos.ws._manifold.has_manifold_role("new_role")


def test_substrate_merging():
    sos = get_semantic_os()
    sos.ws.clear()

    # 1. Main state
    sos.ws._manifold.set_manifold_vector("r1", [0.0] * 16)

    # 2. Branch and evolve
    branch_sos = sos.branch_substrate("merge-test")
    branch_sos.ws._manifold.set_manifold_vector("r1", [1.0] * 16)
    branch_sos.ws._manifold.set_manifold_vector("r2", [0.5] * 16)

    # 3. Diff
    diff = sos.diff_substrate(branch_sos)
    assert diff["manifold_drift"] > 0.5
    assert "r2" in diff["new_roles"]

    # 4. Merge
    sos.merge_substrate(branch_sos, alpha=0.5)

    # 5. Verify results (Linear blend 0.5 * 0.0 + 0.5 * 1.0 = 0.5)
    vec_r1 = sos.ws._manifold.get_manifold_vector("r1")
    assert vec_r1[0] == pytest.approx(0.5)
    assert sos.ws._manifold.has_manifold_role("r2")


def test_causal_lineage_versioning():
    sos = get_semantic_os()
    sos.ws.clear()

    # Transaction on main
    with sos.ws.transaction("main-op"):
        sos.ws._energy.set_energy(1.0)

    main_clock = sos.ws._vector_clock.get_clock()

    # Branch
    branch_sos = sos.branch_substrate("ver-test")

    # Transaction on branch
    with branch_sos.ws.transaction("branch-op"):
        branch_sos.ws._energy.set_energy(2.0)

    branch_clock = branch_sos.ws._vector_clock.get_clock()

    # Verify branch is descendant of main
    assert branch_clock[sos.ws.node_id] == main_clock[sos.ws.node_id]
    assert branch_clock[branch_sos.ws.node_id] > 0

    # Merge back
    sos.merge_substrate(branch_sos)

    # Verify main now has branch's causality
    final_clock = sos.ws._vector_clock.get_clock()
    assert final_clock[branch_sos.ws.node_id] == branch_clock[branch_sos.ws.node_id]
