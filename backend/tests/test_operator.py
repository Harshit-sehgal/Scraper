"""Tests for the operator router: mode switching, dashboard, predictions."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.routers.operator import router as operator_router
from app.visualization import OperatorMode
from fastapi import FastAPI

# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


class LocalASGIClient:
    """Small sync wrapper around httpx ASGITransport that avoids TestClient threads."""

    def __init__(self, app):
        self.app = app

    async def _request(self, method: str, url: str, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await ac.request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs):
        return asyncio.run(self._request(method, url, **kwargs))

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(operator_router)
    return a


@pytest.fixture
def client(app):
    return LocalASGIClient(app)


# ─────────────────────────────────────────────────────────────────────
# Mode Endpoint Tests
# ─────────────────────────────────────────────────────────────────────


class TestGetMode:
    def test_get_mode_returns_valid_response(self, client):
        with patch("app.routers.operator.get_governance_dashboard") as mock_dash:
            mock_instance = MagicMock()
            mock_instance.active_mode = OperatorMode.PRODUCTION
            mock_instance.get_governance_summary.return_value = {
                "resources": {"token_spend_dollars": 0.0},
            }
            mock_dash.return_value = mock_instance

            resp = client.get("/api/operator/mode")
            assert resp.status_code == 200
            data = resp.json()
            assert data["active_mode"] == "production"
            assert "available_modes" in data
            assert "production" in data["available_modes"]
            assert "forensic" in data["available_modes"]

    def test_get_mode_has_all_five_modes(self, client):
        with patch("app.routers.operator.get_governance_dashboard") as mock_dash:
            mock_instance = MagicMock()
            mock_instance.active_mode = OperatorMode.PRODUCTION
            mock_instance.get_governance_summary.return_value = {}
            mock_dash.return_value = mock_instance

            resp = client.get("/api/operator/mode")
            modes = resp.json()["available_modes"]
            for expected in ("production", "benchmark", "forensic", "stealth", "low_cost"):
                assert expected in modes, f"Missing mode: {expected}"


class TestSetMode:
    def test_set_mode_valid(self, client):
        with patch("app.routers.operator.get_governance_dashboard") as mock_dash:
            mock_instance = MagicMock()
            mock_instance.active_mode = OperatorMode.FORENSIC
            mock_instance.set_operator_mode.return_value = {"settle_delay": 1500}
            mock_dash.return_value = mock_instance

            resp = client.post("/api/operator/mode", json={"mode": "forensic"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["active_mode"] == "forensic"
            assert "message" in data

    def test_set_mode_invalid(self, client):
        resp = client.post("/api/operator/mode", json={"mode": "invalid_mode"})
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_set_mode_case_insensitive(self, client):
        with patch("app.routers.operator.get_governance_dashboard") as mock_dash:
            mock_instance = MagicMock()
            mock_instance.active_mode = OperatorMode.STEALTH
            mock_instance.set_operator_mode.return_value = {"stealth": True}
            mock_dash.return_value = mock_instance

            resp = client.post("/api/operator/mode", json={"mode": "STEALTH"})
            assert resp.status_code == 200
            assert resp.json()["active_mode"] == "stealth"

    def test_set_mode_all_modes_valid(self, client):
        for mode in ("production", "benchmark", "forensic", "stealth", "low_cost"):
            with patch("app.routers.operator.get_governance_dashboard") as mock_dash:
                mock_instance = MagicMock()
                mock_instance.active_mode = OperatorMode(mode)
                mock_instance.set_operator_mode.return_value = {}
                mock_dash.return_value = mock_instance

                resp = client.post("/api/operator/mode", json={"mode": mode})
                assert resp.status_code == 200, f"Mode '{mode}' failed: {resp.json()}"


# ─────────────────────────────────────────────────────────────────────
# Dashboard Endpoint Tests
# ─────────────────────────────────────────────────────────────────────


class TestDashboard:
    def test_dashboard_returns_all_sections(self, client):
        with (
            patch("app.routers.operator.get_governance_dashboard") as mock_dash,
            patch("app.routers.operator.get_domain_health_monitor") as mock_monitor,
            patch("app.routers.operator.get_browser_pool") as mock_pool,
            patch("app.routers.operator.get_scrape_telemetry") as mock_telemetry,
        ):
            # Mock dashboard
            dash_instance = MagicMock()
            dash_instance.active_mode = OperatorMode.PRODUCTION
            dash_instance.get_governance_summary.return_value = {
                "resources": {
                    "token_spend_dollars": 0.42,
                    "metrics": {"browser_prunes": 2, "queue_sheds": 1},
                },
            }
            mock_dash.return_value = dash_instance

            # Mock domain health monitor
            monitor_instance = MagicMock()
            monitor_instance.get_all_domains_health.return_value = [
                {"domain": "a.com", "health_level": "healthy"},
                {"domain": "b.com", "health_level": "degrading"},
                {"domain": "c.com", "health_level": "unhealthy"},
            ]
            mock_monitor.return_value = monitor_instance

            # Mock browser pool
            pool_instance = MagicMock()
            pool_instance.get_metrics.return_value = {
                "active_contexts": 3,
                "total_contexts": 8,
            }
            mock_pool.return_value = pool_instance

            # Mock telemetry
            telemetry_instance = MagicMock()
            telemetry_instance.get_recent.return_value = [
                {"fallback_triggered": False} if i < 15
                else {"fallback_triggered": True}
                for i in range(20)
            ]
            mock_telemetry.return_value = telemetry_instance

            resp = client.get("/api/operator/dashboard")
            assert resp.status_code == 200
            data = resp.json()

            assert data["active_mode"] == "production"
            assert data["domains"]["total_monitored"] == 3
            assert data["domains"]["healthy"] == 1
            assert data["domains"]["degrading"] == 1
            assert data["domains"]["unhealthy"] == 1
            assert data["browser"]["active_contexts"] == 3
            assert data["telemetry"]["recent_successes"] == 15
            assert data["telemetry"]["recent_failures"] == 5
            assert data["governor"]["token_spend_dollars"] == 0.42


# ─────────────────────────────────────────────────────────────────────
# Predictions Endpoint Tests
# ─────────────────────────────────────────────────────────────────────


class TestPredictionEndpoints:
    def test_get_predictions_no_data(self, client):
        with patch("app.routers.operator.get_scrape_telemetry") as mock_telemetry:
            telemetry_instance = MagicMock()
            telemetry_instance.get_recent.return_value = []
            mock_telemetry.return_value = telemetry_instance

            resp = client.get("/api/operator/predictions")
            assert resp.status_code == 200
            data = resp.json()
            assert data["domains_analyzed"] == 0
            assert "message" in data

    def test_get_predictions_with_data(self, client):
        with (
            patch("app.routers.operator.get_scrape_telemetry") as mock_telemetry,
            patch("app.routers.operator.get_degradation_predictor") as mock_predictor,
            patch("app.routers.operator.TrendAnalyzer") as mock_analyzer_cls,
        ):
            # Telemetry with data
            telemetry_instance = MagicMock()
            telemetry_instance.get_recent.return_value = [
                {"url": "https://example.com/page", "success": True}
                for _ in range(10)
            ]
            mock_telemetry.return_value = telemetry_instance

            # Mock TrendAnalyzer
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = MagicMock(
                domain_trends={"example.com": {"health_score": 80.0}}
            )
            mock_analyzer_cls.return_value = mock_analyzer

            # Mock predictor
            predictor_instance = MagicMock()
            predictor_instance.predict.return_value.to_dict.return_value = {
                "generated_at": None,
                "domains_analyzed": 1,
                "predictions": [],
                "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "systemic_risk_level": "low",
                "top_risks": [],
            }
            mock_predictor.return_value = predictor_instance

            resp = client.get("/api/operator/predictions")
            assert resp.status_code == 200
            data = resp.json()
            assert data["domains_analyzed"] == 1
            assert data["systemic_risk_level"] == "low"

    def test_get_predictions_min_confidence_filter(self, client):
        with (
            patch("app.routers.operator.get_scrape_telemetry") as mock_telemetry,
            patch("app.routers.operator.get_degradation_predictor") as mock_predictor,
            patch("app.routers.operator.TrendAnalyzer") as mock_analyzer_cls,
        ):
            telemetry_instance = MagicMock()
            telemetry_instance.get_recent.return_value = [
                {"url": "https://example.com/page", "success": True}
                for _ in range(10)
            ]
            mock_telemetry.return_value = telemetry_instance

            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = MagicMock(
                domain_trends={"example.com": {"health_score": 80.0}}
            )
            mock_analyzer_cls.return_value = mock_analyzer

            predictor_instance = MagicMock()
            predictor_instance.predict.return_value.to_dict.return_value = {
                "generated_at": None,
                "domains_analyzed": 1,
                "predictions": [
                    {"domain": "a.com", "confidence": 0.4},
                    {"domain": "b.com", "confidence": 0.8},
                ],
                "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "systemic_risk_level": "low",
                "top_risks": [],
            }
            mock_predictor.return_value = predictor_instance

            resp = client.get("/api/operator/predictions?min_confidence=0.7")
            assert resp.status_code == 200
            data = resp.json()
            assert data["summary"]["total_filtered"] == 1

    def test_get_domain_prediction_not_found(self, client):
        with patch("app.routers.operator.get_scrape_telemetry") as mock_telemetry:
            telemetry_instance = MagicMock()
            telemetry_instance.get_recent.return_value = [
                {"url": "https://other.com/page", "success": True}
            ]
            mock_telemetry.return_value = telemetry_instance

            resp = client.get("/api/operator/predictions/unknown.com")
            assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# Health Summary Endpoint Tests
# ─────────────────────────────────────────────────────────────────────


class TestHealthSummary:
    def test_health_summary_healthy(self, client):
        with (
            patch("app.routers.operator.get_scrape_telemetry") as mock_telemetry,
            patch("app.routers.operator.get_browser_pool") as mock_pool,
            patch("app.routers.operator.get_domain_health_monitor") as mock_monitor,
            patch("app.routers.operator.get_governance_dashboard") as mock_dash,
        ):
            telemetry_instance = MagicMock()
            telemetry_instance.get_recent.return_value = [
                {"fallback_triggered": False} for _ in range(20)
            ]
            mock_telemetry.return_value = telemetry_instance

            pool_instance = MagicMock()
            pool_instance.get_metrics.return_value = {"active_contexts": 2}
            mock_pool.return_value = pool_instance

            monitor_instance = MagicMock()
            monitor_instance.get_all_domains_health.return_value = [
                {"domain": "a.com", "health_level": "healthy"},
            ]
            mock_monitor.return_value = monitor_instance

            dash_instance = MagicMock()
            dash_instance.active_mode = OperatorMode.PRODUCTION
            mock_dash.return_value = dash_instance

            resp = client.get("/api/operator/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["mode"] == "production"
            assert data["success_rate"] == 1.0
            assert data["domains_degraded"] == 0

    def test_health_summary_degraded(self, client):
        with (
            patch("app.routers.operator.get_scrape_telemetry") as mock_telemetry,
            patch("app.routers.operator.get_browser_pool") as mock_pool,
            patch("app.routers.operator.get_domain_health_monitor") as mock_monitor,
            patch("app.routers.operator.get_governance_dashboard") as mock_dash,
        ):
            telemetry_instance = MagicMock()
            telemetry_instance.get_recent.return_value = [
                {"fallback_triggered": False} if i < 10 else {"fallback_triggered": True}
                for i in range(20)
            ]
            mock_telemetry.return_value = telemetry_instance

            pool_instance = MagicMock()
            pool_instance.get_metrics.return_value = {"active_contexts": 1}
            mock_pool.return_value = pool_instance

            monitor_instance = MagicMock()
            monitor_instance.get_all_domains_health.return_value = [
                {"domain": "a.com", "health_level": "unhealthy"},
            ]
            mock_monitor.return_value = monitor_instance

            dash_instance = MagicMock()
            dash_instance.active_mode = OperatorMode.BENCHMARK
            mock_dash.return_value = dash_instance

            resp = client.get("/api/operator/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["domains_degraded"] == 1
