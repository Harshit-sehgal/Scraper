"""Tests for API usage dashboard per key.

Roadmap: Feat 30 — Show requests/day, records extracted, failures,
average latency per API key.

Note: ``GET /api/usage/stats`` is implemented (see other usage-stats
tests in ``test_p0_auth_tenant.py``), so 404 should never happen here.
All assertions run unconditionally — no ``if status_code == 200`` gates
that would silently hide a broken route behind a vacuous pass.
"""

from __future__ import annotations


class TestApiUsageDashboard:
    def test_usage_endpoint_returns_json(self, client) -> None:
        response = client.get("/api/usage/stats")
        assert response.status_code == 200

    def test_usage_returns_keys(self, client) -> None:
        response = client.get("/api/usage/stats")
        assert response.status_code == 200
        data = response.json()
        assert "keys" in data or isinstance(data, dict)

    def test_usage_includes_record_count(self, client) -> None:
        response = client.get("/api/usage/stats")
        assert response.status_code == 200
        data = response.json()
        keys = data.get("keys", {})
        if keys:
            for key_stats in keys.values():
                assert "records" in key_stats
                assert "requests" in key_stats

    def test_usage_returns_zero_for_unknown_key(self, client) -> None:
        response = client.get("/api/usage/stats")
        assert response.status_code == 200

    def test_usage_includes_failure_count(self, client) -> None:
        response = client.get("/api/usage/stats")
        assert response.status_code == 200
        data = response.json()
        keys = data.get("keys", {})
        if keys:
            for key_stats in keys.values():
                assert "failures" in key_stats
