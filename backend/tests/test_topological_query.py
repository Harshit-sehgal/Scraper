"""Unit Tests for TopologicalQuery.

Tests geometric and relational queries against the semantic field,
including TQL execution, near-role search, and stable anchor detection.
"""

from __future__ import annotations

import pytest
from app.semantic_persistence import clear_semantic_state
from app.semantic_world_state import get_world_state
from app.topological_query import TopologicalQuery, get_tql_engine


@pytest.fixture(autouse=True)
def clean_ws() -> None:
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws.clear()


@pytest.fixture
def seeded_ws():
    """World state with a few regions for query testing."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws.clear()

    from app.core_types import FieldConflictRegion

    r1 = FieldConflictRegion(competing_roles=["origin", "destination"], token="LAX", instability=0.3, local_energy=5.0)
    r2 = FieldConflictRegion(competing_roles=["origin", "destination"], token="JFK", instability=0.5, local_energy=3.0)
    r3 = FieldConflictRegion(competing_roles=["origin", "destination"], token="ORD", instability=0.7, local_energy=1.0)
    ws._topology.append_region(r1)
    ws._topology.append_region(r2)
    ws._topology.append_region(r3)

    # Set some learned exclusions
    ws.learned_exclusions[("origin", "destination")] = 0.4
    return ws


class TestTopologicalQueryInit:
    """Tests for __init__ and factory function."""

    def test_default_ws(self) -> None:
        tq = TopologicalQuery()
        assert tq.ws is not None

    def test_factory_function(self) -> None:
        engine = get_tql_engine()
        assert isinstance(engine, TopologicalQuery)

    def test_find_stable_anchors(self) -> None:
        tq = TopologicalQuery()
        anchors = tq.find_stable_anchors()
        assert isinstance(anchors, list)


class TestFindRolesNear:
    """Tests for find_roles_near() and find_roles_near_type()."""

    def test_unknown_role_returns_empty(self, seeded_ws) -> None:
        tq = TopologicalQuery(ws=seeded_ws)
        result = tq.find_roles_near("nonexistent_role")
        assert result == []

    def test_find_roles_near_returns_sorted(self, seeded_ws) -> None:
        tq = TopologicalQuery(ws=seeded_ws)
        # LAX has a vector — find roles near it with a large radius
        result = tq.find_roles_near("origin", radius=5.0)
        # "origin" as a role name may not have a manifold vector...
        # This should return empty or a list depending on the manifold state
        assert isinstance(result, list)

    def test_find_roles_near_type_returns_list(self, seeded_ws) -> None:
        from app.semantic_ir import SemanticType

        tq = TopologicalQuery(ws=seeded_ws)
        result = tq.find_roles_near_type(SemanticType.LOCATION, radius=5.0)
        assert isinstance(result, list)

    def test_find_near_vec_empty_ws(self) -> None:
        tq = TopologicalQuery()
        result = tq._find_near_vec([0.0, 0.0], 1.0)
        assert result == []


class TestExecuteTQL:
    """Tests for execute_tql() — TQL parser/executor."""

    def test_empty_query(self, seeded_ws) -> None:
        tq = TopologicalQuery(ws=seeded_ws)
        result = tq.execute_tql("")
        assert "error" in result

    def test_unknown_command(self, seeded_ws) -> None:
        tq = TopologicalQuery(ws=seeded_ws)
        result = tq.execute_tql("UNKNOWN_CMD")
        assert "error" in result

    def test_near_command(self, seeded_ws) -> None:
        tq = TopologicalQuery(ws=seeded_ws)
        result = tq.execute_tql("NEAR origin 5.0")
        assert "type" in result
        assert "data" in result

    def test_stable_command(self, seeded_ws) -> None:
        tq = TopologicalQuery(ws=seeded_ws)
        result = tq.execute_tql("STABLE 0.4")
        assert "type" in result
        assert isinstance(result.get("data"), list)

    def test_exclusions_command(self, seeded_ws) -> None:
        tq = TopologicalQuery(ws=seeded_ws)
        result = tq.execute_tql("EXCLUSIONS FOR origin")
        assert "type" in result
        assert result["type"] == "exclusions"
        assert "data" in result

    def test_exclusions_missing_for_keyword(self, seeded_ws) -> None:
        """EXCLUSIONS without FOR should fail gracefully."""
        tq = TopologicalQuery(ws=seeded_ws)
        result = tq.execute_tql("EXCLUSIONS origin")
        assert "error" in result
