"""Test runtime field validation."""

from app.field_validator import validate_world_state
from app.semantic_world_state import get_world_state
from app.semantic_persistence import clear_semantic_state


def test_fresh_state_is_valid():
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    issues = validate_world_state(ws)
    assert not issues, f"Fresh state should be clean: {issues}"


def test_nan_energy_detected():
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws._energy._global_energy = float("nan")  # Bypass setter
    issues = validate_world_state(ws)
    assert any("NaN" in i for i in issues)
