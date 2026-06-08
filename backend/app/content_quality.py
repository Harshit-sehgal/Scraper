"""Content quality assessment for scraped pages.

Extracted from selector_discovery_url.py for modularity.

Ownership boundary: assesses page content quality, detects landing pages,
extracts container text values. Redirect detection lives in url_redirects.py.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

# ─── Content Quality Assessment ────────────────────────────────────────


def _assess_content_quality(html: str, profile) -> dict:
    """Assess whether the fetched page contains meaningful data containers.

    Detects landing pages (hero banners, search forms, welcome text),
    empty / poor pages (no repeating data containers), and pages with real
    extractable data.

    Works with ANY StructureProfile — no domain-specific assumptions.
    When the profile's container selector doesn't find enough data, falls
    back to scanning the page for repeating element patterns generically.

    Args:
        html: The page HTML content
        profile: A StructureProfile object (from page_profiler.detect_page_structure)

    Returns:
        dict with:
        - quality: str (good|low|landing_page)
        - has_data_containers: bool
        - is_landing_page: bool
        - data_container_count: int
        - landing_signals: list of detected landing page indicators
        - message: str

    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Landing Page Detection ──────────────────────────────────────
    landing_signals: list[str] = []

    # Hero / banner sections (generic selectors, no hardcoded domain)
    hero_selectors = [
        ".hero",
        ".banner",
        ".jumbotron",
        ".landing",
        ".cover",
        "[class*='hero']",
        "[class*='banner']",
        "[class*='landing']",
        "[class*='jumbotron']",
    ]
    for sel in hero_selectors:
        try:
            if soup.select(sel):
                landing_signals.append("hero_banner")
                break
        except Exception:  # noqa: RUF100, S112
            continue  # nosec B112

    # Search forms (generic — any form with text / search input)
    forms = soup.find_all("form")
    search_form_found = False
    for form in forms:
        inputs = form.find_all("input")
        for inp in inputs:
            type_attr = inp.get("type", "") or ""
            input_type = (type_attr[0] if isinstance(type_attr, list) else str(type_attr)).lower()
            if input_type in ("", "text", "search"):
                search_form_found = True
                break
        if search_form_found:
            break
    if search_form_found:
        landing_signals.append("search_form")

    # Welcome / landing page text patterns (generic, domain-agnostic)
    body_text = soup.get_text().lower()[:2000]
    welcome_patterns = [
        "welcome",
        "find your",
        "search for",
        "get started",
        "start your",
        "explore",
        "discover",
        "find the best",
        "looking for",
    ]
    for pattern in welcome_patterns:
        if pattern in body_text:
            landing_signals.append(f"landing_text:{pattern}")
            break  # One landing text signal is enough

    # ── Data Container Detection ────────────────────────────────────
    data_container_count = 0
    has_profile_selector = profile is not None and hasattr(profile, "container_selector")
    container_selector = profile.container_selector if has_profile_selector else None

    if container_selector and container_selector != "body":
        try:
            containers = soup.select(container_selector)
            data_container_count = sum(1 for c in containers if len(c.get_text(strip=True)) > 20)
        except Exception:  # noqa: RUF100, S110
            pass  # nosec B110

    # ── Generic Data Container Discovery (fallback) ─────────────────
    # When profile's container selector finds little, scan for repeating
    # element patterns across the full DOM (no hardcoded selectors).
    if data_container_count < 3:
        from collections import Counter as _Counter

        tag_class_counts: _Counter = _Counter()
        for tag in soup.find_all(True):
            if tag.name in ("script", "style", "noscript", "svg", "form", "nav", "footer", "header"):
                continue
            cls_val = tag.get("class")
            classes = " ".join(cls_val) if isinstance(cls_val, list) else (str(cls_val) if cls_val else "")
            if classes:
                key = f"{tag.name}.{'.'.join(classes.split()[:2])}"
                tag_class_counts[key] += 1

        # Find patterns with many repetitions (3+) — likely data containers
        for pattern, count in tag_class_counts.most_common(20):
            if count < 3:
                continue
            try:
                # Build a rough CSS selector from the pattern
                css_sel = pattern
                matching = soup.select(css_sel)
                content_count = sum(1 for m in matching if len(m.get_text(strip=True)) > 20)
                data_container_count = max(data_container_count, content_count)
            except Exception:  # noqa: RUF100, S112
                continue  # nosec B112

        # Also scan for repeating direct children of common containers
        for container_tag in ["div", "li", "article", "section", "tr"]:
            parents = soup.find_all(container_tag, limit=10)
            for parent in parents:
                children = parent.find_all(recursive=False)
                if len(children) >= 3:
                    child_classes = []
                    for c in children:
                        cls_val = c.get("class")
                        cls_str = " ".join(cls_val) if isinstance(cls_val, list) else (str(cls_val) if cls_val else "")
                        child_classes.append(cls_str)
                    unique_classes = len(set(child_classes))
                    if unique_classes <= 2:
                        data_container_count = max(data_container_count, len(children))

    # ── Classification ──────────────────────────────────────────────
    is_landing_page = len(landing_signals) >= 2 or (len(landing_signals) >= 1 and data_container_count < 3)

    if is_landing_page:
        return {
            "quality": "landing_page",
            "has_data_containers": data_container_count >= 3,
            "is_landing_page": True,
            "data_container_count": data_container_count,
            "landing_signals": landing_signals,
            "message": (
                f"This appears to be a landing or homepage (signals: "
                f"{', '.join(landing_signals)}), not a data results page "
                f"with extractable records."
            ),
        }

    if data_container_count >= 3:
        return {
            "quality": "good",
            "has_data_containers": True,
            "is_landing_page": False,
            "data_container_count": data_container_count,
            "landing_signals": landing_signals,
            "message": f"Found {data_container_count} data containers on the page with good extraction potential.",
        }

    return {
        "quality": "low",
        "has_data_containers": False,
        "is_landing_page": False,
        "data_container_count": data_container_count,
        "landing_signals": landing_signals,
        "message": "No repeating data containers detected on this page — content may be too sparse for extraction.",
    }


def _extract_container_text_values(html: str, container_selector: str) -> list[str]:
    """Extract meaningful, distinct text values from the first data container.

    Walks the container's DOM tree collecting leaf-level text values
    (short, individual text nodes) rather than concatenated full text.
    Also collects img alt texts.
    """
    soup = BeautifulSoup(html, "html.parser")
    containers: list = soup.select(container_selector)

    # Fallback: scan all visible elements
    if not containers:
        containers = [soup]

    container = containers[0]
    values = []
    seen = set()

    for tag in container.find_all(True):
        if tag.name in ("script", "style", "noscript", "svg", "form", "nav", "footer", "header"):
            continue

        text = tag.get_text(strip=True)
        if not text or len(text) < 2:
            continue

        norm = text.lower()
        if norm in seen:
            continue
        seen.add(norm)

        # Skip if this tag's text is entirely from a single child (not a leaf)
        children = tag.find_all(True, recursive=False)
        if len(children) == 1:
            child_text = children[0].get_text(strip=True)
            if child_text and child_text == text:
                continue

        # Skip very long text (likely descriptions, not field values)
        if len(text) > 100:
            continue

        values.append(text)

    # Add alt texts from images
    for img in container.find_all("img"):
        alt = img.get("alt", "").strip()
        if alt and len(alt) > 2 and alt.lower() not in seen:
            seen.add(alt.lower())
            values.append(alt)

    return values
