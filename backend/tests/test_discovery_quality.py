from app.discovery import _looks_noisy_url, _score_result, _source_allowed
from app.models import SourcePolicy


def test_looks_noisy_url_blocks_configured_dead_domain():
    assert _looks_noisy_url("https://quickfinds.org/listing/top-10-interior-design-company-in-chennai") is True


def test_contact_field_bias_prefers_directory_sources():
    item = {
        "title": "Top Interior Designers Chennai",
        "body": "Directory with contacts and listings",
        "href": "https://example.com/interior-designers-chennai-list",
    }
    data_fields = ["company_name", "phone", "email", "website", "address"]

    directory_score = _score_result(
        item=item,
        query="interior designers chennai",
        location="Chennai, India",
        data_fields=data_fields,
        source_type="directory",
    )
    official_score = _score_result(
        item=item,
        query="interior designers chennai",
        location="Chennai, India",
        data_fields=data_fields,
        source_type="official",
    )

    assert directory_score > official_score


def test_source_policy_accepts_enum_values():
    assert _source_allowed("official", SourcePolicy.OFFICIAL_ONLY) is True
    assert _source_allowed("directory", SourcePolicy.OFFICIAL_ONLY) is False
    assert _source_allowed("directory", SourcePolicy.OFFICIAL_PLUS_DIRECTORY) is True
