"""Unit tests for rating extraction (star ratings, schema, aria, CSS width)."""

from __future__ import annotations

from app.rating_extractor import extract_ratings


def _ratings(html: str, **kwargs) -> list[dict]:
    result = extract_ratings(html, **kwargs)
    return [r.to_dict() for r in result.ratings]


class TestSchemaJsonLd:
    def test_aggregate_rating(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product",
         "aggregateRating":{"@type":"AggregateRating","ratingValue":4.5,"bestRating":5,"reviewCount":127}}
        </script></body></html>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 4.5
        assert ratings[0]["best_rating"] == 5.0
        assert ratings[0]["review_count"] == 127
        assert ratings[0]["source"] == "schema"

    def test_simple_rating(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Rating","ratingValue":3.5,"bestRating":5}
        </script></body></html>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 3.5

    def test_list_format(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        [{"@type":"Product","aggregateRating":{"@type":"AggregateRating","ratingValue":4.0,"reviewCount":50}}]
        </script></body></html>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 4.0

    def test_no_rating(self) -> None:
        assert _ratings("<html><body><p>No rating here</p></body></html>") == []


class TestSchemaMicrodata:
    def test_microdata_rating(self) -> None:
        html = """<div itemscope itemtype="https://schema.org/Product">
        <div itemprop="aggregateRating" itemscope itemtype="https://schema.org/AggregateRating">
          <span itemprop="ratingValue">4.2</span>
          <span itemprop="bestRating">5</span>
          <span itemprop="reviewCount">99</span>
        </div></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 4.2
        assert ratings[0]["review_count"] == 99

    def test_microdata_best_rating_default(self) -> None:
        """When bestRating is missing, defaults to 5.0 (common star scale)."""
        html = """<div itemscope itemtype="https://schema.org/Rating">
          <span itemprop="ratingValue">4.5</span>
        </div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 4.5
        assert ratings[0]["best_rating"] == 5.0


class TestAriaLabel:
    def test_rated_x_out_of_y(self) -> None:
        html = """<div aria-label="Rated 3.5 out of 5 stars"></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 3.5
        assert ratings[0]["best_rating"] == 5.0
        assert ratings[0]["source"] == "aria"

    def test_average_rating(self) -> None:
        html = """<div aria-label="Average rating: 4.2"></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 4.2

    def test_score_format(self) -> None:
        html = """<div aria-label="Score: 9.5 out of 10"></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 9.5
        assert ratings[0]["best_rating"] == 10.0


class TestWidthBased:
    def test_width_percentage(self) -> None:
        html = """<div class="stars"><span style="width: 70%"></span></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 3.5  # 70 / 20
        assert ratings[0]["source"] == "width"

    def test_full_stars(self) -> None:
        html = """<div class="star-rating"><span style="width: 100%"></span></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 5.0

    def test_half_stars(self) -> None:
        html = """<div class="rating-stars"><span style="width: 50%"></span></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 2.5

    def test_non_star_class_ignored(self) -> None:
        html = """<div class="something-else"><span style="width: 70%"></span></div>"""
        ratings = _ratings(html)
        # Should not find anything because parent doesn't have star/rating class
        assert len(ratings) == 0


class TestDataAttribute:
    def test_data_rating(self) -> None:
        html = """<div data-rating="4.5"></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 4.5
        assert ratings[0]["source"] == "data_attr"

    def test_data_score(self) -> None:
        html = """<div data-score="7.5"></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 7.5
        assert ratings[0]["best_rating"] == 10.0

    def test_data_star_rating(self) -> None:
        html = """<div data-star-rating="3"></div>"""
        ratings = _ratings(html)
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 3.0
        assert ratings[0]["best_rating"] == 5.0


class TestIntegration:
    def test_schema_takes_priority(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"@type":"Product","aggregateRating":{"@type":"AggregateRating","ratingValue":4.5,"reviewCount":100}}
        </script>
        <div aria-label="Rated 3.0 out of 5 stars"></div>
        </body></html>"""
        result = extract_ratings(html)
        ratings = [r.to_dict() for r in result.ratings]
        assert len(ratings) == 1
        assert ratings[0]["rating_value"] == 4.5
        assert result.source == "schema"

    def test_heuristics_disabled(self) -> None:
        html = """<div data-rating="4.5"></div>"""
        ratings = _ratings(html, enable_heuristics=False)
        assert ratings == []

    def test_best_rating_method(self) -> None:
        html = """<html><body>
        <div aria-label="Rated 4.0 out of 5 stars"></div>
        <div data-rating="3.0"></div>
        </body></html>"""
        result = extract_ratings(html)
        best = result.best()
        assert best is not None
        assert best.source == "aria"  # higher confidence

    def test_empty_html(self) -> None:
        assert _ratings("") == []

    def test_to_dict_format(self) -> None:
        html = """<html><body>
        <script type="application/ld+json">
        {"aggregateRating":{"@type":"AggregateRating","ratingValue":4.0,"reviewCount":50}}
        </script></body></html>"""
        result = extract_ratings(html)
        d = result.to_dict()
        assert d["source"] == "schema"
        assert d["count"] == 1
        assert "normalized" in d["ratings"][0]
        assert d["ratings"][0]["normalized"] == 0.8  # 4.0/5.0
