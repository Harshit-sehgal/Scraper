"""
Routers — API route definitions for the product kernel.
"""

from forge_kernel.api.routers.exports import router as exports_router
from forge_kernel.api.routers.health import router as health_router
from forge_kernel.api.routers.jobs import router as jobs_router
from forge_kernel.api.routers.system import router as system_router

__all__ = ["exports_router", "health_router", "jobs_router", "system_router"]
