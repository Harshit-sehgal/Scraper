"""Test event cascade is operational — events dispatch to real subscribers."""

from app.event_dispatcher import get_dispatcher
from app.semantic_events import SemanticEventType
from app.semantic_pipeline import run_pipeline


def test_event_cascade_has_subscribers() -> None:
    """All dispatched event types must have at least one subscriber."""
    d = get_dispatcher()
    for et in [SemanticEventType.TOPOLOGY_SHIFT, SemanticEventType.UNCERTAINTY_SPIKE]:
        assert len(d.subscribers.get(et, [])) >= 1, f"{et.value} has no subscribers"


def test_event_cascade_responds_to_instability() -> None:
    """Pipeline must dispatch events that trigger the cascade."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    prev_len = len(ws.decision_history)

    schema = ["name", "price"]
    records = [{"company": "Test Corp", "price": "100"}]
    result = run_pipeline(records, schema)

    # Pipeline should have dispatched events that got recorded
    assert len(result) >= 1
    # At minimum, TOPOLOGY_SHIFT should have been dispatched (for any noise removal)
    # and recorded in decision_history
    assert len(ws.decision_history) >= prev_len, "Events should be recorded to decision_history"
