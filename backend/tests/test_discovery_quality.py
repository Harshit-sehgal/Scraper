from app.discovery import (
    _build_search_query,
    _canonicalize_url,
    _contact_fields_requested,
    _extract_domain,
    _has_query_signal,
    _looks_noisy_url,
    _score_result,
    _source_allowed,
    _source_bonus,
)
from app.models import SourcePolicy


def test_looks_noisy_url_blocks_configured_dead_domain() -> None:
    assert _looks_noisy_url("https://quickfinds.org/listing/top-10-interior-design-company-in-chennai") is True


def test_looks_noisy_url_blocks_pdf() -> None:
    assert _looks_noisy_url("https://example.com/report.pdf") is True


def test_looks_noisy_url_blocks_login_pages() -> None:
    assert _looks_noisy_url("https://example.com/login") is True
    assert _looks_noisy_url("https://example.com/signin") is True
    assert _looks_noisy_url("https://example.com/privacy") is True


def test_looks_noisy_url_allows_clean_urls() -> None:
    assert _looks_noisy_url("https://example.com/companies/interior-design") is False


def test_looks_noisy_url_rejects_non_http() -> None:
    assert _looks_noisy_url("ftp://example.com/file") is True
    assert _looks_noisy_url("") is True


def test_extract_domain_strips_www() -> None:
    assert _extract_domain("https://www.example.com/page") == "example.com"


def test_extract_domain_handles_subdomains() -> None:
    assert _extract_domain("https://sub.domain.co.uk/page") == "sub.domain.co.uk"


def test_extract_domain_returns_empty_for_invalid() -> None:
    assert _extract_domain("") == ""
    assert _extract_domain("not-a-url") == ""


def test_contact_fields_requested_detects_phone() -> None:
    assert _contact_fields_requested(["company_name", "phone"]) is True


def test_contact_fields_requested_detects_email() -> None:
    assert _contact_fields_requested(["email"]) is True


def test_contact_fields_requested_negative() -> None:
    assert _contact_fields_requested(["company_name", "address"]) is False


def test_contact_fields_requested_empty() -> None:
    assert _contact_fields_requested([]) is False


def test_source_bonus_returns_correct_values() -> None:
    assert _source_bonus("official") > _source_bonus("directory")
    assert _source_bonus("directory") > _source_bonus("search_result")
    assert _source_bonus("unknown") == 0.0


def test_has_query_signal_detects_terms() -> None:
    blob = "interior designers in Chennai list of top designers"
    assert _has_query_signal("interior designers chennai", blob) is True


def test_has_query_signal_negative_for_unrelated() -> None:
    blob = "car repair shop engine maintenance"
    assert _has_query_signal("interior designers chennai", blob) is False


def test_has_query_signal_requires_multiple_terms() -> None:
    blob = "interior designers in Chennai directory listing"
    assert _has_query_signal("interior designers chennai", blob) is True
    assert _has_query_signal("plumbers", blob) is False


def test_score_result_penalizes_noisy_urls() -> None:
    item_noisy = {"title": "test", "body": "test", "href": "https://example.com/login"}
    item_clean = {"title": "test", "body": "test", "href": "https://example.com/companies"}
    noisy_score = _score_result(item_noisy, "test", "", [], "search_result")
    clean_score = _score_result(item_clean, "test", "", [], "search_result")
    assert clean_score > noisy_score


def test_score_result_with_listing_hints() -> None:
    item = {"title": "Top 10 Best Interior Designers", "body": "directory and listing", "href": "https://example.com/directory"}
    score = _score_result(item, "interior designers", "", ["company_name"], "search_result")
    assert score > 0.3


def test_score_result_penalizes_social_sharer_urls() -> None:
    item = {"title": "test", "body": "test", "href": "https://facebook.com/sharer"}
    score = _score_result(item, "test", "", [], "search_result")
    assert score <= 0.0


def test_build_search_query_basic() -> None:
    result = _build_search_query(query="interior designers", location="Chennai",
                                  domain="", data_fields=[], origin_location="", max_distance_km=None)
    assert "interior designers" in result
    assert "Chennai" in result


def test_build_search_query_with_domain() -> None:
    result = _build_search_query(query="plumbers", location="",
                                  domain="example.com", data_fields=[], origin_location="", max_distance_km=None)
    assert "site:example.com" in result


def test_build_search_query_with_data_fields() -> None:
    result = _build_search_query(query="dentists", location="",
                                  domain="", data_fields=["phone", "email"], origin_location="", max_distance_km=None)
    assert "dentists" in result


def test_build_search_query_with_location_distance() -> None:
    result = _build_search_query(query="hotels", location="Paris",
                                  domain="", data_fields=[], origin_location="London", max_distance_km=100)
    assert "hotels" in result
    assert "Paris" in result


def test_canonicalize_url_removes_fragment() -> None:
    result = _canonicalize_url("https://example.com/page#section")
    assert "#section" not in result


def test_canonicalize_url_strips_query_and_fragment() -> None:
    result = _canonicalize_url("https://example.com/page?q=test#frag")
    assert result == "https://example.com/page"
    assert "?" not in result
    assert "#" not in result


def test_canonicalize_url_adds_trailing_slash() -> None:
    result = _canonicalize_url("https://example.com")
    assert result == "https://example.com/"


def test_canonicalize_url_handles_empty() -> None:
    assert _canonicalize_url("") == ""
    assert _canonicalize_url(None) == ""


def test_source_policy_accepts_enum_values() -> None:
    assert _source_allowed("official", SourcePolicy.OFFICIAL_ONLY) is True
    assert _source_allowed("directory", SourcePolicy.OFFICIAL_ONLY) is False
    assert _source_allowed("directory", SourcePolicy.OFFICIAL_PLUS_DIRECTORY) is True
    assert _source_allowed("social", SourcePolicy.OFFICIAL_ONLY) is False
    assert _source_allowed("search_result", SourcePolicy.ALL_SOURCES) is True


def test_contact_field_bias_prefers_directory_sources() -> None:
    item = {
        "title": "Top Interior Designers Chennai",
        "body": "Directory with contacts and listings",
        "href": "https://example.com/interior-designers-chennai-list",
    }
    data_fields = ["company_name", "phone", "email", "website", "address"]
    directory_score = _score_result(
        item=item, query="interior designers chennai", location="Chennai, India",
        data_fields=data_fields, source_type="directory",
    )
    official_score = _score_result(
        item=item, query="interior designers chennai", location="Chennai, India",
        data_fields=data_fields, source_type="official",
    )
    assert directory_score > official_score

