"""Phase 51: Topology-Partitioned Concurrency (Hybrid MVCC) Tests.
==============================================================
LAW: Distributed semantic systems must handle concurrent evolution without
global locking bottlenecks. MVCC ensures causality is preserved.
"""

import threading

import pytest
from app.semantic_world_state import SemanticWorldState
from app.topology_state import ConflictError


@pytest.fixture
def ws():
    state = SemanticWorldState()
    state.clear()
    return state


def test_mvcc_conflict_detection(ws) -> None:
    """Verify that concurrent modifications to the same region trigger ConflictError."""
    # 1. Create a region
    with ws.transaction("setup"):
        r = ws._topology.add(["role_a"], "token", instability=0.5)
        region_id = r.region_id

    results = []
    # B signals this event when it has committed, so A knows it's safe
    # to attempt its own (now-conflicting) modification. A signals when
    # it has read the region, so B only commits after that read — without
    # this ordering the test races: if B commits before A's read, the
    # write is not a conflict and the test spuriously fails.
    b_committed = threading.Event()
    a_read = threading.Event()

    def run_tx_A() -> None:
        try:
            with ws.transaction("tx_A"):
                # 2. Transaction A starts and reads the region
                view = ws.get_topology_view()
                _ = view.all_regions()

                # 3. Tell B the read happened, then wait for B to commit —
                # no wall-clock dependency
                a_read.set()
                b_committed.wait(timeout=5.0)

                # 4. Transaction A tries to modify the region
                ws._topology.set_region_instability(region_id, 0.2)
                # Commit will happen here
            results.append("A_SUCCESS")
        except ConflictError:
            results.append("A_CONFLICT")
        except Exception as e:
            results.append(f"A_ERROR: {e}")

    def run_tx_B() -> None:
        try:
            # Only write after A's read, so the write is guaranteed to
            # conflict with A's in-flight transaction.
            a_read.wait(timeout=5.0)
            with ws.transaction("tx_B"):
                # 3. Transaction B modifies AND COMMITS the region
                ws._topology.set_region_instability(region_id, 0.8)
            results.append("B_SUCCESS")
            b_committed.set()
        except Exception as e:
            results.append(f"B_ERROR: {e}")

    t1 = threading.Thread(target=run_tx_A)
    t2 = threading.Thread(target=run_tx_B)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    assert "B_SUCCESS" in results
    assert "A_CONFLICT" in results
    assert "A_SUCCESS" not in results


def test_version_incrementing(ws) -> None:
    """Verify that every commit increments region versions."""
    with ws.transaction("tx1"):
        r = ws._topology.add(["r1"], "t1", instability=0.5)
        rid = r.region_id
        v0 = r.version

    with ws.transaction("tx2"):
        ws._topology.set_region_instability(rid, 0.7)

    r_live = next(r for r in ws._topology._regions if r.region_id == rid)
    assert r_live.version == v0 + 1
