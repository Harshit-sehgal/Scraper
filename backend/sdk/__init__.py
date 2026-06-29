"""DataForge SDK — Python client for the DataForge Scraper API."""

from __future__ import annotations

from typing import Any


class DataForge:
    """Python client for DataForge Scraper API.

    Usage:
        client = DataForge(api_key="df_key_...")
        job = client.extract(url="https://example.com", schema_fields=[...])
        jobs = client.jobs.list()
    """

    def __init__(self, api_key: str, base_url: str = "http://localhost:8000") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._session: Any = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        import httpx

        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", f"Bearer {self.api_key}")
        headers.setdefault("Content-Type", "application/json")
        async with httpx.AsyncClient(base_url=self.base_url, headers=headers) as client:
            resp = await client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def extract(
        self,
        url: str,
        schema_fields: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create and run an extraction job.

        Args:
            url: Target URL to extract data from.
            schema_fields: List of field definitions.
            **kwargs: Additional job parameters (selectors_map, headers, cookies,
                     fetch_strategy, hydration_wait_ms, scroll_attempts, etc.)

        Returns:
            Job creation response with job_id and status.
        """
        body: dict[str, Any] = {
            "name": kwargs.pop("name", f"SDK extraction: {url}"),
            "mode": "manual",
            "urls": [url],
            "schema_fields": schema_fields or [],
            **kwargs,
        }
        return await self._request("POST", "/api/jobs", json=body)

    async def preview(
        self,
        url: str,
        schema_fields: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Dry-run extraction without persisting a job.

        Args:
            url: Target URL to preview extraction for.
            schema_fields: List of field definitions.
            **kwargs: Additional job parameters.

        Returns:
            Preview response with sample records.
        """
        body: dict[str, Any] = {
            "name": kwargs.pop("name", f"SDK preview: {url}"),
            "mode": "manual",
            "urls": [url],
            "schema_fields": schema_fields or [],
            **kwargs,
        }
        return await self._request("POST", "/api/scraper/preview", json=body)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        """Get job details and results."""
        return await self._request("GET", f"/api/jobs/{job_id}")

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        """Cancel a running or pending job."""
        return await self._request("POST", f"/api/jobs/{job_id}/cancel")

    async def list_jobs(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """List recent jobs."""
        return await self._request("GET", f"/api/jobs?limit={limit}&offset={offset}")

    async def delete_job(self, job_id: str) -> dict[str, Any]:
        """Delete (recycle) a completed job."""
        return await self._request("DELETE", f"/api/jobs/{job_id}")

    async def get_usage(self) -> dict[str, Any]:
        """Get current usage statistics."""
        return await self._request("GET", "/api/saas/usage")
