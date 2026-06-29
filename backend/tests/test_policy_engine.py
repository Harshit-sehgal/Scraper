"""Tests for SubstratePolicy and its module-level singleton."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.policy_engine import SubstratePolicy, get_policy_engine


@pytest.fixture(autouse=True)
def _mock_world_state() -> None:
    """Prevent SubstratePolicy from initializing a real SemanticWorldState."""
    with patch("app.policy_engine.get_world_state") as mock_gws:
        mock_ws = MagicMock()
        mock_ws.global_communities = []
        mock_ws.get_system_pressure.return_value = 0.0
        mock_ws.capture_governance_snapshot.return_value = {}
        mock_gws.return_value = mock_ws
        yield


class TestSubstratePolicy:
    """Tests for SubstratePolicy behavior."""

    def test_create_policy(self) -> None:
        policy = SubstratePolicy()
        assert policy is not None
        assert policy.max_community_density == 15
        assert policy.critical_entropy_threshold == 0.8
        assert policy.min_attractor_plasticity == 0.1

    def test_can_dispatch_action_allows_critical_at_low_pressure(self) -> None:
        policy = SubstratePolicy()
        assert policy.can_dispatch_action("role_merger", 0.5) is True

    def test_can_dispatch_action_blocks_at_high_pressure(self) -> None:
        policy = SubstratePolicy()
        assert policy.can_dispatch_action("unknown_action", 1.6) is False

    def test_validate_substrate_health_returns_dict(self) -> None:
        policy = SubstratePolicy()
        policy.ws._observability.get_semantic_health_index.return_value = {
            "metrics": {"diversity": 0.9},
        }
        health = policy.validate_substrate_health()
        assert "valid" in health
        assert "issues" in health


class TestPolicyEngineSingleton:
    """Tests for the module-level thread-safe singleton."""

    def test_singleton_returns_same_instance(self) -> None:
        p1 = get_policy_engine()
        p2 = get_policy_engine()
        assert p1 is p2

    def test_singleton_is_substrate_policy(self) -> None:
        p = get_policy_engine()
        assert isinstance(p, SubstratePolicy)
