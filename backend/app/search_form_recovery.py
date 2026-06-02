"""Search form detection and POST recovery for expired session URLs.

Extracted from selector_discovery_url.py for modularity.

Ownership boundary: detects HTML search forms, builds absolute URLs,
maps search parameters to form fields, and attempts POST/GET recovery.
Value classification lives in url_value_classification.py; content
quality in content_quality.py.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ─── Search Form Detection ──────────────────────────────────────────────


def _detect_search_form(html: str) -> dict:
    """Detect search forms on a page and extract their field structure.

    Scans the page HTML for forms that look like search / query forms
    (text inputs with location, date, or search-related names / placeholders),
    and returns a structured description of the form fields, action URL,
    and method. Fully generic — works with any site, no hardcoded values.

    Args:
        html: The page HTML content

    Returns:
        dict with:
        - detected: bool
        - action: str
        - method: str
        - fields: list of dicts with {id, name, type, placeholder}
        - search_fields: list of field dicts identified as search-relevant
    """
    soup = BeautifulSoup(html, "html.parser")
    forms = soup.find_all("form")

    SEARCH_FIELD_NAMES: set[str] = {
        "from", "to", "source", "target", "location", "place",
        "city", "date", "query", "search", "q", "keyword",
    }
    SEARCH_PLACEHOLDER_PATTERNS: list[str] = [
        r"from|to", r"location|place", r"date|when",
        r"search|find", r"keyword|query",
    ]

    best_form = None
    best_fields: list[dict] = []
    best_form_score = 0

    for form in forms:
        inputs = form.find_all("input")
        selects = form.find_all("select")
        all_inputs = list(inputs) + list(selects)

        if not all_inputs:
            continue

        fields: list[dict] = []
        search_inputs: list[dict] = []
        form_score = 0

        for inp in all_inputs:
            tag_name = inp.name
            field_id = inp.get("id", "") or ""
            field_name = inp.get("name", "") or ""
            field_type = inp.get("type", "text") if tag_name == "input" else "select"
            placeholder = inp.get("placeholder", "") or ""

            input_type_lower = field_type.lower()
            if input_type_lower not in ("", "text", "search", "date", "datetime-local", "tel", "number"):
                continue

            field_entry = {
                "id": field_id,
                "name": field_name or field_id,
                "type": field_type,
                "placeholder": placeholder,
            }
            fields.append(field_entry)

            name_lower = field_name.lower()
            id_lower = field_id.lower()
            placeholder_lower = placeholder.lower()

            for keyword in SEARCH_FIELD_NAMES:
                if keyword in name_lower or keyword in id_lower:
                    form_score += 2
                    break

            for pattern in SEARCH_PLACEHOLDER_PATTERNS:
                if re.search(pattern, placeholder_lower, re.IGNORECASE):
                    form_score += 2
                    break

            is_search_relevant = False
            for keyword in SEARCH_FIELD_NAMES:
                if keyword in name_lower or keyword in id_lower or keyword in placeholder_lower:
                    is_search_relevant = True
                    break
            if is_search_relevant:
                search_inputs.append(field_entry)

        if search_inputs:
            form_score += len(search_inputs) * 3

        if form_score > best_form_score:
            best_form_score = form_score
            best_form = form
            best_fields = fields

    if best_form is None or best_form_score < 3:
        return {
            "detected": False,
            "action": "",
            "method": "",
            "fields": [],
            "search_fields": [],
        }

    action = best_form.get("action", "") or ""
    method = (best_form.get("method", "post") or "post").upper()

    return {
        "detected": True,
        "action": action.strip(),
        "method": method,
        "fields": best_fields,
        "search_fields": search_inputs,
    }


# ─── Search Form POST Recovery ─────────────────────────────────────────


def _build_absolute_url(base_url: str, action: str) -> str:
    """Build an absolute URL from a base URL and potentially relative action."""
    from urllib.parse import urljoin, urlparse

    if action.startswith("http://") or action.startswith("https://"):
        return action
    if action.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{action}"
    return urljoin(base_url.rstrip("/") + "/", action.lstrip("/"))


def _map_search_params_to_fields(
    search_params: dict[str, str],
    form_fields: list[dict],
) -> dict[str, str]:
    """Map user-provided search parameters to form field names.

    Uses fuzzy matching of field names, IDs, and placeholders to find
    the best field for each search parameter. No hardcoded field names.

    Args:
        search_params: User-provided params like {"origin": "NYC", "destination": "LHR"}
        form_fields: Detected form fields from _detect_search_form()

    Returns:
        dict mapping form field names → values
    """
    mapped: dict[str, str] = {}

    param_variants: dict[str, list[str]] = {
        "query": ["query", "search", "q", "keyword"],
        "location": ["location", "place", "city"],
        "origin": ["origin", "from", "source", "departure", "depart", "start"],
        "destination": ["destination", "to", "target", "arrival", "arrive", "end"],
        "from": ["from", "origin", "source", "departure", "depart", "start"],
        "to": ["to", "destination", "target", "arrival", "arrive", "end"],
        "date": ["date", "when"],
        "departure_date": ["departure_date", "departuredate", "departdate", "depart", "startdate", "date"],
        "depart_date": ["depart_date", "departuredate", "departdate", "depart", "startdate", "date"],
        "return_date": ["return_date", "returndate", "return", "enddate", "date"],
        "arrival_date": ["arrival_date", "arrivaldate", "arrivedate", "arrival", "enddate", "date"],
    }

    used_fields: set[str] = set()

    for param_key, value in search_params.items():
        if not value:
            continue
        param_lower = param_key.lower().replace("_", "").replace("-", "")

        variant_keywords = param_variants.get(param_key.lower(), [param_lower])

        best_match = None
        best_score = 0

        for field in form_fields:
            field_name = field.get("name", "").lower().replace("_", "").replace("-", "")
            field_id = field.get("id", "").lower().replace("_", "").replace("-", "")
            placeholder = field.get("placeholder", "").lower().replace("_", "").replace("-", "")

            if field_name in used_fields or field_id in used_fields:
                continue

            for kw in variant_keywords:
                score = 0
                kw_norm = kw.lower().replace("_", "").replace("-", "")
                if kw_norm == field_name or kw_norm == field_id:
                    score = 10
                elif kw_norm in field_name or kw_norm in field_id:
                    score = 5
                elif kw_norm in placeholder:
                    score = 3

                if score > best_score:
                    best_score = score
                    best_match = field

        if best_match:
            form_field_name = best_match.get("name", "") or best_match.get("id", "")
            if form_field_name:
                mapped[form_field_name] = value
                used_fields.add(form_field_name)
                used_fields.add(best_match.get("id", ""))

    return mapped


async def _try_form_search_recovery(
    landing_page_html: str,
    landing_page_url: str,
    search_params: dict[str, str],
) -> dict:
    """Try to recover from an expired session URL by submitting the site's
    search form programmatically.

    Detects the search form on the landing page, maps user-provided
    search parameters to form fields, POSTs to the form action, and
    follows redirects to the fresh session results page.

    Fully generic — works with any site that has a search form, no
    hardcoded domains or field names.

    Args:
        landing_page_html: HTML of the landing / homepage (after redirect)
        landing_page_url: URL of the landing page (for resolving relative actions)
        search_params: Dict of search parameters
            (e.g. {"origin": "NYC", "destination": "LHR", "departure_date": "05 / 15 / 2026"})

    Returns:
        dict with:
        - success: bool
        - fresh_url: str
        - fresh_html: str
        - form_detected: bool
        - form_info: dict
        - error: str | None
    """
    import httpx

    from app.url_safety import validate_public_http_url

    # Step 1: Detect the search form
    form_info = _detect_search_form(landing_page_html)
    if not form_info["detected"]:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": False,
            "form_info": form_info,
            "error": "No search form detected on the landing page — cannot recover expired session",
        }

    # Step 2: Map user search params to form field names
    form_action = form_info["action"]
    form_method = form_info["method"]
    form_fields = form_info["fields"]

    mapped_params = _map_search_params_to_fields(search_params, form_fields)

    if not mapped_params:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": True,
            "form_info": form_info,
            "error": (
                f"Found a search form at '{form_action}' but could not map your "
                f"search parameters to form fields. Detected form fields: "
                f"{[f['name'] or f['id'] for f in form_fields]}. "
                f"Try using field names like: origin, destination, departure_date."
            ),
        }

    # Build absolute form action URL
    absolute_action = _build_absolute_url(landing_page_url, form_action)

    # SSRF: Validate absolute form action URL before submission
    try:
        validate_public_http_url(absolute_action)
    except ValueError as e:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": True,
            "form_info": form_info,
            "error": f"Search form action URL '{absolute_action}' failed security check: {e}",
        }

    logger.info("[SearchRecovery] POSTing to %s with params: %s", absolute_action, mapped_params)

    # Step 3: Submit the form
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(30.0),
        ) as client:
            if form_method == "GET":
                resp = await client.get(absolute_action, params=mapped_params)
            else:
                resp = await client.post(absolute_action, data=mapped_params)

            max_redirects = 10
            redirects_followed = 0
            while resp.is_redirect:
                redirects_followed += 1
                if redirects_followed > max_redirects:
                    raise ValueError(f"Too many redirects (max {max_redirects})")

                redirect_target = resp.headers.get("location", "")
                if not redirect_target:
                    break

                from urllib.parse import urljoin

                redirect_url = urljoin(str(resp.url), redirect_target)
                validate_public_http_url(redirect_url)
                resp = await client.get(redirect_url)

            fresh_url = str(resp.url)
            validate_public_http_url(fresh_url)
            fresh_html = resp.text

            if resp.status_code >= 400:
                return {
                    "success": False,
                    "fresh_url": fresh_url,
                    "fresh_html": fresh_html,
                    "form_detected": True,
                    "form_info": form_info,
                    "error": f"Search form submission returned HTTP {resp.status_code}",
                }

            logger.info("[SearchRecovery] Form submitted successfully → %s (status %d)", fresh_url, resp.status_code)

            return {
                "success": True,
                "fresh_url": fresh_url,
                "fresh_html": fresh_html,
                "form_detected": True,
                "form_info": form_info,
                "error": None,
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": True,
            "form_info": form_info,
            "error": "Search form submission timed out after 30 seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "fresh_url": landing_page_url,
            "fresh_html": "",
            "form_detected": True,
            "form_info": form_info,
            "error": f"Search form submission failed: {str(e)}",
        }
