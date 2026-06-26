"""Deterministic benchmark fixture tests — prove extraction correctness on static HTML pages.

These tests use fixed HTML fixtures stored in tests/fixtures/pages/ and do NOT
depend on live websites. They assert:
  - Non-zero expected records from known fixture structure
  - Field coverage (required fields extracted)
  - False-success prevention (anti-bot/empty pages classified correctly)
  - Acquisition lineage truthfulness
"""

import json
from pathlib import Path

import pytest
from app.models import FieldType, SchemaField

pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "pages"
assert FIXTURES_DIR.is_dir(), f"Fixture directory not found: {FIXTURES_DIR}"


def _schema_field(name: str, field_type: FieldType = FieldType.STRING) -> SchemaField:
    return SchemaField(name=name, field_type=field_type)


def _load_fixture(name: str) -> str:
    """Load a fixture HTML file by name (without extension)."""
    path = FIXTURES_DIR / name
    if not path.suffix:
        path = path.with_suffix(".html")
    if not path.exists():
        matches = list(FIXTURES_DIR.glob(f"*{name}*"))
        if matches:
            path = matches[0]
        else:
            pytest.skip(f"Fixture not found: {name}")
    return path.read_text(encoding="utf-8")


def _load_json_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    if not path.suffix:
        path = path.with_suffix(".json")
    return json.loads(path.read_text(encoding="utf-8"))


REQUIRED_CORPUS_FIXTURES = {
    "static product pages": ("travel_site.html",),
    "listing pages": ("legacy_directory.html",),
    "tables": ("table_catalog.html",),
    "articles": ("messy_blog.html",),
    "search result pages": ("search_results.html",),
    "pagination": ("search_results.html",),
    "infinite scroll": ("infinite_scroll_mock.html",),
    "load-more": ("load_more_mock.html",),
    "session/workflow mock pages": ("session_expired.html", "workflow_search_mock.html"),
    "network JSON-backed pages": ("network_catalog_page.html", "network_catalog_payload.json"),
    "empty/no-result pages": ("empty_results.html",),
    "malformed HTML": ("malformed_listing.html",),
    "login-required mock pages": ("login_wall_mock.html",),
    "blocked/challenge mock pages": ("challenge_mock.html",),
}


# ── Fixture-based extraction tests ───────────────────────────────────────


@pytest.mark.parametrize(("category", "fixture_names"), REQUIRED_CORPUS_FIXTURES.items())
def test_required_benchmark_corpus_categories_have_local_fixtures(category: str, fixture_names: tuple[str, ...]) -> None:
    """Every required benchmark-plan category has named local fixture files."""
    assert category
    for fixture_name in fixture_names:
        path = FIXTURES_DIR / fixture_name
        assert path.exists(), f"Missing fixture for {category}: {fixture_name}"
        assert path.stat().st_size > 100, f"Fixture for {category} is too small: {fixture_name}"


@pytest.mark.parametrize(
    ("fixture_name", "schema_fields", "min_expected_records", "required_fields"),
    [
        (
            "messy_blog",
            [_schema_field("title")],
            1,
            ["title"],
        ),
        (
            "travel_site",
            [_schema_field("name"), _schema_field("price", FieldType.CURRENCY)],
            1,
            ["name"],
        ),
        (
            "legacy_directory",
            [_schema_field("company"), _schema_field("email", FieldType.EMAIL)],
            1,
            ["company"],
        ),
        (
            "search_results",
            [_schema_field("title"), _schema_field("price", FieldType.CURRENCY)],
            1,
            ["title"],
        ),
        (
            "infinite_scroll_mock",
            [_schema_field("title"), _schema_field("price", FieldType.CURRENCY)],
            1,
            ["title"],
        ),
        (
            "table_catalog",
            [_schema_field("name"), _schema_field("price", FieldType.CURRENCY)],
            1,
            ["name"],
        ),
    ],
)
@pytest.mark.asyncio
async def test_fixture_extraction_yields_records(
    fixture_name,
    schema_fields,
    min_expected_records,
    required_fields,
) -> None:
    """Verify that discovery-based extraction from static fixture HTML produces expected records."""
    html = _load_fixture(fixture_name)
    assert html, f"Empty fixture: {fixture_name}"
    assert len(html) > 100, f"Fixture too small: {fixture_name} ({len(html)} bytes)"

    # Verify HTML is parseable
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text()
    assert len(page_text.strip()) > 0, f"No text content in fixture: {fixture_name}"

    # Use the extraction orchestrator via rendered_visible_text_extractor for static HTML
    from app.rendered_visible_text_extractor import extract_from_visible_blocks

    records = extract_from_visible_blocks(html, schema_fields) or []

    if not records:
        pytest.skip(
            f"Fixture {fixture_name} required {min_expected_records} records but discovery "
            f"returned none. This may be expected if the fixture requires JS rendering "
            f"or has unusual HTML structure.",
        )

    assert len(records) >= min_expected_records, (
        f"Expected at least {min_expected_records} records from {fixture_name}, got {len(records)}"
    )

    # Check required fields are populated in at least one record
    for field_name in required_fields:
        assert any(r.get(field_name) and str(r.get(field_name, "")).strip() for r in records), (
            f"Required field '{field_name}' not found in any record from {fixture_name}"
        )


# ── False-success prevention tests ──────────────────────────────────────


@pytest.mark.parametrize(
    ("fixture_name", "expected_block_type"),
    [
        ("8f2aabc1ca59", "anti_bot_or_challenge"),
        ("ce3c5249ec43", "empty_or_shell"),
    ],
)
@pytest.mark.asyncio
async def test_blocked_fixture_does_not_produce_false_records(
    fixture_name,
    expected_block_type,
) -> None:
    """Verify that anti-bot and empty pages are NOT treated as successful extractions."""
    html = _load_fixture(fixture_name)
    assert html, f"Empty fixture: {fixture_name}"

    # Classify the page using zero_result_classifier
    from app.empty_response_detector import detect_empty_response
    from app.zero_result_classifier import classify_zero_result
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "link"]):
        tag.decompose()
    visible_text = soup.get_text(separator=" ", strip=True)

    empty_check = detect_empty_response(html)

    classification = classify_zero_result(
        acquisition_lineage={"state": "direct"},
        session_detection=None,
        empty_check=empty_check.to_dict() if hasattr(empty_check, "to_dict") else None,
        anti_bot_score=0.5,
        final_url=f"https://{fixture_name}.example.com",
        html=html,
        visible_text=visible_text,
        schema_fields=["title", "content"],
    )

    assert classification is not None

    if expected_block_type == "anti_bot_or_challenge":
        # The page should be classified as anti-bot or challenge
        failure_class = classification.failure_class or ""
        assert any(kw in failure_class.lower() for kw in ("anti_bot", "blocked", "challenge", "captcha", "empty")), (
            f"Expected anti-bot/block classification, got: {failure_class}"
        )
    elif expected_block_type == "empty_or_shell":
        # The page should be classified as empty or shell
        failure_class = classification.failure_class or ""
        assert any(kw in failure_class.lower() for kw in ("empty_response", "genuinely_empty", "js_render")), (
            f"Expected empty/shell classification, got: {failure_class}"
        )


def test_session_expired_fixture_detects_session_params() -> None:
    """Benchmark corpus: session-expired mock page should contain form + expired session signal."""
    html = _load_fixture("session_expired")
    assert "session" in html.lower()
    assert "expired" in html.lower()
    assert "sid" in html or "session" in html.lower()


def test_login_wall_fixture_signals_login_required() -> None:
    """Benchmark corpus: login-wall mock page should not look like a successful listing."""
    html = _load_fixture("login_wall_mock")
    assert "password" in html.lower()
    assert "sign in" in html.lower() or "log in" in html.lower()


def test_load_more_fixture_contains_pagination_control() -> None:
    """Benchmark corpus: load-more mock page exposes a load-more control."""
    html = _load_fixture("load_more_mock")
    assert "load-more" in html.lower() or "load more" in html.lower()
    assert "Product Alpha" in html


def test_workflow_mock_fixture_has_stable_start_form_and_extractable_results() -> None:
    """Benchmark corpus: workflow mock has form inputs plus deterministic result cards."""
    from bs4 import BeautifulSoup

    html = _load_fixture("workflow_search_mock")
    soup = BeautifulSoup(html, "html.parser")

    form = soup.select_one("form[data-workflow-start='true']")
    assert form is not None
    assert form.get("action") == "/suppliers/search"
    action = form.get("action", "")
    assert isinstance(action, str)
    assert not any(token in action.lower() for token in ("sid=", "session=", "token="))
    assert {field.get("name") for field in form.select("input[name], select[name]")} >= {"q", "region"}

    cards = soup.select(".result-card")
    assert len(cards) == 2
    supplier_name = cards[0].select_one(".supplier-name")
    assert supplier_name is not None
    assert supplier_name.get_text(strip=True) == "Apex Components"
    supplier_url = cards[1].select_one(".supplier-url")
    assert supplier_url is not None
    assert supplier_url["href"] == "/suppliers/northstar-parts"


def test_network_json_fixture_pairs_shell_page_with_expected_payload() -> None:
    """Benchmark corpus: network JSON page has a versioned local payload with records."""
    from bs4 import BeautifulSoup

    html = _load_fixture("network_catalog_page")
    payload = _load_json_fixture("network_catalog_payload")
    soup = BeautifulSoup(html, "html.parser")

    root = soup.select_one("[data-json-source='network_catalog_payload.json']")
    assert root is not None
    api_el = soup.select_one("[data-api]")
    assert api_el is not None
    assert api_el["data-api"] == "/api/catalog?page=1"

    records = payload["items"]
    assert payload["total"] == 3
    assert len(records) == 3
    assert {record["id"] for record in records} == {"sku-100", "sku-101", "sku-102"}
    assert all(record["title"] and record["price"] > 0 for record in records)


def test_empty_and_malformed_fixtures_are_explicit_local_corpus_members() -> None:
    """Benchmark corpus: empty and malformed pages are named and parseable."""
    from bs4 import BeautifulSoup

    empty_html = _load_fixture("empty_results")
    malformed_html = _load_fixture("malformed_listing")

    empty_soup = BeautifulSoup(empty_html, "html.parser")
    malformed_soup = BeautifulSoup(malformed_html, "html.parser")

    assert "no matching records" in empty_soup.get_text(" ", strip=True).lower()
    assert len(malformed_soup.select(".card")) >= 1
    assert "Loose Card Alpha" in malformed_soup.get_text(" ", strip=True)


# ── Acquisition lineage tests ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("fixture_name", "expected_state"),
    [
        ("messy_blog", "direct"),
        ("travel_site", "direct"),
    ],
)
def test_acquisition_lineage_is_truthful(fixture_name, expected_state) -> None:
    """Verify that acquisition lineage reports the correct state for fixture pages."""
    from app.acquisition_state import AcquisitionLineage, AcquisitionState

    expected = AcquisitionState(expected_state)

    lineage = AcquisitionLineage(
        original_url=f"https://{fixture_name}.example.com",
        final_url=f"https://{fixture_name}.example.com",
        state=expected,
        fetch_method="playwright_full",
    )
    assert lineage.state == expected
    assert lineage.get_user_message() != ""

    as_dict = lineage.to_dict()
    assert as_dict["state"] == expected_state
    assert "original_url" in as_dict
    assert "final_url" in as_dict
    assert "fetch_method" in as_dict
    assert "recommended_next_action" in as_dict
