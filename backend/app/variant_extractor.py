"""E-commerce variant extractor.

Detects size/color/material/style variant groups within product pages
and emits one record per variant option with per-variant price and
availability when detected.

Detection heuristics:
  * ``<select>`` with ``<option>`` inside a container whose class
    contains ``variant|option|size|color|material`` -> VariantGroup
  * ``<input type="radio">`` groups with ``name=...Size...|...Color...``
    -> VariantGroup
  * ``<button>`` elements inside ``[data-variant]`` containers
  * Per-variant price: nearest ``.price`` / ``[data-price]`` within
    the same container
  * Availability: ``<span class="in-stock|out-of-stock">`` per option

No remote calls, no LLM, no Playwright - pure HTML parsing via
BeautifulSoup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Tag

_VARIANT_CONTAINER_RE = re.compile(
    r"(?:variant|option|size|color|material|style|finish|pattern)",
    re.IGNORECASE,
)
_VARIANT_TYPE_RE = re.compile(
    r"(size|color|colour|material|style|finish|pattern|capacity|weight)",
    re.IGNORECASE,
)
_IN_STOCK_RE = re.compile(
    r"(?:in[ _-]?stock|available|add[ _-]?to[ _-]?cart|buy)",
    re.IGNORECASE,
)
_OUT_OF_STOCK_RE = re.compile(
    r"(?:out[ _-]?of[ _-]?stock|unavailable|sold[ _-]?out|discontinued)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VariantGroup:
    """One variant dimension (e.g. Size or Colour) with its options."""

    variant_type: str  # "size" | "color" | "material" | "style"
    options: list[str]  # ["S", "M", "L", "XL"]
    selected: str | None = None  # currently selected option, if detectable


@dataclass
class VariantExtractionResult:
    """Result of scanning a product page for variant options."""

    base_record: dict[str, Any] = field(default_factory=dict)
    variants: list[dict[str, Any]] = field(default_factory=list)
    variant_groups: list[VariantGroup] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_record": dict(self.base_record),
            "variants": [dict(v) for v in self.variants],
            "variant_groups": [
                {
                    "variant_type": g.variant_type,
                    "options": list(g.options),
                    "selected": g.selected,
                }
                for g in self.variant_groups
            ],
        }


def _infer_variant_type(class_attr: str, name_attr: str) -> str | None:
    """Guess the variant dimension from CSS class and input name."""
    combined = f"{class_attr} {name_attr}"
    m = _VARIANT_TYPE_RE.search(combined)
    return m.group(1).lower().replace("colour", "color") if m else None


def _classify_availability(option: Tag) -> str:
    """Return 'in_stock' | 'out_of_stock' | 'unknown' for an option element."""
    # Check attribute first: aria-label, data-availability, etc.
    for attr in ("aria-label", "data-availability", "data-stock", "title"):
        raw = option.get(attr, "")
        if raw is None:
            raw = ""
        val = raw.lower() if isinstance(raw, str) else str(raw).lower()
        if not val:
            continue
        if _OUT_OF_STOCK_RE.search(val):
            return "out_of_stock"
        if _IN_STOCK_RE.search(val):
            return "in_stock"

    if option.has_attr("disabled") or option.get("aria-disabled") == "true":
        return "out_of_stock"

    text_parts = [option.get_text(" ", strip=True)]
    if option.name != "option":
        parent = option.find_parent()
        if parent is not None:
            text_parts.append(parent.get_text(" ", strip=True))
    all_text = " ".join(part for part in text_parts if part)
    if _OUT_OF_STOCK_RE.search(all_text):
        return "out_of_stock"
    if _IN_STOCK_RE.search(all_text):
        return "in_stock"
    return "unknown"


def _extract_price(container: Tag) -> float | None:
    """Find the nearest price within the same container."""
    price_tag: Tag | None = None
    # Check the container itself first
    classes = container.get("class", "")
    class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
    if re.search(r"price|amount|cost|value", class_str, re.IGNORECASE) or container.get("data-price") is not None:
        price_tag = container
    else:
        price_tag = container.find(
            attrs={"class": re.compile(r"price|amount|cost|value", re.IGNORECASE)},
        )
    if price_tag is None:
        price_tag = container.find(attrs={"data-price": True})
    if price_tag is None:
        return None
    text = price_tag.get("data-price") or price_tag.get_text(strip=True)
    try:
        clean = re.sub(r"[^\d.]", "", str(text))
        return float(clean) if clean else None
    except ValueError:
        return None


def _extract_select_variants(soup: BeautifulSoup) -> tuple[list[VariantGroup], list[dict[str, Any]]]:
    """Extract variants from ``<select>`` elements."""
    groups: list[VariantGroup] = []
    variants: list[dict[str, Any]] = []
    for select in soup.find_all("select"):
        class_attr = select.get("class", "")
        class_str = " ".join(class_attr) if isinstance(class_attr, list) else str(class_attr)
        name_str = str(select.get("name", ""))
        parent = select.find_parent()
        parent_classes = parent.get("class", "") if parent else ""
        parent_class_str = " ".join(parent_classes) if isinstance(parent_classes, list) else str(parent_classes)
        selector_context = f"{class_str} {name_str} {parent_class_str}"
        all_opt_text = " ".join(opt.get_text(strip=True) for opt in select.find_all("option"))

        if not _VARIANT_CONTAINER_RE.search(selector_context) and not _VARIANT_CONTAINER_RE.search(all_opt_text):
            continue
        price = _extract_price(parent) if parent else None
        variant_type = _infer_variant_type(f"{class_str} {parent_class_str}", name_str) or "unknown"
        options: list[str] = []
        selected: str | None = None
        for opt in select.find_all("option"):
            label = opt.get_text(strip=True)
            if not label or label.startswith(("--", "Select")):
                continue
            options.append(label)
            availability = _classify_availability(opt)
            variant_record: dict[str, Any] = {
                "variant_type": variant_type,
                "option": label,
                "availability": availability,
            }
            if price is not None:
                variant_record["price"] = price
            variants.append(variant_record)
            if opt.get("selected") is not None:
                selected = label
        if options:
            groups.append(VariantGroup(variant_type=variant_type, options=list(options), selected=selected))
    return groups, variants


def _extract_radio_variants(soup: BeautifulSoup) -> tuple[list[VariantGroup], list[dict[str, Any]]]:
    """Extract variants from ``<input type="radio">`` groups."""
    groups: list[VariantGroup] = []
    variants: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for radio in soup.find_all("input", {"type": "radio"}):
        name = radio.get("name", "")
        if not name or name in seen_names:
            continue
        name_lower = name.lower()
        if not _VARIANT_CONTAINER_RE.search(name_lower):
            continue
        seen_names.add(name)
        variant_type = _infer_variant_type("", name) or "unknown"
        # Gather all radios in the same named group
        siblings = soup.find_all("input", {"type": "radio", "name": name})
        options = []
        selected = None
        for radio in siblings:
            label = radio.get("value") or radio.get("aria-label", "")
            if not label:
                continue
            options.append(label)
            parent = radio.find_parent()
            price = _extract_price(parent) if parent else None
            availability = _classify_availability(radio)
            vr: dict[str, Any] = {"variant_type": variant_type, "option": label, "availability": availability}
            if price is not None:
                vr["price"] = price
            variants.append(vr)
            if radio.get("checked") is not None:
                selected = label
        if options:
            groups.append(VariantGroup(variant_type=variant_type, options=list(options), selected=selected))
    return groups, variants


def _extract_button_variants(soup: BeautifulSoup) -> tuple[list[VariantGroup], list[dict[str, Any]]]:
    """Extract variants from ``<button>`` elements inside ``[data-variant]`` containers."""
    groups: list[VariantGroup] = []
    variants: list[dict[str, Any]] = []
    for container in soup.find_all(attrs={"data-variant": True}):
        variant_type = _infer_variant_type(" ".join(container.get("class", [])), container.get("data-variant", "")) or "unknown"
        buttons = container.find_all("button")
        if not buttons:
            continue
        options = []
        for btn in buttons:
            label = btn.get_text(strip=True)
            if not label:
                continue
            options.append(label)
            availability = _classify_availability(btn)
            vr: dict[str, Any] = {"variant_type": variant_type, "option": label, "availability": availability}
            price = _extract_price(btn)
            variant_container = btn.find_parent()
            if price is None and variant_container is not None and variant_container is not container:
                price = _extract_price(variant_container)
            if price is not None:
                vr["price"] = price
            variants.append(vr)
        if options:
            groups.append(VariantGroup(variant_type=variant_type, options=list(options)))
    return groups, variants


def extract_variants(
    html: str,
    *,
    base_record: dict[str, Any] | None = None,
) -> VariantExtractionResult:
    """Extract e-commerce variants from an HTML product page.

    Args:
        html: Raw HTML of the product page. Must be parseable
            (even if it only contains the product card section).
        base_record: Fields already extracted from the parent
            product page (price, title, description, etc.). If
            supplied, each variant record copies these fields.

    Returns:
        :class:`VariantExtractionResult` - base_record + flat
        variant list + typed variant groups.
    """
    soup = BeautifulSoup(html, "html.parser")
    base = dict(base_record) if base_record else {}

    all_variants: list[dict[str, Any]] = []
    all_groups: list[VariantGroup] = []
    for extractor in (_extract_select_variants, _extract_radio_variants, _extract_button_variants):
        groups, variants = extractor(soup)
        all_groups.extend(groups)
        all_variants.extend(variants)

    # Merge base_record fields into each variant so the caller gets complete records.
    enriched = [{**base, **v} for v in all_variants]

    return VariantExtractionResult(
        base_record=base,
        variants=enriched,
        variant_groups=all_groups,
    )
