from app.semantic_world_state import get_world_state


def test_transaction_commit():
    ws = get_world_state()
    ws.clear()

    with ws.transaction():
        ws._energy.set_energy(8.0)
        assert ws.metrics.global_energy == 8.0

    # After commit, value should persist
    assert ws.metrics.global_energy == 8.0


def test_transaction_rollback():
    ws = get_world_state()
    ws.clear()
    initial_energy = ws.metrics.global_energy

    try:
        with ws.transaction():
            ws._energy.set_energy(9.0)
            assert ws.metrics.global_energy == 9.0
            raise ValueError("Intentional failure")
    except ValueError:
        pass

    # After rollback, value should be restored
    assert ws.metrics.global_energy == initial_energy


def test_nested_transaction():
    ws = get_world_state()
    ws.clear()

    with ws.transaction():
        ws._energy.set_energy(7.0)
        with ws.transaction():
            ws._energy.set_energy(6.0)
            assert ws.metrics.global_energy == 6.0
        assert ws.metrics.global_energy == 6.0

    assert ws.metrics.global_energy == 6.0


def test_nested_transaction_rollback():
    ws = get_world_state()
    ws.clear()
    initial_energy = ws.metrics.global_energy

    try:
        with ws.transaction():
            ws._energy.set_energy(7.0)
            try:
                with ws.transaction():
                    ws._energy.set_energy(6.0)
                    raise ValueError("Nested failure")
            except ValueError:
                # This should NOT trigger a global rollback yet,
                # but because our current implementation rolls back EVERYTHING
                # if the outer-most transaction fails, we need to see how it behaves.
                pass

            assert ws.metrics.global_energy == 6.0
            raise ValueError("Outer failure")
    except ValueError:
        pass

    assert ws.metrics.global_energy == initial_energy


def test_topology_transaction_rollback():
    ws = get_world_state()
    ws.clear()

    from app.core_types import FieldConflictRegion

    region = FieldConflictRegion(competing_roles=["role_a"], token="test", instability=0.5)
    ws._topology.append_region(region)
    rid = region.region_id

    try:
        with ws.transaction():
            ws._topology.set_region_instability(rid, 0.9)
            # Staged value should be 0.9
            staged = ws._topology.get_view().find_by_token_and_roles("test", ("role_a",))
            assert staged is not None
            assert staged.instability == 0.9
            raise ValueError("Rollback")
    except ValueError:
        pass

    # After rollback, value should be 0.5
    committed = ws._topology.get_view().find_by_token_and_roles("test", ("role_a",))
    assert committed is not None
    assert committed.instability == 0.5


def test_topology_addition_rollback():
    ws = get_world_state()
    ws.clear()

    try:
        with ws.transaction():
            ws._topology.add(["role_b"], "test2", instability=0.8)
            assert ws._topology.region_count() == 1
            raise ValueError("Rollback")
    except ValueError:
        pass

    assert ws._topology.region_count() == 0


def test_failure_injection_rollback():
    ws = get_world_state()
    ws.clear()
    initial_energy = ws.metrics.global_energy

    from app.failure_injector import set_injection_probability

    set_injection_probability(1.0)  # Guarantee failure

    try:
        with ws.transaction("guaranteed_fail"):
            ws._energy.set_energy(2.0)
            from app.failure_injector import get_injector

            get_injector().inject("test_point")
    except RuntimeError:
        pass
    finally:
        set_injection_probability(0.0)  # Reset

    assert ws.metrics.global_energy == initial_energy


def test_deterministic_replay():
    ws = get_world_state()
    ws.clear()

    # 1. Execute a transaction
    with ws.transaction("original"):
        ws._energy.set_energy(4.0)
        # Mutations now record deltas AUTOMATICALLY via callback
        ws._topology.add(["role_c"], "replay_test", instability=0.6)

    journal = ws.trace_causality()
    assert len(journal) > 0
    tx = journal[-1]

    # 2. Clear state and replay
    ws.clear()
    assert ws.metrics.global_energy == 5.0
    assert ws._topology.region_count() == 0

    ws.replay_transaction(tx)

    # 3. Verify state restored
    assert ws.metrics.global_energy == 4.0
    assert ws._topology.region_count() == 1
    assert ws._topology.get_view().all_regions()[0].token == "replay_test"
