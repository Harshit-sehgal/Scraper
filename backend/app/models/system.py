"""System domain models — status, audit log, selector memory/stats, operator
responses, and scraper router response models.
"""

from typing import Any

from pydantic import BaseModel


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str


class AuditLogResponse(BaseModel):
    """Response model for GET /api/system/audit-log."""

    total: int
    limit: int
    category: str
    items: list[Any]


class RemoveDenylistResponse(BaseModel):
    """Response model for DELETE /api/operator/denylist."""

    message: str
    domain: str
    path_prefix: str


# ─── Scraper Router Response Models ───────────────────────────────────


class ScraperConfigResponse(BaseModel):
    """Response model for GET /api/scraper/config."""

    playwright_timeout: int
    page_settle_delay: float
    request_timeout: int
    max_retries: int
    max_records_per_source: int
    selector_snippet_max_chars: int
    regex_max_containers: int


class SelectorMemoryStatsResponse(BaseModel):
    """Response model for GET /api/scraper/memory/stats."""

    domain_count: int
    total_successes: int
    total_failures: int
    top_domains: list[dict[str, Any]]


class ScraperStatsResponse(BaseModel):
    """Response model for GET /api/scraper/stats."""

    confidence_histogram: list[list[int | float]]
    recent_latency_avg: float
    recent_success_rate: float


class PreviewResponse(BaseModel):
    """Response model for POST /api/scraper/preview."""

    url: str
    total_records_found: int
    preview_records: list[Any]
    dry_run: bool


class RegressionTestGenerateResponse(BaseModel):
    """Response model for POST /api/scraper/regressions/{entry_id}/generate-test."""

    entry_id: str
    test_code: str


class RegressionGenerateAllResponse(BaseModel):
    """Response model for POST /api/scraper/regressions/generate-all-tests."""

    total_tests_generated: int
    test_code: str


class SelectorMemoryFullStatsResponse(BaseModel):
    """Response model for GET /api/scraper/selectors/stats."""

    total_domains: int
    total_selectors: int
    avg_confidence: float
    high_confidence: int
    medium_confidence: int
    low_confidence: int
    confidence_distribution: dict[str, int]


class DomainConfidenceResponse(BaseModel):
    """Response model for GET /api/scraper/selectors/domain/{domain}."""

    domain: str
    raw_confidence: float
    age_factor: float
    freshness_factor: float
    final_score: float
    reason: str


class SelectorCleanupResponse(BaseModel):
    """Response model for POST /api/scraper/selectors/cleanup."""

    message: str | None = None
    next_cleanup_available_in_seconds: int | None = None
    domains_checked: int | None = None
    selectors_deleted: int | None = None
    deleted_domains: int | None = None
    low_confidence_selectors: int | None = None


class LowConfidenceSelectorItem(BaseModel):
    """A single low-confidence selector entry."""

    domain: str
    score: float
    raw_confidence: float
    age_factor: float
    freshness_factor: float
    success_count: int
    failure_count: int
    reason: str


class LowConfidenceSelectorsResponse(BaseModel):
    """Response model for GET /api/scraper/selectors/low-confidence."""

    threshold: float
    count: int
    selectors: list[LowConfidenceSelectorItem]
