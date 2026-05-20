from pathlib import Path
from enrich_chennai_leads import (
    EnrichmentContext,
    infer_enrichment_context,
    normalize_phone,
    extract_contact_data_from_html,
)

def test_infer_enrichment_context_from_filename():
    # Test UK / London inference from filename
    input_file = Path("/home/user/workspace/london_interior_designers_cleaned.json")
    records = []
    ctx = infer_enrichment_context(input_file, records)
    
    assert ctx.city == "London"
    assert ctx.niche == "Interior Designer"
    assert ctx.country_name == "United Kingdom"
    assert ctx.country_code == "+44"

    # Test India / Chennai inference from filename
    input_file = Path("/home/user/workspace/chennai_leads.json")
    ctx = infer_enrichment_context(input_file, records)
    
    assert ctx.city == "Chennai"
    assert ctx.country_name == "India"
    assert ctx.country_code == "+91"


def test_infer_enrichment_context_from_records():
    # Fallback to scanning records if filename has no matches
    input_file = Path("/home/user/workspace/leads.json")
    records = [
        {"address": "123 Rue de la Paix, Paris, France"},
        {"address": "456 Avenue des Champs-Élysées, Paris"}
    ]
    ctx = infer_enrichment_context(input_file, records)
    
    assert ctx.city == "Paris"
    assert ctx.country_name == "France"
    assert ctx.country_code == "+33"


def test_normalize_phone_dynamic_country_codes():
    # Test India format formatting
    assert normalize_phone("9876543210", country_code="+91") == "+91 9876543210"
    assert normalize_phone("09876543210", country_code="+91") == "+91 9876543210"
    assert normalize_phone("919876543210", country_code="+91") == "+91 9876543210"

    # Test UK format formatting
    assert normalize_phone("07700900077", country_code="+44") == "+44 7700900077"
    assert normalize_phone("7700900077", country_code="+44") == "+44 7700900077"

    # Test US format formatting
    assert normalize_phone("2125550199", country_code="+1") == "+1 2125550199"
    assert normalize_phone("12125550199", country_code="+1") == "+1 2125550199"

    # Test already-prefixed numbers are kept as-is
    assert normalize_phone("+44 7700 900077", country_code="+91") == "+44 7700 900077"


def test_extract_contact_data_dynamic_address_filter():
    london_ctx = EnrichmentContext(
        city="London",
        niche="Interior Designer",
        country_name="United Kingdom",
        country_code="+44"
    )
    
    html = """
    <html>
      <body>
        <p>Contact us at 020 7946 0958 or hello@londondecor.co.uk</p>
        <p>Visit our showroom at: 221B Baker St, London, United Kingdom</p>
      </body>
    </html>
    """
    
    data = extract_contact_data_from_html(html, context=london_ctx)
    
    assert "hello@londondecor.co.uk" in data.emails
    assert "+44 2079460958" in data.phones
    assert any("221B Baker St" in addr for addr in data.addresses)
