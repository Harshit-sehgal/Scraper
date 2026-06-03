import re

import app.scraper as scraper_mod
from app.models import FieldType, SchemaField
from app.selector_engine import apply_selectors, extract_with_regex


def _lead_schema() -> list[SchemaField]:
    return [
        SchemaField(name="company_name", field_type=FieldType.STRING, required=True, description=""),
        SchemaField(name="phone", field_type=FieldType.PHONE, required=False, description=""),
        SchemaField(name="email", field_type=FieldType.EMAIL, required=False, description=""),
        SchemaField(name="website", field_type=FieldType.URL, required=False, description=""),
    ]


def test_apply_selectors_enriches_contacts_from_mailto_tel_links() -> None:
    html = """
    <html><body>
      <div class="card">
        <h3>Acme Interiors</h3>
        <a class="site" href="https://acme.example">Website</a>
        <a class="mail" href="mailto:hello@acme.example?subject=Lead">Email Us</a>
        <a class="phone" href="tel:+91 98765 43210">Call Us</a>
      </div>
    </body></html>
    """

    selectors = {
        "item_container": "div.card",
        "fields": {
            "company_name": "h3",
            "phone": "a.phone",
            "email": "a.mail",
            "website": "a.site",
        },
    }

    results = apply_selectors(html, selectors, _lead_schema(), base_url="https://acme.example")

    assert len(results) == 1
    row = results[0]
    assert row["company_name"] == "Acme Interiors"
    assert row["email"] == "hello@acme.example"
    assert re.sub(r"\D", "", row["phone"] or "") == "919876543210"


def test_extract_with_regex_enriches_contacts_from_mailto_tel_links() -> None:
    html = """
    <html><body>
      <div class="listing-item">
        <h3>Beta Designs</h3>
        <a href="mailto:support@beta.example">Email</a>
        <a href="tel:+91 98888 22222">Call</a>
      </div>
    </body></html>
    """

    results = extract_with_regex(html, _lead_schema(), base_url="https://beta.example")

    assert results
    assert any(r.get("email") == "support@beta.example" for r in results)
    assert any(re.sub(r"\D", "", r.get("phone") or "") == "919888822222" for r in results)


def test_limit_source_records_prioritizes_contact_rows(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_RECORDS_PER_SOURCE", 2)
    schema = _lead_schema()

    records = [
        {"company_name": "No Contact High Score", "record_score": 0.95, "website": "https://a.example"},
        {"company_name": "Has Email", "record_score": 0.8, "email": "lead@b.example"},
        {"company_name": "Has Phone", "record_score": 0.79, "phone": "+91 98888 77777"},
    ]

    trimmed = scraper_mod._limit_source_records(records, schema)

    assert len(trimmed) == 2
    names = {r.get("company_name") for r in trimmed}
    assert names == {"Has Email", "Has Phone"}


def test_boost_contacts_with_page_html_injects_page_contact_when_missing() -> None:
    schema = _lead_schema()
    rows = [
        {
            "company_name": "Gamma Interiors",
            "phone": None,
            "email": None,
            "website": "https://gamma.example",
            "record_score": 0.7,
        }
    ]
    html = """
    <html><body>
      <footer>
        <a href="mailto:hello@gamma.example">hello@gamma.example</a>
        <a href="tel:+91 90000 11111">+91 90000 11111</a>
      </footer>
    </body></html>
    """

    boosted = scraper_mod._boost_contacts_with_page_html(rows, html, schema)

    assert boosted[0].get("email") == "hello@gamma.example"
    assert re.sub(r"\D", "", boosted[0].get("phone") or "") == "919000011111"
