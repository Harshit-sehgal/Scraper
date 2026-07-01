"""Stock/availability extraction — detects in-stock/out-of-stock status.

Detects product availability from multiple patterns:

1.  **Schema.org offers** — ``Offers.availability`` URL pattern
    (``InStock``, ``OutOfStock``, ``PreOrder``, etc.)

2.  **CSS classes** — common e-commerce CSS classes like
    ``in-stock``, ``out-of-stock``, ``available``, ``sold-out``

3.  **Text patterns** — text like "In Stock", "Out of Stock",
    "Only 3 left in stock", "Currently unavailable"

4.  **Data attributes** — ``[data-stock]``, ``[data-availability]``,
    ``[data-inventory]``

No remote calls, no LLM, no Playwright — pure HTML parsing via
BeautifulSoup.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

_IN_STOCK_TEXT = re.compile(
    r"(?:in[ _-]?stock|available|add[ _-]?to[ _-]?cart|buy[ _-]?now|\d+\s*(?:left|remaining))",
    re.IGNORECASE,
)
_OUT_OF_STOCK_TEXT = re.compile(
    r"(?:out[ _-]?of[ _-]?stock|unavailable|sold[ _-]?out|discontinued|"
    r"backordered|temporarily[ _-]?unavailable|currently[ _-]?unavailable|"
    r"notify[ _-]?me[ _-]?when[ _-]?available)",
    re.IGNORECASE,
)
_PREORDER_TEXT = re.compile(
    r"(?:pre[ _-]?order|preorder|coming[ _-]?soon|reserve[ _-]?now|release[ _-]?date)",
    re.IGNORECASE,
)

# Schema.org availability URLs
_AVAILABILITY_MAP: dict[str, str] = {
    "https://schema.org/InStock": "in_stock",
    "http://schema.org/InStock": "in_stock",
    "https://schema.org/OutOfStock": "out_of_stock",
    "http://schema.org/OutOfStock": "out_of_stock",
    "https://schema.org/PreOrder": "preorder",
    "http://schema.org/PreOrder": "preorder",
    "https://schema.org/PreSale": "preorder",
    "http://schema.org/PreSale": "preorder",
    "https://schema.org/LimitedAvailability": "limited",
    "http://schema.org/LimitedAvailability": "limited",
    "https://schema.org/Discontinued": "discontinued",
    "http://schema.org/Discontinued": "discontinued",
    "https://schema.org/OnlineOnly": "in_stock",
    "http://schema.org/OnlineOnly": "in_stock",
}

_STOCK_CLASS_RE = re.compile(
    r"(?:in[-_]?stock|out[-_]?of[-_]?stock|available|sold[-_]?out|"
    r"discontinued|pre[-_]?order|backorder)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StockResult:
    """A single stock/availability detection result."""

    status: str  # "in_stock" | "out_of_stock" | "preorder" | "limited" | "discontinued" | "unknown"
    quantity: int | None = None  # numeric quantity if detected
    source: str = "schema"  # "schema" | "class" | "text" | "data_attr"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "quantity": self.quantity,
            "source": self.source,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class StockExtractionResult:
    """Aggregate stock extraction result."""

    results: list[StockResult] = field(default_factory=list)
    source: str = "none"  # "schema" | "heuristic" | "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "source": self.source,
            "count": len(self.results),
        }

    def best(self) -> StockResult | None:
        """Return the highest-confidence result, or ``None``."""
        if not self.results:
            return None
        return max(self.results, key=lambda r: r.confidence)


# ── Schema.org extraction ───────────────────────────────────────────


def _extract_schema_availability(soup: BeautifulSoup) -> list[StockResult]:
    """Extract availability from schema.org offers (JSON-LD and microdata)."""
    results: list[StockResult] = []

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
            results.extend(_extract_availability_from_jsonld(item))

    # Microdata schema.org Offer
    for offer in soup.find_all(attrs={"itemtype": re.compile(r"https?://schema\.org/Offer", re.IGNORECASE)}):
        for meta in offer.find_all("meta", attrs={"itemprop": "availability"}):
            content = meta.get("content", "")
            mapped = _AVAILABILITY_MAP.get(content)
            if mapped:
                results.append(
                    StockResult(
                        status=mapped,
                        source="schema",
                        confidence=0.95,
                    )
                )
                break
        # Also check link elements for availability
        for link in offer.find_all("link", attrs={"itemprop": "availability"}):
            href = link.get("href", "")
            mapped = _AVAILABILITY_MAP.get(href)
            if mapped:
                results.append(
                    StockResult(
                        status=mapped,
                        source="schema",
                        confidence=0.95,
                    )
                )
                break

    return results


def _extract_availability_from_jsonld(item: dict[str, Any]) -> list[StockResult]:
    """Recursively extract availability from a JSON-LD item."""
    results: list[StockResult] = []
    item_type = item.get("@type", "")
    if item_type == "Offer":
        availability = item.get("availability", "")
        mapped = _AVAILABILITY_MAP.get(availability)
        if mapped:
            results.append(
                StockResult(
                    status=mapped,
                    source="schema",
                    confidence=0.95,
                )
            )
        # Also check for quantity
        inventory = item.get("inventoryLevel")
        if isinstance(inventory, dict):
            try:
                qty = int(inventory.get("value", 0) or 0)
                if qty > 0:
                    results.append(
                        StockResult(
                            status="in_stock",
                            quantity=qty,
                            source="schema",
                            confidence=0.9,
                        )
                    )
            except (ValueError, TypeError):
                pass
    # Check nested
    for value in item.values():
        if isinstance(value, dict):
            results.extend(_extract_availability_from_jsonld(value))
        elif isinstance(value, list):
            for sub in value:
                if isinstance(sub, dict):
                    results.extend(_extract_availability_from_jsonld(sub))
    return results


# ── Heuristic extraction ────────────────────────────────────────────


def _extract_from_class(soup: BeautifulSoup) -> list[StockResult]:
    """Extract availability from CSS class names on product containers."""
    results: list[StockResult] = []
    for el in soup.find_all(class_=_STOCK_CLASS_RE):
        classes = el.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()
        for cls in classes:
            cls_lower = cls.lower()
            if _OUT_OF_STOCK_TEXT.search(cls_lower):
                results.append(StockResult(status="out_of_stock", source="class", confidence=0.75))
                break
            if _IN_STOCK_TEXT.search(cls_lower):
                results.append(StockResult(status="in_stock", source="class", confidence=0.7))
                break
            if _PREORDER_TEXT.search(cls_lower):
                results.append(StockResult(status="preorder", source="class", confidence=0.7))
                break
        # Only the first match per element
        if results:
            break
    return results


def _extract_from_text(soup: BeautifulSoup) -> list[StockResult]:
    """Extract availability from visible text patterns."""
    results: list[StockResult] = []
    seen_texts: set[str] = set()

    for el in soup.find_all(string=True):
        text = el.strip()
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)

        # Check quantity pattern first: "Only 3 left in stock"
        qty_match = re.search(r"(\d+)\s*(?:left|remaining|in stock)", text, re.IGNORECASE)
        if qty_match:
            try:
                qty = int(qty_match.group(1))
                results.append(
                    StockResult(
                        status="in_stock",
                        quantity=qty,
                        source="text",
                        confidence=0.8,
                    )
                )
                continue
            except (ValueError, TypeError):
                pass

        if _PREORDER_TEXT.search(text):
            # Check if it's also "out of stock" text
            if _OUT_OF_STOCK_TEXT.search(text):
                results.append(StockResult(status="out_of_stock", source="text", confidence=0.65))
            else:
                results.append(StockResult(status="preorder", source="text", confidence=0.7))
        elif _OUT_OF_STOCK_TEXT.search(text):
            results.append(StockResult(status="out_of_stock", source="text", confidence=0.75))
        elif _IN_STOCK_TEXT.search(text):
            results.append(StockResult(status="in_stock", source="text", confidence=0.7))

    return results


def _extract_from_data_attr(soup: BeautifulSoup) -> list[StockResult]:
    """Extract availability from data attributes."""
    results: list[StockResult] = []
    attr_names = ("data-stock", "data-availability", "data-inventory", "data-stock-status")

    for el in soup.find_all(lambda tag: any(tag.has_attr(a) for a in attr_names)):
        for attr in attr_names:
            raw = el.get(attr)
            if raw is None:
                continue
            val = str(raw).strip().lower()
            # Try numeric first (handles "0", "15", etc. with quantity)
            try:
                qty = int(val)
                if qty >= 0:
                    results.append(
                        StockResult(
                            status="in_stock" if qty > 0 else "out_of_stock",
                            quantity=qty,
                            source="data_attr",
                            confidence=0.8,
                        )
                    )
                    break
            except (ValueError, TypeError):
                pass
            # Then check string values
            if val in ("in_stock", "instock", "in stock", "true", "yes"):
                results.append(StockResult(status="in_stock", source="data_attr", confidence=0.85))
                break
            if val in ("out_of_stock", "outofstock", "out of stock", "false", "no"):
                results.append(StockResult(status="out_of_stock", source="data_attr", confidence=0.85))
                break
            if val in ("preorder", "pre_order", "pre-order"):
                results.append(StockResult(status="preorder", source="data_attr", confidence=0.85))
                break
            if val == "discontinued":
                results.append(StockResult(status="discontinued", source="data_attr", confidence=0.85))
                break
            if val in ("limited", "low_stock"):
                results.append(StockResult(status="limited", source="data_attr", confidence=0.8))
                break

    return results


# ── Public API ──────────────────────────────────────────────────────


def extract_stock(
    html: str,
    *,
    enable_heuristics: bool = True,
) -> StockExtractionResult:
    """Extract stock/availability data from HTML.

    Prefers schema.org structured data first; falls back to heuristic
    patterns (CSS class names, visible text, data attributes) when
    ``enable_heuristics`` is True (default).

    Args:
        html: Raw HTML of the page.
        enable_heuristics: When True, also scans for structural stock
            patterns.

    Returns:
        :class:`StockExtractionResult` with extracted availability data.
    """
    soup = BeautifulSoup(html, "html.parser")
    all_results: list[StockResult] = []

    # Stage 1: Schema.org
    schema_results = _extract_schema_availability(soup)
    if schema_results:
        return StockExtractionResult(results=schema_results, source="schema")

    # Stage 2: Heuristics (only if schema didn't fire)
    if enable_heuristics:
        for extractor in (
            _extract_from_class,
            _extract_from_text,
            _extract_from_data_attr,
        ):
            try:
                results = extractor(soup)
                all_results.extend(results)
            except (AttributeError, TypeError, ValueError):
                continue

    source = "heuristic" if all_results else "none"
    return StockExtractionResult(results=all_results, source=source)
