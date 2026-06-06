"""Operator Router — operational intelligence endpoints (RESERVED).

All former routes (operator mode switching, governance dashboard, degradation
predictions, system health overview) were backed by research-shell modules
(visualization, domain_health_alerts, trend_analyzer, degradation_predictor).
They have been quarantined to ``routers/experimental.py`` and require
``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true`` to mount.

This router is reserved for future product-kernel operator endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/operator", tags=["operator"])

# No routes currently — all operator routes are research-backed and have
# been moved to app/routers/experimental.py.
