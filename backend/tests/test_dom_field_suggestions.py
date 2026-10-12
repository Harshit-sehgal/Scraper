"""Regression tests for generic, repeated-DOM field discovery."""

from app.selector_engine import extract_raw_from_selectors
from app.url_value_classification import infer_dom_field_suggestions


def test_infer_dom_field_suggestions_uses_repeated_semantic_values() -> None:
    html = """
    <html><body>
      <nav><a href='/home'>Home</a></nav>
      <main>
        <article class="record">
          <h2 class="name">Alpha</h2>
          <span class="price">$12</span>
          <span class="availability">In stock</span>
        </article>
        <article class="record">
          <h2 class="name">Beta</h2>
          <span class="price">$15</span>
          <span class="availability">Out of stock</span>
        </article>
      </main>
      <footer>Copyright and terms</footer>
    </body></html>
    """

    fields = infer_dom_field_suggestions(html, "article.record")

    by_name = {field["name"]: field for field in fields}
    assert {"name", "price", "availability"}.issubset(by_name)
    assert all(by_name[name]["selector"] for name in ("name", "price", "availability"))
    assert by_name["price"]["example_value"] == "$12"
    assert "phone" not in by_name
    assert "copyright" not in by_name


def test_infer_dom_field_suggestions_maps_table_headers() -> None:
    html = """
    <table>
      <thead><tr><th>SKU</th><th>Name</th><th>Unit price</th></tr></thead>
      <tbody>
        <tr><td>SKU-1</td><td>Brass Fitting</td><td>$4.20</td></tr>
        <tr><td>SKU-2</td><td>Steel Clamp</td><td>$2.85</td></tr>
      </tbody>
    </table>
    """
    fields = infer_dom_field_suggestions(html, "table tr")
    by_name = {field["name"]: field for field in fields}
    assert {"sku", "name", "unit_price"}.issubset(by_name)
    assert by_name["unit_price"]["selector"] == "td:nth-of-type(3)"


def test_infer_dom_field_suggestions_samples_large_repeating_catalog() -> None:
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "pages" / "large_catalog.html"
    html = fixture.read_text(encoding="utf-8")
    fields = infer_dom_field_suggestions(html, "div.catalog-entry")
    names = {field["name"] for field in fields}
    assert {"name", "price", "region", "sku"}.issubset(names)


def test_infer_dom_field_suggestions_finds_generic_text_author_and_tags() -> None:
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "pages" / "395f96f5d719.html"
    html = fixture.read_text(encoding="utf-8")
    fields = infer_dom_field_suggestions(html, "div.quote")
    by_name = {field["name"]: field for field in fields}

    assert {"text", "author", "tag"}.issubset(by_name)
    assert by_name["text"]["selector"] == "span.text"
    assert by_name["text"]["type"] == "string"
    assert by_name["author"]["selector"] == "small.author"
    assert by_name["tag"]["selector"] == "a.tag"
    assert by_name["tag"]["type"] == "list_string"


def test_infer_dom_field_suggestions_maps_prefixed_semantic_classes() -> None:
    html = """
    <div class="record">
      <h3 class="record-name">Andorra</h3>
      <span class="record-capital">Andorra la Vella</span>
      <span class="record-population">84000</span>
      <span class="record-area">468.0</span>
      <a class="record-link" href="https://example.test/andorra">Details</a>
    </div>
    <div class="record">
      <h3 class="record-name">Brazil</h3>
      <span class="record-capital">Brasilia</span>
      <span class="record-population">212000000</span>
      <span class="record-area">8515767.0</span>
      <a class="record-link" href="https://example.test/brazil">Details</a>
    </div>
    """
    fields = infer_dom_field_suggestions(html, "div.record")
    by_name = {field["name"]: field for field in fields}

    assert {"name", "capital", "population", "area", "url"}.issubset(by_name)
    assert by_name["capital"]["selector"] == "span.record-capital"
    assert by_name["population"]["type"] == "number"
    assert by_name["url"]["selector"] == "a.record-link"


def test_name_field_uses_entity_link_instead_of_aggregate_title_wrapper() -> None:
    html = """
    <div class="record">
      <span class="rank">1.</span>
      <div class="title">
        <a href="https://example.test/alpha">Alpha headline</a>
        <span class="source">example.test</span>
      </div>
      <span class="category">Research</span>
    </div>
    <div class="record">
      <span class="rank">2.</span>
      <div class="title">
        <a href="https://example.test/beta">Beta headline</a>
        <span class="source">example.test</span>
      </div>
      <span class="category">Engineering</span>
    </div>
    """
    fields = infer_dom_field_suggestions(html, "div.record")
    selectors = {
        "item_container": "div.record",
        "fields": {field["name"]: {"selector": field["selector"], "type": field["type"]} for field in fields},
    }

    rows = extract_raw_from_selectors(html, selectors, base_url="https://example.test/")

    assert rows[0]["name"] == "Alpha headline"
    assert rows[0]["url"] == "https://example.test/alpha"
    assert "example.test" not in rows[0]["name"]


def test_infer_dom_field_suggestions_maps_definition_list_labels() -> None:
    html = """
    <dl>
      <dt>Country</dt><dd>India</dd>
      <dt>Capital</dt><dd>New Delhi</dd>
      <dt>Population</dt><dd>1,428,600,000</dd>
      <dt>Area</dt><dd>3,287,590 km2</dd>
    </dl>
    """

    fields = infer_dom_field_suggestions(html, "dl")
    by_name = {field["name"]: field for field in fields}
    assert {"country", "capital", "population", "area"}.issubset(by_name)
    assert by_name["population"]["type"] == "number"
    assert by_name["area"]["type"] == "number"
    assert by_name["country"]["selector"] == "dd:nth-of-type(1)"

    selectors = {
        "item_container": "dl",
        "fields": {field["name"]: {"selector": field["selector"], "type": field["type"]} for field in fields},
    }
    rows = extract_raw_from_selectors(html, selectors)
    assert rows == [
        {
            "country": "India",
            "capital": "New Delhi",
            "population": "1,428,600,000",
            "area": "3,287,590 km2",
        },
    ]


def test_infer_dom_field_suggestions_maps_two_column_key_value_table() -> None:
    html = """
    <table>
      <tr><td>Country</td><td>India</td></tr>
      <tr><td>Capital</td><td>New Delhi</td></tr>
      <tr><td>Population</td><td>1,428,600,000</td></tr>
    </table>
    """

    fields = infer_dom_field_suggestions(html, "table")
    by_name = {field["name"]: field for field in fields}
    assert {"country", "capital", "population"}.issubset(by_name)
    assert by_name["population"]["selector"] == "tr:nth-of-type(3) > td:nth-of-type(2)"

    selectors = {
        "item_container": "table",
        "fields": {field["name"]: {"selector": field["selector"], "type": field["type"]} for field in fields},
    }
    assert extract_raw_from_selectors(html, selectors) == [
        {"country": "India", "capital": "New Delhi", "population": "1,428,600,000"},
    ]


def test_infer_dom_field_suggestions_exposes_plain_list_item_text() -> None:
    html = """
    <html><body>
      <nav><a href="/home">Home</a></nav>
      <ul>
        <li>Plain item Alpha</li>
        <li>Plain item Beta</li>
        <li>Plain item Gamma</li>
        <li>Plain item Delta</li>
        <li>Plain item Epsilon</li>
        <li>Plain item Zeta</li>
      </ul>
      <footer>Terms and navigation noise</footer>
    </body></html>
    """

    fields = infer_dom_field_suggestions(html, "ul li")
    by_name = {field["name"]: field for field in fields}
    assert by_name["text"]["selector"] == ":scope"
    assert by_name["text"]["type"] == "string"

    selectors = {
        "item_container": "ul li",
        "fields": {field["name"]: {"selector": field["selector"], "type": field["type"]} for field in fields},
    }
    rows = extract_raw_from_selectors(html, selectors)
    assert [row["text"] for row in rows] == [
        "Plain item Alpha",
        "Plain item Beta",
        "Plain item Gamma",
        "Plain item Delta",
        "Plain item Epsilon",
        "Plain item Zeta",
    ]


def test_infer_dom_field_suggestions_scopes_article_prose() -> None:
    html = """
    <html><body>
      <nav><p>Navigation prose must not be a result.</p></nav>
      <article>
        <h1>Example title</h1>
        <p>First paragraph with useful prose.</p>
        <div><p>Nested paragraph with more detail.</p></div>
      </article>
      <footer><p>Footer prose must not be a result.</p></footer>
    </body></html>
    """

    fields = infer_dom_field_suggestions(html, "body")
    by_name = {field["name"]: field for field in fields}
    assert by_name["name"]["example_value"] == "Example title"
    assert by_name["description"]["type"] == "list_string"
    assert by_name["description"]["selector"] == "article p"

    selectors = {
        "item_container": "body",
        "fields": {field["name"]: {"selector": field["selector"], "type": field["type"]} for field in fields},
    }
    rows = extract_raw_from_selectors(html, selectors)
    assert rows == [
        {
            "name": "Example title",
            "description": [
                "First paragraph with useful prose.",
                "Nested paragraph with more detail.",
            ],
        },
    ]


def test_infer_dom_field_suggestions_does_not_duplicate_nested_list_items() -> None:
    parents = "".join(f"<li>Parent {i}<ul><li>Child {i}-a</li><li>Child {i}-b</li></ul></li>" for i in range(6))
    html = f"<html><body><ul>{parents}</ul></body></html>"

    fields = infer_dom_field_suggestions(html, "body > ul:nth-of-type(1) > li")
    selectors = {
        "item_container": "body > ul:nth-of-type(1) > li",
        "fields": {field["name"]: {"selector": field["selector"], "type": field["type"]} for field in fields},
    }
    rows = extract_raw_from_selectors(html, selectors)
    assert [row["text"] for row in rows] == [f"Parent {i}" for i in range(6)]
