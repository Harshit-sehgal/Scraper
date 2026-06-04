"""API — FastAPI app factory, middleware, and routers for the product kernel."""

from forge_kernel.api.app import create_app
from forge_kernel.api.deps import get_jobs_store, get_recycle_bin_store

__all__ = ["create_app", "get_jobs_store", "get_recycle_bin_store"]
