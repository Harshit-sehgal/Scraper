"""Star rating extraction — extracts numeric ratings from visual representations.

Detects star ratings from multiple patterns:

1.  **Schema.org Rating** — ``AggregateRating`` / ``Rating`` structured data
    (JSON-LD, microdata) with ``ratingValue``, ``bestRating``, ``reviewCount``.

2.  **Aria-label attributes** — ``aria-label="Rated 3.5 out of 5 stars"``,
    ``aria-label="4.2 average rating"``, etc.

3.  **CSS width-based stars** — elements where the inner star fill is
    expressed as a CSS ``width: X%`` on a child element, representing
    how many stars are filled.

4.  **Data attributes** — ``[data-rating]``, ``[data-score]``,
    ``[data-star-rating]`` on rating widgets.

No remote calls, no LLM, no Playwright — pure HTML parsing via
BeautifulSoup.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

_RATING_ARIA_RE = re.compile(
    r"(?:rated|rating|score|average)[:\s]*([\d.]+)\s*(?:out\s*of\s*)?(\d+)?",
    re.IGNORECASE,
)
_STAR_WIDTH_RE = re.compile(r"width\s*:\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
_STAR_CLASS_RE = re.compile(
    r"(?:star|rating|score)[-_]?(?:full|filled|active|half|empty|off)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RatingResult:
    """A single rating extraction result."""

    rating_value: float
    best_rating: float = 5.0
    review_count: int = 0
    source: str = "schema"  # "schema" | "aria" | "width" | "data_attr"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rating_value": self.rating_value,
            "best_rating": self.best_rating,
            "normalized": round(self.rating_value / self.best_rating, 4) if self.best_rating else 0.0,
            "review_count": self.review_count,
            "source": self.source,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class RatingExtractionResult:
    """Aggregate rating extraction result."""

    ratings: list[RatingResult] = field(default_factory=list)
    source: str = "none"  # "schema" | "heuristic" | "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ratings": [r.to_dict() for r in self.ratings],
            "source": self.source,
            "count": len(self.ratings),
        }

    def best(self) -> RatingResult | None:
        """Return the highest-confidence rating, or ``None`` if none found."""
        if not self.ratings:
            return None
        return max(self.ratings, key=lambda r: r.confidence)


# ── Schema.org extraction ───────────────────────────────────────────


def _extract_schema_rating(soup: BeautifulSoup) -> list[RatingResult]:
    """Extract ratings from ``AggregateRating`` / ``Rating`` JSON-LD and microdata."""
    results: list[RatingResult] = []

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string) if script.string else {}
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            results.extend(_extract_rating_from_jsonld_item(item))

    # Microdata
    for rating_elem in soup.find_all(attrs={"itemtype": re.compile(r"https?://schema\.org/(Aggregate)?Rating", re.IGNORECASE)}):
        try:
            rating_value = float(_find_itemprop_text(rating_elem, "ratingValue") or "")
            best_rating = float(_find_itemprop_text(rating_elem, "bestRating") or "5")
            review_count_str = _find_itemprop_text(rating_elem, "reviewCount") or "0"
            review_count = int(review_count_str) if review_count_str else 0
            results.append(
                RatingResult(
                    rating_value=rating_value,
                    best_rating=best_rating,
                    review_count=review_count,
                    source="schema",
                    confidence=0.95,
                )
            )
        except (ValueError, AttributeError, TypeError):
            continue

    return results


def _extract_rating_from_jsonld_item(item: dict[str, Any]) -> list[RatingResult]:
    """Recursively extract rating from a JSON-LD item (or item containing one)."""
    results: list[RatingResult] = []
    item_type = item.get("@type", "")
    if item_type in ("AggregateRating", "Rating"):
        try:
            rating_value = float(item.get("ratingValue", 0) or 0)
            best_rating = float(item.get("bestRating", 5) or 5)
            review_count = int(item.get("reviewCount", 0) or 0)
            results.append(
                RatingResult(
                    rating_value=rating_value,
                    best_rating=best_rating,
                    review_count=review_count,
                    source="schema",
                    confidence=0.95,
                )
            )
        except (ValueError, TypeError):
            pass
    # Also check nested items
    for value in item.values():
        if isinstance(value, dict):
            results.extend(_extract_rating_from_jsonld_item(value))
        elif isinstance(value, list):
            for sub in value:
                if isinstance(sub, dict):
                    results.extend(_extract_rating_from_jsonld_item(sub))
    return results


def _find_itemprop_text(container: Any, prop: str) -> str | None:
    """Find an ``itemprop`` element and return its text content."""
    el = container.find(attrs={"itemprop": prop})
    return el.get_text(strip=True) if el else None


# ── Heuristic extraction ────────────────────────────────────────────


def _extract_aria_label(soup: BeautifulSoup) -> list[RatingResult]:
    """Extract ratings from ``aria-label`` attributes on rating widgets."""
    results: list[RatingResult] = []
    for el in soup.find_all(attrs={"aria-label": True}):
        label = el.get("aria-label", "")
        m = _RATING_ARIA_RE.search(label)
        if m:
            try:
                rating_value = float(m.group(1))
                best_rating = float(m.group(2)) if m.group(2) else 5.0
                results.append(
                    RatingResult(
                        rating_value=rating_value,
                        best_rating=best_rating,
                        source="aria",
                        confidence=0.85,
                    )
                )
            except (ValueError, TypeError):
                continue
    return results


def _extract_width_based(soup: BeautifulSoup) -> list[RatingResult]:
    """Extract ratings from CSS width-based star fills.

    Looks for elements with ``star`` or ``rating`` in class inside a
    container where a child's ``width: X%`` style indicates the star fill.
    """
    results: list[RatingResult] = []
    for container in soup.find_all(class_=_STAR_CLASS_RE):
        # Look for a child element with an inline style containing width: X%
        for child in container.find_all(style=True):
            style = child.get("style", "")
            m = _STAR_WIDTH_RE.search(style)
            if m:
                try:
                    pct = float(m.group(1))
                    rating_value = pct / 20.0  # 100% = 5 stars
                    if 0 <= rating_value <= 5:
                        results.append(
                            RatingResult(
                                rating_value=round(rating_value, 2),
                                best_rating=5.0,
                                source="width",
                                confidence=0.7,
                            )
                        )
                except (ValueError, TypeError):
                    continue
    return results


def _extract_data_attr(soup: BeautifulSoup) -> list[RatingResult]:
    """Extract ratings from data attributes: ``[data-rating]``, ``[data-score]``, etc."""
    results: list[RatingResult] = []
    attr_names = ("data-rating", "data-score", "data-star-rating", "data-average-rating", "data-rating-value")
    for el in soup.find_all(lambda tag: any(tag.has_attr(a) for a in attr_names)):
        for attr in attr_names:
            raw = el.get(attr)
            if raw is not None:
                try:
                    rating_value = float(str(raw).strip())
                    if 0 < rating_value <= 10:
                        best_rating = 10.0 if rating_value > 5 else 5.0
                        results.append(
                            RatingResult(
                                rating_value=rating_value,
                                best_rating=best_rating,
                                source="data_attr",
                                confidence=0.8,
                            )
                        )
                        break
                except (ValueError, TypeError):
                    continue
    return results


# ── Public API ──────────────────────────────────────────────────────


def extract_ratings(
    html: str,
    *,
    enable_heuristics: bool = True,
) -> RatingExtractionResult:
    """Extract rating data from HTML.

    Prefers schema.org structured data first; falls back to heuristic
    patterns (aria-labels, width-based stars, data attributes) when
    ``enable_heuristics`` is True (default).

    Args:
        html: Raw HTML of the page.
        enable_heuristics: When True, also scans for structural rating
            patterns.

    Returns:
        :class:`RatingExtractionResult` with all extracted ratings and
        the detection source.
    """
    soup = BeautifulSoup(html, "html.parser")
    all_ratings: list[RatingResult] = []

    # Stage 1: Schema.org
    schema_ratings = _extract_schema_rating(soup)
    if schema_ratings:
        return RatingExtractionResult(ratings=schema_ratings, source="schema")

    # Stage 2: Heuristics (only if schema didn't fire)
    if enable_heuristics:
        for extractor in (
            _extract_aria_label,
            _extract_width_based,
            _extract_data_attr,
        ):
            try:
                ratings = extractor(soup)
                all_ratings.extend(ratings)
            except (AttributeError, TypeError, ValueError):
                continue

    source = "heuristic" if all_ratings else "none"
    return RatingExtractionResult(ratings=all_ratings, source=source)
