"""Unit tests for stock/availability extraction.

Tests schema.org offers, CSS classes, text patterns, and data attributes.
"""

from __future__ import annotations

from app.stock_extractor import extract_stock


def _results(html: str, **kwargs) -> list[dict]:
    result = extract_stock(html, **kwargs)
    return [r.to_dict() for r in result.results]


class TestSchemaJsonLd:
    def test_in_stock(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Offer","availability":"https://schema.org/InStock"}
        </script></body></html>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"
        assert results[0]["source"] == "schema"

    def test_out_of_stock(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Offer","availability":"https://schema.org/OutOfStock"}
        </script></body></html>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "out_of_stock"

    def test_preorder(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Offer","availability":"https://schema.org/PreOrder"}
        </script></body></html>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "preorder"

    def test_nested_in_product(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Product","name":"Widget","offers":{"@type":"Offer","availability":"https://schema.org/InStock"}}
        </script></body></html>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"

    def test_inventory_level(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Offer","availability":"https://schema.org/InStock",
         "inventoryLevel":{"value":42}}
        </script></body></html>"""
        results = _results(html)
        # Should have at least one in_stock result
        assert any(r["status"] == "in_stock" for r in results)
        assert any(r.get("quantity") == 42 for r in results)

    def test_no_schema(self) -> None:
        assert _results("<html><body><p>Nothing here.</p></body></html>") == []


class TestSchemaMicrodata:
    def test_meta_availability(self) -> None:
        html = """<div itemscope itemtype="https://schema.org/Offer">
        <meta itemprop="availability" content="https://schema.org/InStock">
        </div>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"

    def test_link_availability(self) -> None:
        html = """<div itemscope itemtype="https://schema.org/Offer">
        <link itemprop="availability" href="https://schema.org/OutOfStock">
        </div>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "out_of_stock"


class TestClassHeuristic:
    def test_in_stock_class(self) -> None:
        html = """<span class="in-stock"></span>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"

    def test_out_of_stock_class(self) -> None:
        html = """<span class="out-of-stock"></span>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "out_of_stock"

    def test_sold_out_class(self) -> None:
        html = """<span class="sold-out"></span>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "out_of_stock"


class TestTextHeuristic:
    def test_in_stock_text(self) -> None:
        html = "<p>In Stock</p>"
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"

    def test_out_of_stock_text(self) -> None:
        html = "<p>Currently unavailable</p>"
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "out_of_stock"

    def test_quantity_text(self) -> None:
        html = "<p>Only 5 left in stock</p>"
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"
        assert results[0]["quantity"] == 5

    def test_preorder_text(self) -> None:
        html = "<p>Pre-order now</p>"
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "preorder"

    def test_discontinued_text(self) -> None:
        html = "<p>Discontinued</p>"
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "out_of_stock"

    def test_add_to_cart_is_in_stock(self) -> None:
        html = "<button>Add to Cart</button>"
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"


class TestDataAttribute:
    def test_data_stock_in_stock(self) -> None:
        html = """<div data-stock="in_stock"></div>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"
        assert results[0]["source"] == "data_attr"

    def test_data_stock_out(self) -> None:
        html = """<div data-stock="out_of_stock"></div>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "out_of_stock"

    def test_data_availability(self) -> None:
        html = """<div data-availability="1"></div>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"

    def test_data_inventory_zero(self) -> None:
        html = """<div data-inventory="0"></div>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "out_of_stock"
        assert results[0]["quantity"] == 0

    def test_data_inventory_positive(self) -> None:
        html = """<div data-inventory="15"></div>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "in_stock"
        assert results[0]["quantity"] == 15

    def test_preorder_data_attr(self) -> None:
        html = """<div data-stock-status="preorder"></div>"""
        results = _results(html)
        assert len(results) == 1
        assert results[0]["status"] == "preorder"


class TestIntegration:
    def test_schema_takes_priority(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Offer","availability":"https://schema.org/InStock"}
        </script>
        <span class="out-of-stock">Out of Stock</span>
        </body></html>"""
        result = extract_stock(html)
        assert result.source == "schema"
        assert result.results[0].status == "in_stock"

    def test_heuristics_disabled(self) -> None:
        html = """<span class="in-stock">In Stock</span>"""
        results = _results(html, enable_heuristics=False)
        assert results == []

    def test_best_method(self) -> None:
        html = """<span class="sold-out">Sold Out</span>"""
        result = extract_stock(html)
        best = result.best()
        assert best is not None
        assert best.status == "out_of_stock"

    def test_empty_html(self) -> None:
        assert _results("") == []

    def test_to_dict_format(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Offer","availability":"https://schema.org/OutOfStock"}
        </script></body></html>"""
        result = extract_stock(html)
        d = result.to_dict()
        assert d["source"] == "schema"
        assert d["count"] == 1
