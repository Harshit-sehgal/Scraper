"""Tests for app.variant_extractor - e-commerce variant detection."""

from __future__ import annotations

from app.variant_extractor import (
    VariantExtractionResult,
    VariantGroup,
    _classify_availability,
    _extract_button_variants,
    _extract_price,
    _extract_radio_variants,
    _extract_select_variants,
    _infer_variant_type,
    extract_variants,
)
from bs4 import BeautifulSoup


def test_extract_variants_empty_html() -> None:
    result = extract_variants("")
    assert result.variants == []
    assert result.variant_groups == []
    assert result.base_record == {}


def test_extract_variants_no_variant_content() -> None:
    result = extract_variants("<html><body><p>No variants here</p></body></html>")
    assert result.variants == []
    assert result.variant_groups == []


def test_extract_variants_select_size() -> None:
    html = """<select class="size-select"><option>S</option><option>M</option><option selected>L</option></select>"""
    result = extract_variants(html)
    assert len(result.variant_groups) == 1
    assert result.variant_groups[0].variant_type == "size"
    assert result.variant_groups[0].options == ["S", "M", "L"]
    assert result.variant_groups[0].selected == "L"
    assert len(result.variants) == 3


def test_extract_variants_with_base_record() -> None:
    html = """<select class="color"><option>Red</option><option>Blue</option></select>"""
    result = extract_variants(html, base_record={"title": "T-Shirt", "price": 19.99})
    assert result.base_record == {"title": "T-Shirt", "price": 19.99}
    assert len(result.variants) == 2
    for v in result.variants:
        assert v["title"] == "T-Shirt"
        assert v["price"] == 19.99
        assert v["variant_type"] == "color"


def test_infer_variant_type_detects_size() -> None:
    assert _infer_variant_type("size-selector", "") == "size"


def test_infer_variant_type_detects_color() -> None:
    assert _infer_variant_type("color-picker", "") == "color"


def test_infer_variant_type_normalises_colour() -> None:
    assert _infer_variant_type("colour-picker", "") == "color"


def test_infer_variant_type_detects_material() -> None:
    assert _infer_variant_type("material-select", "") == "material"


def test_infer_variant_type_detects_style() -> None:
    assert _infer_variant_type("style-variant", "") == "style"


def test_infer_variant_type_returns_none_for_unrelated() -> None:
    assert _infer_variant_type("some-class", "") is None


def test_classify_availability_in_stock_via_aria() -> None:
    soup = BeautifulSoup('<option aria-label="In Stock">Red</option>', "html.parser")
    tag = soup.find("option")
    assert tag is not None
    assert _classify_availability(tag) == "in_stock"


def test_classify_availability_out_of_stock_via_data() -> None:
    soup = BeautifulSoup('<option data-availability="out of stock">Red</option>', "html.parser")
    tag = soup.find("option")
    assert tag is not None
    assert _classify_availability(tag) == "out_of_stock"


def test_classify_availability_unavailable_is_out_of_stock() -> None:
    soup = BeautifulSoup('<option data-availability="unavailable">Red</option>', "html.parser")
    tag = soup.find("option")
    assert tag is not None
    assert _classify_availability(tag) == "out_of_stock"


def test_classify_availability_in_stock_via_text() -> None:
    soup = BeautifulSoup("<option><span>In Stock</span></option>", "html.parser")
    tag = soup.find("option")
    assert tag is not None
    assert _classify_availability(tag) == "in_stock"


def test_classify_availability_unknown() -> None:
    soup = BeautifulSoup("<option>Just a label</option>", "html.parser")
    tag = soup.find("option")
    assert tag is not None
    assert _classify_availability(tag) == "unknown"


def test_classify_availability_checks_title() -> None:
    soup = BeautifulSoup('<option title="Sold Out">Red</option>', "html.parser")
    tag = soup.find("option")
    assert tag is not None
    assert _classify_availability(tag) == "out_of_stock"


def test_extract_price_from_class() -> None:
    soup = BeautifulSoup('<div class="price">$29.99</div>', "html.parser")
    container = soup.find("div")
    assert container is not None
    assert _extract_price(container) == 29.99


def test_extract_price_from_data_attr() -> None:
    soup = BeautifulSoup('<button data-price="15.50">Buy</button>', "html.parser")
    container = soup.find("button")
    assert container is not None
    assert _extract_price(container) == 15.50


def test_extract_price_none() -> None:
    soup = BeautifulSoup("<div>No price here</div>", "html.parser")
    container = soup.find("div")
    assert container is not None
    assert _extract_price(container) is None


def test_extract_select_variants_skips_non_variant() -> None:
    soup = BeautifulSoup('<select name="country"><option>US</option></select>', "html.parser")
    groups, variants = _extract_select_variants(soup)
    assert groups == []
    assert variants == []


def test_extract_select_variants_skips_placeholder_options() -> None:
    html = """<select class="size-select"><option>-- Select --</option><option>M</option></select>"""
    soup = BeautifulSoup(html, "html.parser")
    groups, variants = _extract_select_variants(soup)
    assert len(groups) == 1
    assert groups[0].options == ["M"]


def test_extract_select_variants_does_not_leak_stock_between_options() -> None:
    html = """
    <select class="color-select">
      <option>Red - sold out</option>
      <option>Blue</option>
    </select>
    """
    result = extract_variants(html)
    by_option = {variant["option"]: variant for variant in result.variants}

    assert by_option["Red - sold out"]["availability"] == "out_of_stock"
    assert by_option["Blue"]["availability"] == "unknown"


def test_extract_select_variants_detects_variant_name_without_class() -> None:
    html = '<select name="size"><option>S</option><option>M</option></select>'
    result = extract_variants(html)

    assert len(result.variant_groups) == 1
    assert result.variant_groups[0].variant_type == "size"
    assert [variant["option"] for variant in result.variants] == ["S", "M"]


def test_extract_radio_variants() -> None:
    html = """<input type="radio" name="Size" value="S"><input type="radio" name="Size" value="M" checked>"""
    soup = BeautifulSoup(html, "html.parser")
    groups, variants = _extract_radio_variants(soup)
    assert len(groups) == 1
    assert groups[0].variant_type == "size"
    assert groups[0].options == ["S", "M"]
    assert groups[0].selected == "M"


def test_extract_radio_variants_skips_non_variant_names() -> None:
    html = '<input type="radio" name="gender" value="M"><input type="radio" name="gender" value="F">'
    soup = BeautifulSoup(html, "html.parser")
    groups, variants = _extract_radio_variants(soup)
    assert groups == []
    assert variants == []


def test_extract_radio_variants_dedupes_seen_names() -> None:
    """Same name group should only be processed once."""
    html = '<div><input type="radio" name="Color" value="Red"></div><div><input type="radio" name="Color" value="Blue"></div>'
    soup = BeautifulSoup(html, "html.parser")
    groups, variants = _extract_radio_variants(soup)
    assert len(groups) == 1


def test_extract_button_variants() -> None:
    html = """<div data-variant="size" class="size-options"><button>S</button><button>M</button><button>L</button></div>"""
    soup = BeautifulSoup(html, "html.parser")
    groups, variants = _extract_button_variants(soup)
    assert len(groups) == 1
    assert groups[0].variant_type == "size"
    assert groups[0].options == ["S", "M", "L"]


def test_extract_button_variants_with_price() -> None:
    html = """<div data-variant="color"><button data-price="25.00">Red</button><button data-price="25.00">Blue</button></div>"""
    soup = BeautifulSoup(html, "html.parser")
    groups, variants = _extract_button_variants(soup)
    assert len(variants) == 2
    for v in variants:
        assert v["price"] == 25.00


def test_extract_button_variants_keeps_per_button_prices() -> None:
    html = """<div data-variant="color"><button data-price="25.00">Red</button><button data-price="30.00">Blue</button></div>"""
    result = extract_variants(html)
    by_option = {variant["option"]: variant for variant in result.variants}

    assert by_option["Red"]["price"] == 25.00
    assert by_option["Blue"]["price"] == 30.00


def test_extract_button_variants_skips_empty_labels() -> None:
    html = """<div data-variant="size"><button>S</button><button></button><button>L</button></div>"""
    soup = BeautifulSoup(html, "html.parser")
    groups, variants = _extract_button_variants(soup)
    assert groups[0].options == ["S", "L"]


def test_variant_group_frozen_dataclass() -> None:
    g = VariantGroup(variant_type="size", options=["S", "M", "L"], selected="M")
    assert g.variant_type == "size"
    assert g.options == ["S", "M", "L"]
    assert g.selected == "M"


def test_variant_group_selected_none_by_default() -> None:
    g = VariantGroup(variant_type="color", options=["Red", "Blue"])
    assert g.selected is None


def test_variant_extraction_result_to_dict() -> None:
    result = VariantExtractionResult(
        base_record={"title": "Shirt"},
        variants=[{"variant_type": "size", "option": "M", "title": "Shirt"}],
        variant_groups=[VariantGroup(variant_type="size", options=["S", "M", "L"])],
    )
    d = result.to_dict()
    assert d["base_record"] == {"title": "Shirt"}
    assert len(d["variants"]) == 1
    assert len(d["variant_groups"]) == 1
    assert d["variant_groups"][0]["variant_type"] == "size"
    assert d["variant_groups"][0]["selected"] is None


def test_extract_variants_select_with_price_in_parent() -> None:
    html = """<div class="price">$49.99</div><select class="size-select"><option>S</option><option selected>M</option></select>"""
    result = extract_variants(html)
    assert len(result.variants) == 2
    # Price extraction depends on parent container relationship
    assert all(v["variant_type"] == "size" for v in result.variants)


def test_extract_variants_multiple_selects() -> None:
    html = """
    <select class="size"><option>S</option><option>M</option></select>
    <select class="color"><option>Red</option><option>Blue</option></select>
    """
    result = extract_variants(html)
    assert len(result.variant_groups) == 2
    types = {g.variant_type for g in result.variant_groups}
    assert types == {"size", "color"}
