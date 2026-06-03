"""Tests for the enriched ScrapeAttemptResult and scrape_url_attempt()."""

from __future__ import annotations

from typing import Any

import pytest
from app.zero_result_classifier import ZeroResultClassification


class LazyClassMeta(type):
    def __instancecheck__(cls, instance):
        import app.scraper

        return isinstance(instance, app.scraper.ScrapeAttemptResult)


class ScrapeAttemptResult(list, metaclass=LazyClassMeta):
    """Test proxy for app.scraper.ScrapeAttemptResult — behaves as a list subclass."""

    html: str | None
    final_url: str | None
    fetch_method: str | None
    extraction_method: str | None
    telemetry: Any
    zero_result_classification: Any
    acquisition_lineage: dict | None
    anti_bot_score: float
    data_evidence_score: float
    recommended_next_action: str
    warnings: list[str]

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        import app.scraper

        return app.scraper.ScrapeAttemptResult(*args, **kwargs)

    def to_telemetry_dict(self) -> dict:
        import app.scraper

        return app.scraper.ScrapeAttemptResult([]).to_telemetry_dict()


async def scrape_url_attempt(*args: Any, **kwargs: Any) -> Any:
    import app.scraper

    return await app.scraper.scrape_url_attempt(*args, **kwargs)


# ── Helper: Stub crawl policy that allows all ──────────────────────────


class _AllowAllCrawlPolicy:
    async def check_domain(self, url):
        return None

    def record_result(self, url, success=True):
        return None


# ── 1. Backward compatibility ────────────────────────────────────────


def test_scrape_attempt_result_is_list_subclass() -> None:
    """ScrapeAttemptResult behaves as a plain list for backward compat."""
    sar = ScrapeAttemptResult(
        [{"name": "Alpha"}, {"name": "Beta"}],
        html="<html><body>Alpha Beta</body></html>",
        final_url="https://example.com/list",
        fetch_method="playwright_full",
        extraction_method="profile",
        telemetry={},
        anti_bot_score=0.1,
        data_evidence_score=0.8,
        recommended_next_action="",
        warnings=["slow page load"],
    )

    # List behaviours
    assert len(sar) == 2
    assert sar[0]["name"] == "Alpha"
    assert sar[1]["name"] == "Beta"

    # Iteration works
    names = [r["name"] for r in sar]
    assert names == ["Alpha", "Beta"]

    # Slicing works
    assert sar[0:1] == [{"name": "Alpha"}]

    # Calling list() on it works
    assert list(sar) == [{"name": "Alpha"}, {"name": "Beta"}]


def test_scrape_attempt_result_empty_list() -> None:
    """An empty ScrapeAttemptResult still behaves as list."""
    sar = ScrapeAttemptResult([])
    assert len(sar) == 0
    assert list(sar) == []


# ── 2. HTML evidence attachment ──────────────────────────────────────


def test_scrape_attempt_result_carries_html_evidence() -> None:
    """HTML evidence is preserved as an attribute, especially for zero-record results."""
    html = "<html><body><div>Some data container</div></body></html>"
    sar = ScrapeAttemptResult(
        [],
        html=html,
        final_url="https://example.com/zero",
        extraction_method="regex",
        zero_result_classification=ZeroResultClassification(
            zero_result=True,
            failure_class="empty_shell",
            confidence=0.85,
            recommended_action="retry_with_recovery",
            user_message="Page appears structurally empty.",
            operator_hint="DOM exists but no data containers found.",
        ),
    )

    assert sar.html == html
    assert sar.extraction_method == "regex"
    assert sar.zero_result_classification is not None
    assert sar.zero_result_classification.failure_class == "empty_shell"
    assert sar.zero_result_classification.recommended_action == "retry_with_recovery"


def test_scrape_attempt_result_html_none() -> None:
    """When fetch fails, html is None but result still functions."""
    sar = ScrapeAttemptResult([], html=None, telemetry={"error": "timeout"})
    assert sar.html is None
    assert sar.telemetry["error"] == "timeout"


# ── 3. Zero-record classification ────────────────────────────────────


def test_zero_result_classification_preserved() -> None:
    """Zero-result classification metadata is preserved on the result."""
    classification = ZeroResultClassification(
        zero_result=True,
        failure_class="anti_bot_block",
        confidence=0.92,
        recommended_action="use_authorized_access_or_retry_later",
        user_message="Blocked by anti-bot",
        operator_hint="Captcha challenge detected.",
    )
    sar = ScrapeAttemptResult(
        [],
        html="<html><body>challenge</body></html>",
        extraction_method="playwright_stealth",
        zero_result_classification=classification,
        anti_bot_score=0.91,
        recommended_next_action="use_authorized_access_or_retry_later",
        warnings=["captcha detected"],
    )

    assert sar.zero_result_classification.failure_class == "anti_bot_block"
    assert sar.zero_result_classification.confidence == 0.92
    assert sar.anti_bot_score == 0.91
    assert sar.recommended_next_action == "use_authorized_access_or_retry_later"
    assert "captcha detected" in sar.warnings


def test_zero_result_classification_none() -> None:
    """When no zero-result classification, the field is None."""
    sar = ScrapeAttemptResult([{"name": "Acme"}], html="<html>ok</html>")
    assert sar.zero_result_classification is None


def test_zero_result_classification_empty_shell() -> None:
    """Empty shell classification is preserved with evidence scores."""
    classification = ZeroResultClassification(
        zero_result=True,
        failure_class="empty_shell",
        confidence=0.75,
        recommended_action="try_alternate_source",
        user_message="No data containers found.",
        operator_hint="DOM parsed but no candidate containers detected.",
    )
    sar = ScrapeAttemptResult(
        [],
        html="<html><body><p>No results found</p></body></html>",
        extraction_method="container_discovery",
        zero_result_classification=classification,
        data_evidence_score=0.05,
        recommended_next_action="try_alternate_source",
    )

    assert sar.zero_result_classification.failure_class == "empty_shell"
    assert sar.data_evidence_score == 0.05
    assert sar.recommended_next_action == "try_alternate_source"


# ── 4. Anti-bot lineage ──────────────────────────────────────────────


def test_anti_bot_lineage_preserved() -> None:
    """Anti-bot detection scores and fetch method propagate through result."""
    sar = ScrapeAttemptResult(
        [],
        html="<html><body>blocked page</body></html>",
        final_url="https://example.com/blocked",
        fetch_method="playwright_stealth",
        extraction_method="playwright_stealth",
        anti_bot_score=0.87,
        data_evidence_score=0.0,
        recommended_next_action="use_authorized_access_or_retry_later",
        warnings=["possible captcha"],
        zero_result_classification=ZeroResultClassification(
            zero_result=True,
            failure_class="anti_bot_block",
            confidence=0.88,
            recommended_action="use_authorized_access_or_retry_later",
            user_message="Blocked by anti-bot measures.",
            operator_hint="High anti-bot score detected.",
        ),
    )

    assert sar.final_url == "https://example.com/blocked"
    assert sar.fetch_method == "playwright_stealth"
    assert sar.anti_bot_score == 0.87
    assert sar.data_evidence_score == 0.0
    assert sar.warnings == ["possible captcha"]


# ── 5. to_telemetry_dict ─────────────────────────────────────────────


def test_to_telemetry_dict() -> None:
    """to_telemetry_dict produces a flat diagnostic dict."""
    sar = ScrapeAttemptResult(
        [{"name": "A"}, {"name": "B"}],
        html="<html><body>AB</body></html>",
        final_url="https://example.com/list",
        fetch_method="playwright_full",
        extraction_method="memory",
        anti_bot_score=0.12,
        data_evidence_score=0.9,
        recommended_next_action="",
        warnings=["slow JS render"],
    )

    d = sar.to_telemetry_dict()
    assert d["records"] == 2
    assert d["html_length"] == len("<html><body>AB</body></html>")
    assert d["final_url"] == "https://example.com/list"
    assert d["fetch_method"] == "playwright_full"
    assert d["extraction_method"] == "memory"
    assert d["anti_bot_score"] == 0.12
    assert d["data_evidence_score"] == 0.9
    assert d["zero_result_classification"] is None
    assert d["warnings"] == ["slow JS render"]


def test_to_telemetry_dict_zero_result() -> None:
    """to_telemetry_dict includes zero-result classification when present."""
    sar = ScrapeAttemptResult(
        [],
        html="<html></html>",
        zero_result_classification=ZeroResultClassification(
            zero_result=True,
            failure_class="empty_response",
            confidence=0.95,
            recommended_action="retry_with_recovery",
            user_message="Empty page.",
            operator_hint="HTTP 200 but empty body.",
        ),
    )

    d = sar.to_telemetry_dict()
    assert d["records"] == 0
    assert d["zero_result_classification"]["failure_class"] == "empty_response"
    assert d["zero_result_classification"]["confidence"] == 0.95


# ── 6. scrape_url_attempt — mock-based integration tests ─────────────


@pytest.mark.asyncio
async def test_scrape_url_attempt_returns_rich_result(monkeypatch) -> None:
    """scrape_url_attempt returns a ScrapeAttemptResult with lineage."""
    from app import scraper

    async def fake_fetch(*args, **kwargs):
        return "<html><body><h1>Data</h1></body></html>", 0.0, "playwright_full", 0

    class FakeExtractionResult:
        records = [{"company_name": "Acme", "record_score": 0.95}]
        method = "memory"
        selector_success = True
        selectors: dict = {"fields": {}}

    async def fake_orchestrate(*args, **kwargs):
        return FakeExtractionResult()

    async def fake_profile(*args, **kwargs):
        return None

    monkeypatch.setattr(scraper, "get_crawl_policy", lambda: _AllowAllCrawlPolicy())
    monkeypatch.setattr(scraper, "match_profile_for_url", lambda url: None)
    monkeypatch.setattr(scraper, "try_profile_extraction", fake_profile)
    monkeypatch.setattr(scraper, "fetch_page_content", fake_fetch)
    monkeypatch.setattr(scraper, "orchestrate_extraction", fake_orchestrate)

    class FakeTelemetry:
        def record(self, **kw):
            pass

    class FakeFrontier:
        async def add_discovered_links(self, links, source_url, source_depth=0):
            return 0

    monkeypatch.setattr(scraper, "get_scrape_telemetry", lambda: FakeTelemetry())
    monkeypatch.setattr(scraper, "get_crawl_frontier", lambda: FakeFrontier())
    monkeypatch.setattr(scraper, "detect_anti_bot", lambda html: 0.0)
    monkeypatch.setattr(scraper, "estimate_dom_nodes", lambda html: 1)
    monkeypatch.setattr(scraper, "collect_page_evidence", lambda *a, **kw: None)
    monkeypatch.setattr(scraper, "classify_zero_result", lambda **kw: None)
    monkeypatch.setattr(scraper, "classify_failure", lambda **kw: None)

    def fake_process(records, schema_fields, min_record_score, **kw):
        return records

    monkeypatch.setattr(scraper, "process_raw_records", fake_process)
    monkeypatch.setattr(scraper, "_boost_contacts_with_page_html", lambda r, h, s: r)
    monkeypatch.setattr(scraper, "_limit_source_records", lambda r, s: r)

    result = await scrape_url_attempt(
        "https://example.com/test",
        [],
    )

    assert isinstance(result, ScrapeAttemptResult)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["company_name"] == "Acme"
    assert result.html is not None
    assert result.final_url == "https://example.com/test"
    assert result.fetch_method is not None
    assert result.acquisition_lineage is not None
    assert result.acquisition_lineage["original_url"] == "https://example.com/test"
    assert "anti_bot_score" in result.acquisition_lineage
    assert "data_evidence_score" in result.acquisition_lineage


@pytest.mark.asyncio
async def test_scrape_url_attempt_handles_monkeypatched_plain_list(monkeypatch) -> None:
    """scrape_url_attempt gracefully handles when scrape_url returns a plain list."""
    from app import scraper

    # Directly monkeypatch scrape_url to return a plain list
    async def fake_scrape_url(*args, **kwargs):
        return [{"company_name": "Monkey"}]

    monkeypatch.setattr(scraper, "scrape_url", fake_scrape_url)

    result = await scrape_url_attempt(
        "https://example.com/monkey",
        [],
    )

    assert isinstance(result, ScrapeAttemptResult)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["company_name"] == "Monkey"
    # Default metadata should be present
    assert result.html is None
    assert result.anti_bot_score == 0.0
    assert result.data_evidence_score == 0.0
    assert result.warnings == []
    # Lineage should still be built
    assert result.acquisition_lineage is not None
    assert result.acquisition_lineage["original_url"] == "https://example.com/monkey"


@pytest.mark.asyncio
async def test_scrape_url_attempt_zero_result_with_html(monkeypatch) -> None:
    """scrape_url_attempt preserves HTML and classification in zero-record case."""
    from app import scraper

    async def fake_fetch(*args, **kwargs):
        return "<html><body>No results found</body></html>", 0.0, "playwright_full", 0

    class FakeExtractionResult:
        records: list = []
        method: str = "regex"
        selector_success: bool = False
        selectors: dict = {"fields": {}}

    async def fake_orchestrate(*args, **kwargs):
        return FakeExtractionResult()

    async def fake_profile(*args, **kwargs):
        return None

    monkeypatch.setattr(scraper, "get_crawl_policy", lambda: _AllowAllCrawlPolicy())
    monkeypatch.setattr(scraper, "match_profile_for_url", lambda url: None)
    monkeypatch.setattr(scraper, "try_profile_extraction", fake_profile)
    monkeypatch.setattr(scraper, "fetch_page_content", fake_fetch)
    monkeypatch.setattr(scraper, "orchestrate_extraction", fake_orchestrate)

    class FakeTelemetry:
        def record(self, **kw):
            pass

    class FakeFrontier:
        async def add_discovered_links(self, links, source_url, source_depth=0):
            return 0

    class FakeEvidence:
        forms: str | None = None
        candidate_containers: list = []

    monkeypatch.setattr(scraper, "get_scrape_telemetry", lambda: FakeTelemetry())
    monkeypatch.setattr(scraper, "get_crawl_frontier", lambda: FakeFrontier())
    monkeypatch.setattr(scraper, "collect_page_evidence", lambda *a, **kw: FakeEvidence())
    monkeypatch.setattr(scraper, "detect_anti_bot", lambda html: 0.05)
    monkeypatch.setattr(scraper, "estimate_dom_nodes", lambda html: 10)
    monkeypatch.setattr(
        scraper,
        "classify_zero_result",
        lambda **kw: ZeroResultClassification(
            zero_result=True,
            failure_class="empty_shell",
            confidence=0.75,
            recommended_action="try_alternate_source",
            user_message="No data containers found.",
            operator_hint="DOM parsed but empty.",
        ),
    )
    monkeypatch.setattr(scraper, "classify_failure", lambda **kw: None)

    def fake_process(records, schema_fields, min_record_score, **kw):
        return records

    monkeypatch.setattr(scraper, "process_raw_records", fake_process)
    monkeypatch.setattr(scraper, "_boost_contacts_with_page_html", lambda r, h, s: r)
    monkeypatch.setattr(scraper, "_limit_source_records", lambda r, s: r)

    result = await scrape_url_attempt(
        "https://example.com/zero",
        [],
    )

    assert len(result) == 0
    assert result.html is not None
    assert result.zero_result_classification is not None
    assert result.zero_result_classification.failure_class == "empty_shell"
    assert result.acquisition_lineage is not None
    assert result.acquisition_lineage["original_url"] == "https://example.com/zero"
    assert result.acquisition_lineage["records"] == 0


# ── 7. Edge cases ────────────────────────────────────────────────────


def test_warnings_defaults_to_empty_list() -> None:
    """Warnings default to [] when not provided."""
    sar = ScrapeAttemptResult([], html="<html></html>")
    assert sar.warnings == []


def test_warnings_explicitly_provided() -> None:
    """Warnings are preserved when explicitly provided."""
    sar = ScrapeAttemptResult([], html="<html></html>", warnings=["timeout", "retry"])
    assert sar.warnings == ["timeout", "retry"]


def test_scores_default_to_zero() -> None:
    """anti_bot_score and data_evidence_score default to 0.0."""
    sar = ScrapeAttemptResult([{"name": "X"}])
    assert sar.anti_bot_score == 0.0
    assert sar.data_evidence_score == 0.0


def test_recommended_next_action_defaults_to_empty() -> None:
    """recommended_next_action defaults to empty string."""
    sar = ScrapeAttemptResult([])
    assert sar.recommended_next_action == ""


def test_multiple_zero_results_with_different_classifications() -> None:
    """Different failure classes are properly represented."""
    classifications = [
        ("anti_bot_block", "use_authorized_access_or_retry_later"),
        ("empty_response", "retry_with_recovery"),
        ("empty_shell", "try_alternate_source"),
        ("session_bound_url", "replay_with_session"),
        ("js_render_required", "retry_with_js_render"),
    ]

    for failure_class, recommended_action in classifications:
        sar = ScrapeAttemptResult(
            [],
            html="<html></html>",
            zero_result_classification=ZeroResultClassification(
                zero_result=True,
                failure_class=failure_class,
                confidence=0.8,
                recommended_action=recommended_action,
                user_message="Test",
                operator_hint="Test hint",
            ),
            recommended_next_action=recommended_action,
        )

        assert sar.zero_result_classification.failure_class == failure_class
        assert sar.recommended_next_action == recommended_action
