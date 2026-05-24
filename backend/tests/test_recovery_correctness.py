"""Regression tests for recovery flag and acquisition-lineage correctness."""

import pytest

from app.acquisition_state import AcquisitionLineage, AcquisitionState
from app.models import FieldType, JobCreate, SchemaField
from app.recovery_strategies import AttemptContext


class _AllowAllCrawlPolicy:
    async def check_domain(self, url):
        return None

    def record_result(self, url, success=True):
        return None


@pytest.mark.asyncio
async def test_attempt_context_does_not_skip_profiles_by_default(monkeypatch):
    from app import scraper

    called = {"profile": 0, "fetch": 0}

    async def fake_profile(url, max_wait=None):
        called["profile"] += 1
        return [{"company_name": "Acme Studio"}]

    def fake_process(records, schema_fields, min_record_score, **kwargs):
        return [{"company_name": records[0]["company_name"], "record_score": 0.95}]

    async def fake_fetch(*args, **kwargs):
        called["fetch"] += 1
        return "<html></html>", 0.0, "playwright_full", 0

    monkeypatch.setattr(scraper, "get_crawl_policy", lambda: _AllowAllCrawlPolicy())
    monkeypatch.setattr(scraper, "match_profile_for_url", lambda url: {"fields": {"company_name": ".name"}})
    monkeypatch.setattr(scraper, "try_profile_extraction", fake_profile)
    monkeypatch.setattr(scraper, "process_raw_records", fake_process)
    monkeypatch.setattr(scraper, "fetch_page_content", fake_fetch)

    results = await scraper.scrape_url(
        "https://example.com/list",
        [SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        attempt_ctx=AttemptContext(),
    )

    assert called["profile"] == 1
    assert called["fetch"] == 0
    assert results[0]["company_name"] == "Acme Studio"


@pytest.mark.asyncio
async def test_force_llm_discovery_skips_profiles_and_passes_recovery_flags(monkeypatch):
    from app import scraper
    from app.extraction_orchestrator import ExtractionResult

    called = {"profile": 0, "provided_selectors": None}

    async def fake_profile(url, max_wait=None):
        called["profile"] += 1
        return [{"company_name": "Should Not Use"}]

    async def fake_fetch(*args, **kwargs):
        return "<html><body>fallback</body></html>", 0.0, "playwright_full", 0

    async def fake_orchestrate(*args, **kwargs):
        called["provided_selectors"] = kwargs.get("provided_selectors")
        return ExtractionResult([], "regex")

    monkeypatch.setattr(scraper, "get_crawl_policy", lambda: _AllowAllCrawlPolicy())
    monkeypatch.setattr(scraper, "try_profile_extraction", fake_profile)
    monkeypatch.setattr(scraper, "fetch_page_content", fake_fetch)
    monkeypatch.setattr(scraper, "orchestrate_extraction", fake_orchestrate)

    ctx = AttemptContext(force_llm_discovery=True, bypass_selector_memory=True, force_container_discovery=True)
    await scraper.scrape_url(
        "https://example.com/list",
        [SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        attempt_ctx=ctx,
    )

    assert called["profile"] == 0
    assert called["provided_selectors"]["force_llm_discovery"] is True
    assert called["provided_selectors"]["bypass_selector_memory"] is True
    assert called["provided_selectors"]["force_container_discovery"] is True


def test_acquisition_lineage_to_dict_contains_quality_and_action_fields():
    lineage = AcquisitionLineage(
        original_url="https://example.com/old",
        final_url="https://example.com/new",
        state=AcquisitionState.ANTI_BOT_BLOCKED,
        fetch_method="playwright_stealth",
        recovery_method="rotate_proxy",
        recovered_url="https://example.com/new",
        session_bound=False,
        ephemeral_params=["sid"],
        data_evidence_score=0.2,
        network_payloads_found=3,
        forms_detected=1,
        containers_detected=2,
        anti_bot_score=0.91,
        visible_text_length=42,
        recommended_next_action="use_authorized_access_or_retry_later",
    )

    data = lineage.to_dict()

    assert data["state"] == "anti_bot_blocked"
    assert data["fetch_method"] == "playwright_stealth"
    assert data["recovery_method"] == "rotate_proxy"
    assert data["recovered_url"] == "https://example.com/new"
    assert data["ephemeral_params"] == ["sid"]
    assert data["data_evidence_score"] == 0.2
    assert data["network_payloads_found"] == 3
    assert data["recommended_next_action"] == "use_authorized_access_or_retry_later"


@pytest.mark.asyncio
async def test_failed_lineage_uses_computed_anti_bot_state(monkeypatch):
    import app.scraper_recovery_integration as recovery

    async def fake_scrape_url(*args, **kwargs):
        raise RuntimeError("captcha challenge blocked")

    monkeypatch.setattr("app.scraper.scrape_url", fake_scrape_url)

    _results, stats = await recovery.scrape_url_with_recovery(
        "https://blocked.example/list",
        [SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        max_recovery_attempts=1,
    )

    lineage = stats["acquisition_lineage"]
    assert lineage["state"] == "anti_bot_blocked"
    assert lineage["session_bound"] is False
    assert lineage["recommended_next_action"] == "use_authorized_access_or_retry_later"


@pytest.mark.asyncio
async def test_skip_url_stops_recovery_loop(monkeypatch):
    import app.scraper_recovery_integration as recovery

    async def fake_scrape_url(*args, **kwargs):
        return []

    class FakeExecutor:
        async def execute(self, plan, context, attempt_ctx=None):
            attempt_ctx.skip_url = True
            return True

    monkeypatch.setattr("app.scraper.scrape_url", fake_scrape_url)
    monkeypatch.setattr(recovery, "get_recovery_executor", lambda: FakeExecutor())

    _results, stats = await recovery.scrape_url_with_recovery(
        "https://example.com/empty",
        [SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        max_recovery_attempts=3,
    )

    assert stats["attempts"] == 1
    assert stats["recovery_attempts"] == 1
    assert stats["final_failure_category"] == "skipped_url"


@pytest.mark.asyncio
async def test_extra_headers_and_timeout_passed_to_httpx(monkeypatch):
    from app import html_utils
    from app.strategy_evolution import FetchStrategy

    captured = {}

    async def fake_httpx(url, strategy=FetchStrategy.HTTPX_BASIC, extra_headers=None, timeout_ms=None):
        captured["extra_headers"] = extra_headers
        captured["timeout_ms"] = timeout_ms
        return "<html>ok</html>", 0.0, strategy.value, 0

    monkeypatch.setattr(html_utils, "_fetch_with_httpx", fake_httpx)

    await html_utils.fetch_page_content(
        "https://example.com",
        preferred_method=FetchStrategy.HTTPX_BASIC,
        timeout_ms=1234,
        extra_headers={"X-Test": "1"},
    )

    assert captured["extra_headers"] == {"X-Test": "1"}
    assert captured["timeout_ms"] == 1234


@pytest.mark.asyncio
async def test_force_container_discovery_skips_llm_and_memory(monkeypatch):
    from app import extraction_orchestrator as orchestrator

    called = {"discover": 0, "memory": 0, "container": 0}

    class FakeMemory:
        def get_selectors(self, url):
            called["memory"] += 1
            return {"item_container": ".cached", "fields": {"company_name": ".name"}}

    class FakeContainerResult:
        all_passed = True
        final_records = [{"company_name": "Container Studio", "record_score": 0.95}]
        total_records = 1
        best_selector = ".card"

    async def fake_discover(*args, **kwargs):
        called["discover"] += 1
        return {"item_container": ".llm", "fields": {"company_name": ".name"}}

    async def fake_container(*args, **kwargs):
        called["container"] += 1
        return FakeContainerResult()

    monkeypatch.setattr(orchestrator, "get_selector_memory", lambda: FakeMemory())
    monkeypatch.setattr(orchestrator, "discover_selectors", fake_discover)
    monkeypatch.setattr(orchestrator, "extract_from_network", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, "multi_pass_container_extraction", fake_container)

    result = await orchestrator.orchestrate_extraction(
        "https://example.com/list",
        "<html><body><div class='card'>Container Studio</div></body></html>",
        [SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
        min_record_score=0.35,
        provided_selectors={"force_container_discovery": True},
    )

    assert result.method == "container_discovery"
    assert called == {"discover": 0, "memory": 0, "container": 1}


def test_selectors_map_rejects_malformed_shapes():
    payload = {
        "name": "bad selectors",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
        "selectors_map": {"item_container": 123, "fields": "not a dict"},
    }

    with pytest.raises(Exception):
        JobCreate.model_validate(payload)


def test_schema_rejects_runtime_metadata_field_names():
    with pytest.raises(Exception):
        SchemaField(name="record_score", field_type=FieldType.FLOAT)


@pytest.mark.asyncio
async def test_crawl_policy_active_counter_never_leaks_on_fetch_failure(monkeypatch):
    from app import scraper
    from app.crawl_policy import get_crawl_policy
    
    # Get active crawl policy and reset it
    policy = get_crawl_policy()
    policy.reset_domain("https://example.com/fail-fetch")
    
    # Assert initial state
    assert policy._domains["example.com"].active_fetches == 0
    
    # Simulate fetch throwing an exception
    async def fake_fetch(*args, **kwargs):
        raise RuntimeError("simulated fetch crash")
        
    monkeypatch.setattr(scraper, "fetch_page_content", fake_fetch)
    
    # Call scrape_url (should handle error and return [])
    results = await scraper.scrape_url(
        "https://example.com/fail-fetch",
        [SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
    )
    
    assert results == []
    # Assert counter decremented back to 0!
    assert policy._domains["example.com"].active_fetches == 0


@pytest.mark.asyncio
async def test_scrape_attempt_result_exposes_html_and_telemetry(monkeypatch):
    from app import scraper
    from app.crawl_policy import get_crawl_policy
    
    # Reset domain crawl pacing to prevent blocks
    policy = get_crawl_policy()
    policy.reset_domain("https://unique-subclass.example.com/")
    
    async def fake_fetch(*args, **kwargs):
        return "<html><body><h1>Example</h1></body></html>", "playwright_full", 123.0, 0.0
        
    monkeypatch.setattr(scraper, "fetch_page_content", fake_fetch)
    
    results = await scraper.scrape_url(
        "https://unique-subclass.example.com/test-result-subclass",
        [SchemaField(name="company_name", field_type=FieldType.STRING, required=True)],
    )
    
    # Assert result is indeed a list subclass with extra metadata
    assert isinstance(results, list)
    assert hasattr(results, "html")
    assert results.html == "<html><body><h1>Example</h1></body></html>"
    assert hasattr(results, "telemetry")
    assert results.telemetry is not None
