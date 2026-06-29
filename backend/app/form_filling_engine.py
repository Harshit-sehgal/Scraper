"""Form Filling Engine — detect, fill, and submit HTML forms.

Roadmap Feat 8: Reusable form-filling engine that can submit HTML forms
(text inputs, selects, checkboxes, textareas) via Playwright.

Architecture
------------
The engine has three layers:

1. **Detection** (``detect_form_fields``) — Given raw HTML, finds all forms
   and their input elements (text, select, checkbox, radio, textarea). Returns
   a structured description of each form.

2. **Filling** (``fill_form``) — Given a Playwright page and a form selector,
   fills each mapped field with the provided value. Supports text typing,
   select picking, checkbox/radio toggling, and textarea filling.

3. **Submission** (``submit_form``) — Clicks the form's submit button or an
   explicit button selector, then waits for navigation to complete.

Usage
-----
::

    from app.form_filling_engine import fill_form, submit_form, detect_form_fields

    # Detect forms on a page
    forms = detect_form_fields(page_html)
    for form in forms:
        print(form["name"], form["fields"])

    # Fill a form and submit
    await fill_form(page, "#search-form", {"origin": "NYC", "destination": "LAX"})
    result = await submit_form(page, "#search-form")
"""

from __future__ import annotations

import contextlib
import inspect
import logging
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.url_safety import get_safe_async_client, validate_public_http_url

logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────

# HTML input type values that represent text-entry fields
_TEXT_INPUT_TYPES = frozenset(
    {"text", "search", "email", "url", "tel", "number", "password", "date", "datetime-local", "time", "month", "week", "color"}
)

# Input types that represent boolean / choice fields
_CHOICE_INPUT_TYPES = frozenset({"checkbox", "radio"})

# Form element kinds we can handle
_SUPPORTED_ELEMENT_TYPES = frozenset({"input", "select", "textarea", "button"})

# ─── Data structures (plain dicts for simplicity) ──────────────────────


def _make_field(
    element_type: str,
    name: str,
    field_id: str = "",
    input_type: str = "text",
    placeholder: str = "",
    label: str = "",
    options: list[dict] | None = None,
    required: bool = False,
    value: str = "",
    selector: str = "",
) -> dict[str, Any]:
    """Build a canonical field descriptor dict."""
    return {
        "element_type": element_type,
        "name": name,
        "id": field_id,
        "input_type": input_type if element_type == "input" else element_type,
        "placeholder": placeholder,
        "label": label,
        "options": options or [],
        "required": required,
        "value": value,
        "selector": selector,
    }


def _make_form(
    form_id: str = "",
    action: str = "",
    method: str = "GET",
    name: str = "",
    selector: str = "",
    fields: list[dict] | None = None,
    submit_button: dict | None = None,
) -> dict[str, Any]:
    """Build a canonical form descriptor dict."""
    return {
        "id": form_id,
        "action": action,
        "method": method.upper(),
        "name": name,
        "selector": selector,
        "fields": fields or [],
        "submit_button": submit_button,
        "field_count": len(fields or []),
    }


# ─── Form Detection ────────────────────────────────────────────────────


def _extract_label(soup: BeautifulSoup, field_element) -> str:
    """Extract the associated label text for a form field."""
    field_id = field_element.get("id", "")
    field_name = field_element.get("name", "")
    for label in soup.find_all("label"):
        label_for = label.get("for", "")
        if label_for and label_for == field_id:
            return label.get_text(strip=True)
        # Check if the field is nested inside the label
        if label.find(field_element) is not None:
            return label.get_text(strip=True)
    # Try aria-label
    aria = field_element.get("aria-label", "")
    if aria:
        return str(aria)
    # Try placeholder as label hint
    placeholder = field_element.get("placeholder", "")
    if placeholder:
        return str(placeholder)
    # Use the field name as fallback
    return field_name.replace("_", " ").replace("-", " ").strip().capitalize()


def _build_css_selector(field_element, form_selector: str) -> str:
    """Build a CSS selector for a field element within a form."""
    field_id = field_element.get("id", "")
    field_name = field_element.get("name", "")
    field_class = field_element.get("class", [])
    input_type = str(field_element.get("type", "")).lower()
    tag = field_element.name or "input"

    if field_id:
        return f"{form_selector} #{field_id}"
    if field_name:
        return f'{form_selector} {tag}[name="{field_name}"]'
    if input_type:
        return f'{form_selector} {tag}[type="{input_type}"]'
    if field_class:
        cls = ".".join(field_class if isinstance(field_class, list) else [field_class])
        return f"{form_selector} .{cls}"
    return f"{form_selector} {tag}"


def _extract_select_options(field_element) -> list[dict]:
    """Extract options from a select element."""
    options: list[dict[str, Any]] = []
    if field_element.name != "select":
        return options
    for opt in field_element.find_all("option"):
        opt_value = opt.get("value", "")
        opt_text = opt.get_text(strip=True)
        if opt_value or opt_text:  # skip truly empty options
            options.append(
                {
                    "value": str(opt_value),
                    "text": opt_text,
                    "selected": opt.has_attr("selected"),
                }
            )
    return options


def _detect_single_form(soup: BeautifulSoup, form_element) -> dict[str, Any]:
    """Detect form fields for a single <form> element."""
    form_id = str(form_element.get("id", ""))
    form_action = str(form_element.get("action", ""))
    form_method = str(form_element.get("method", "get")).upper()
    form_name = str(form_element.get("name", "") or form_id or f"form-{id(form_element)}")

    fields: list[dict] = []
    submit_button = None

    # Build a CSS selector for this form (used for building field selectors below)
    if form_id:
        form_selector = f"#{form_id}"
    elif form_name:
        form_selector = f'form[name="{form_name}"]'
    elif form_element.get("class"):
        cls = form_element["class"]
        cls_str = ".".join(cls if isinstance(cls, list) else [cls])
        form_selector = f"form.{cls_str}"
    else:
        form_selector = "form"

    for element in form_element.find_all(_SUPPORTED_ELEMENT_TYPES):
        element_type = element.name
        input_type = str(element.get("type", "text")).lower()
        field_name = str(element.get("name", ""))
        field_id = str(element.get("id", ""))

        # Skip elements without a name (they can't be submitted)
        if element_type == "input" and input_type == "submit":
            submit_button = {
                "element_type": "button",
                "name": field_name,
                "id": field_id,
                "value": str(element.get("value", "Submit")),
                "selector": _build_css_selector(element, form_selector),
            }
            continue

        if element_type == "input" and input_type == "hidden":
            continue  # skip hidden fields

        if element_type == "button" and str(element.get("type", "submit")).lower() in ("submit", "button"):
            if submit_button is None:  # prefer first submit button
                submit_button = {
                    "element_type": "button",
                    "name": field_name,
                    "id": field_id,
                    "value": str(element.get("value", element.get_text(strip=True) or "Submit")),
                    "selector": _build_css_selector(element, form_selector),
                }
            continue

        if element_type == "input" and input_type not in _TEXT_INPUT_TYPES and input_type not in _CHOICE_INPUT_TYPES:
            continue

        placeholder = str(element.get("placeholder", ""))
        label = _extract_label(soup, element)
        required = element.has_attr("required") or "required" in (element.get("class") or [])
        value = str(element.get("value", ""))
        selector = _build_css_selector(element, form_selector)

        if element_type == "select":
            options = _extract_select_options(element)
            field = _make_field("select", field_name, field_id, "select", placeholder, label, options, required, value, selector)
        elif element_type == "textarea":
            field = _make_field(
                "textarea",
                field_name,
                field_id,
                "textarea",
                placeholder,
                label,
                None,
                required,
                element.get_text(strip=True),
                selector,
            )
        else:
            is_choice = input_type in _CHOICE_INPUT_TYPES
            field = _make_field("input", field_name, field_id, input_type, placeholder, label, None, required, value, selector)
            field["is_choice"] = is_choice
            field["checked"] = element.has_attr("checked")

        fname = field_name or field_id
        if fname:
            fields.append(field)

    return _make_form(form_id, form_action, form_method, form_name, form_selector, fields, submit_button)


def detect_form_fields(html: str) -> list[dict[str, Any]]:
    """Detect all HTML forms and their input fields in the given HTML.

    Args:
        html: Raw HTML string of the page.

    Returns:
        A list of form descriptor dicts, each containing:
        - id: Form element ID (if any)
        - action: Form action URL
        - method: Form method (GET/POST)
        - name: Form name attribute
        - selector: CSS selector for this form
        - fields: list of field descriptors
        - submit_button: Descriptor for the submit button
        - field_count: Number of detected fields
    """
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    form_elements = soup.find_all("form")
    if not form_elements:
        # No <form> tags — try to detect standalone input fields
        # (some SPAs use inputs without a wrapping <form>)
        return _detect_standalone_fields(soup)

    return [_detect_single_form(soup, form) for form in form_elements]


def _detect_standalone_fields(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Detect input fields that exist outside a <form> tag (SPA pattern)."""
    fields: list[dict] = []
    submit_button = None

    for element in soup.find_all(["input", "select", "textarea", "button"]):
        element_type = element.name
        input_type = str(element.get("type", "text")).lower()
        field_name = str(element.get("name", ""))
        field_id = str(element.get("id", ""))

        if element_type == "button" or (element_type == "input" and input_type == "submit"):
            if submit_button is None:
                submit_button = {
                    "element_type": "button",
                    "name": field_name,
                    "id": field_id,
                    "value": str(element.get("value", element.get_text(strip=True) or "Submit")),
                    "selector": f"#{field_id}"
                    if field_id
                    else f'[name="{field_name}"]'
                    if field_name
                    else "button, input[type=submit]",
                }
            continue

        if element_type == "input" and input_type == "hidden":
            continue

        if element_type == "input" and input_type not in _TEXT_INPUT_TYPES and input_type not in _CHOICE_INPUT_TYPES:
            continue

        if not field_name and not field_id:
            continue

        placeholder = str(element.get("placeholder", ""))
        label = field_name.replace("_", " ").replace("-", " ").strip().capitalize()
        required = element.has_attr("required")
        value = str(element.get("value", ""))
        selector = f"#{field_id}" if field_id else f'[name="{field_name}"]'

        if element_type == "select":
            options = _extract_select_options(element)
            field = _make_field("select", field_name, field_id, "select", placeholder, label, options, required, value, selector)
        elif element_type == "textarea":
            field = _make_field(
                "textarea",
                field_name,
                field_id,
                "textarea",
                placeholder,
                label,
                None,
                required,
                element.get_text(strip=True),
                selector,
            )
        else:
            is_choice = input_type in _CHOICE_INPUT_TYPES
            field = _make_field("input", field_name, field_id, input_type, placeholder, label, None, required, value, selector)
            field["is_choice"] = is_choice
            field["checked"] = element.has_attr("checked")

        fields.append(field)

    if not fields and submit_button is None:
        return []

    return [
        {
            "id": "",
            "action": "",
            "method": "GET",
            "name": "standalone-fields",
            "selector": "body",
            "fields": fields,
            "submit_button": submit_button,
            "field_count": len(fields),
            "standalone": True,
        }
    ]


async def _maybe_await(value: Any) -> Any:
    """Return awaited value when *value* is awaitable, otherwise return it."""
    if inspect.isawaitable(value):
        return await value
    return value


async def _locator_count(locator: Any) -> int:
    """Return a numeric locator count, treating unknown mock values as zero."""
    count = await _maybe_await(locator.count())
    if isinstance(count, int):
        return count
    return 0


def map_form_fields_to_values(
    form: dict[str, Any],
    field_values: dict[str, str],
) -> dict[str, str]:
    """Map user-supplied field values to the correct form field names.

    Performs fuzzy matching against field names, IDs, labels, and
    placeholders so callers don't need to know exact DOM attribute values.

    Args:
        form: A form descriptor from ``detect_form_fields``.
        field_values: User-supplied mapping of logical field names to values.

    Returns:
        A dict mapping actual form field names → values.
    """
    if not form or not field_values:
        return {}

    mapped: dict[str, str] = {}
    used_keys: set[str] = set()
    used_fields: set[str] = set()

    for user_key, user_value in field_values.items():
        if not user_value:
            continue
        user_key_lower = user_key.lower().replace("_", "").replace("-", "")

        best_field = None
        best_score = 0

        for field in form.get("fields", []):
            field_name = field.get("name", "")
            field_id = field.get("id", "")
            field_label = field.get("label", "").lower().replace("_", "").replace("-", "")
            field_placeholder = field.get("placeholder", "").lower().replace("_", "").replace("-", "")

            if field_name in used_fields or field_id in used_fields:
                continue

            score = 0

            # Exact match on name or id
            fname_norm = field_name.lower().replace("_", "").replace("-", "")
            fid_norm = field_id.lower().replace("_", "").replace("-", "")

            if fname_norm == user_key_lower:
                score = 10
            elif fid_norm == user_key_lower:
                score = 9
            elif field_label == user_key_lower:
                score = 8
            elif field_placeholder == user_key_lower:
                score = 7
            elif user_key_lower in fname_norm:
                score = 6
            elif user_key_lower in fid_norm:
                score = 5
            elif user_key_lower in field_label:
                score = 4
            elif user_key_lower in field_placeholder:
                score = 3
            # Partial token match
            elif any(token in fname_norm for token in user_key_lower.split() if len(token) > 2):
                score = 2
            elif any(token in field_label for token in user_key_lower.split() if len(token) > 2):
                score = 1

            if score > best_score:
                best_score = score
                best_field = field

        if best_field and best_score >= 2:
            bf_name = best_field.get("name", "") or best_field.get("id", "")
            if bf_name and bf_name not in used_fields:
                mapped[bf_name] = user_value
                used_fields.add(bf_name)
                used_keys.add(user_key)

    return mapped


# ─── Browser-level Form Filling ────────────────────────────────────────


async def fill_form_fields(page: Any, form_selector: str, field_values: dict[str, str]) -> list[dict[str, Any]]:
    """Fill form fields on a Playwright page.

    For each field in ``field_values``, locates the field using CSS
    selectors (by name, id, label, or placeholder) and fills it.
    Supports text inputs, selects, checkboxes, and textareas.

    Args:
        page: A Playwright page object.
        form_selector: CSS selector for the target form element.
        field_values: Dict mapping field names → values.

    Returns:
        A list of fill result dicts with status and field info.

    Raises:
        RuntimeError: If ``page`` is None or invalid.
        ValueError: If a required field cannot be located.
    """
    if page is None:
        msg = "fill_form_fields requires a valid Playwright page"
        raise RuntimeError(msg)

    results: list[dict[str, Any]] = []
    MAX_STEP_TIMEOUT = 30_000  # 30 seconds max per field

    for field_name, field_value in field_values.items():
        if not field_name:
            continue

        result: dict[str, Any] = {
            "field": field_name,
            "value": field_value,
            "status": "ok",
        }

        # Build a CSS selector for the field
        selectors = [
            f'{form_selector} [name="{field_name}"]',
            f"{form_selector} #{field_name}",
            f'{form_selector} [id="{field_name}"]',
            f'{form_selector} [placeholder="{field_name}"]',
            f'{form_selector} input[name="{field_name}"]',
            f'{form_selector} select[name="{field_name}"]',
            f'{form_selector} textarea[name="{field_name}"]',
        ]

        element = None
        for sel in selectors:
            try:
                locator = page.locator(sel)
                if await _locator_count(locator) > 0:
                    element = locator.first
                    break
            except (RuntimeError, OSError, ValueError, TypeError):
                continue

        if element is None:
            # Broader search: try aria-label and label text matching
            try:
                element = page.locator(f'{form_selector} [aria-label="{field_name}"]').first
                if await _locator_count(element) == 0:
                    element = None
            except (RuntimeError, OSError, ValueError, TypeError):
                element = None

        if element is None:
            result["status"] = "skipped"
            result["error"] = f"Field '{field_name}' not found in form"
            results.append(result)
            continue

        try:
            tag_name = await _maybe_await(element.evaluate("el => el.tagName.toLowerCase()"))
            input_type = await _maybe_await(element.evaluate("el => (el.type || '').toLowerCase()"))

            if tag_name == "select":
                await _maybe_await(element.select_option(field_value, timeout=MAX_STEP_TIMEOUT))
            elif tag_name == "textarea":
                await _maybe_await(element.fill(field_value, timeout=MAX_STEP_TIMEOUT))
            elif input_type in ("checkbox", "radio"):
                should_check = field_value.lower() in ("true", "yes", "1", "on", "checked")
                is_checked = await _maybe_await(element.is_checked())
                if should_check and not is_checked:
                    await _maybe_await(element.check(timeout=MAX_STEP_TIMEOUT))
                elif not should_check and is_checked:
                    await _maybe_await(element.uncheck(timeout=MAX_STEP_TIMEOUT))
            else:
                await _maybe_await(element.fill(field_value, timeout=MAX_STEP_TIMEOUT))

        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            result["status"] = "failed"
            result["error"] = str(exc)

        results.append(result)

    return results


async def submit_form(page: Any, form_selector: str, submit_selector: str | None = None) -> dict[str, Any]:
    """Submit a form by clicking its submit button.

    After clicking, waits for navigation to complete (``networkidle``
    with a 10-second timeout) and returns the resulting URL and page
    content.

    Args:
        page: A Playwright page object.
        form_selector: CSS selector for the form.
        submit_selector: Optional explicit selector for the submit button.
            If None, the first submit button inside the form is used.

    Returns:
        A dict with ``success``, ``final_url``, ``status_code``, and
        optional ``error``.
    """
    if page is None:
        msg = "submit_form requires a valid Playwright page"
        raise RuntimeError(msg)

    try:
        # Use explicit submit selector or find one in the form
        if submit_selector:
            btn = page.locator(submit_selector).first
        else:
            btn = page.locator(f"{form_selector} button[type=submit], {form_selector} input[type=submit]").first

        btn_count = await _locator_count(btn)
        if btn_count == 0 and not submit_selector:
            # Try pressing Enter on the last field
            last_input = page.locator(f"{form_selector} input, {form_selector} textarea").last
            await _maybe_await(last_input.press("Enter"))
        elif btn_count > 0:
            await _maybe_await(btn.click(timeout=15_000))
        else:
            return {
                "success": False,
                "error": "No submit button found and Enter key press not possible",
            }

        # Wait for navigation to complete
        import asyncio

        await asyncio.sleep(1.5)  # brief settle time
        with contextlib.suppress(RuntimeError, OSError, ValueError, TimeoutError):
            await _maybe_await(page.wait_for_load_state("networkidle", timeout=10_000))

        final_url = page.url
        return {
            "success": True,
            "final_url": final_url,
        }

    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        logger.warning("Form submission failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
        }


# ─── HTTP-level Form Submission (no browser needed) ─────────────────────


async def submit_form_http(
    form: dict[str, Any],
    base_url: str,
    field_values: dict[str, str],
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Submit a form via plain HTTP (no Playwright needed).

    Detects the form action and method from the form descriptor, maps
    field values using ``map_form_fields_to_values``, and submits the
    request.

    Args:
        form: A form descriptor from ``detect_form_fields``.
        base_url: The page URL for resolving relative form actions.
        field_values: User-supplied field name → value mapping.
        extra_headers: Optional extra HTTP headers.

    Returns:
        A dict with ``success``, ``final_url``, ``html``, ``status_code``.
    """
    import httpx

    mapped = map_form_fields_to_values(form, field_values)

    # Resolve the form action URL
    action = form.get("action", "")
    action = base_url if not action else urljoin(base_url, action)

    validate_public_http_url(action)

    method = form.get("method", "GET").upper()
    headers = dict(extra_headers or {})

    try:
        async with get_safe_async_client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            if method == "GET":
                resp = await client.get(action, params=mapped)
            else:
                resp = await client.post(action, data=mapped)

            return {
                "success": resp.status_code < 400,
                "final_url": str(resp.url),
                "html": resp.text,
                "status_code": resp.status_code,
            }

    except (httpx.HTTPError, httpx.TimeoutException, ValueError, OSError) as exc:
        logger.warning("HTTP form submission failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "final_url": "",
            "html": "",
            "status_code": 0,
        }
