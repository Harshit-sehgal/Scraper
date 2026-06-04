"""Serialization Symmetry Verification — Phase 47.
=============================================
LAW: All state objects must support bit-for-bit parity in to_dict/from_dict
round-trips to ensure deterministic replay and distributed consistency.
"""

import json
import sys

from app.semantic_world_state import SemanticWorldState


def verify_symmetry(subsystem_name, state_obj) -> bool:
    """Verify that a subsystem's to_dict/from_dict is perfectly symmetrical."""
    original_dict = state_obj.to_dict()

    # Round-trip
    state_obj.from_dict(original_dict)
    new_dict = state_obj.to_dict()

    # Compare
    orig_str = json.dumps(original_dict, sort_keys=True)
    new_str = json.dumps(new_dict, sort_keys=True)

    if orig_str != new_str:
        # Find the difference
        orig_obj = json.loads(orig_str)
        new_obj = json.loads(new_str)
        for k in orig_obj:
            if orig_obj.get(k) != new_obj.get(k):
                pass
        return False

    return True


def test_all_subsystems_symmetry() -> None:
    ws = SemanticWorldState()

    # 1. Populate with some dummy data to ensure we aren't just comparing empty dicts
    ws._manifold.set_manifold_vector("test_role", [0.1] * 16)
    ws._energy.set_energy(7.5)
    ws._instability.set_exclusion(("a", "b"), 0.8)
    ws._motif.reinforce(("type_a", "type_b"), 100)
    ws._topology.add(["r1", "r2"], "token", instability=0.5)

    subsystems = {
        "topology": ws._topology,
        "energy": ws._energy,
        "instability": ws._instability,
        "manifold": ws._manifold,
        "motif": ws._motif,
        "transition": ws._transition,
        "history": ws._history,
        "intent": ws._intent,
        "action": ws._action,
        "abstraction": ws._abstraction,
        "observability": ws._observability,
    }

    all_ok = True
    for name, obj in subsystems.items():
        if not verify_symmetry(name, obj):
            all_ok = False

    # Final WorldState symmetry
    if not verify_symmetry("WorldState", ws):
        all_ok = False

    assert all_ok, "Symmetry verification failed!"


if __name__ == "__main__":
    try:
        test_all_subsystems_symmetry()
    except Exception:
        sys.exit(1)
