"""
Scraping engine with LLM-guided selector mapping, schema-aware cleanup,
record quality scoring, and optional Groq support.

Now using universal intent-driven extraction layers:
- intent_parser: Parse user intent to semantic needs
- page_profiler: Detect page structure and value patterns  
- semantic_mapper: Match values to intent by meaning
- validation: Confidence scoring and validation
"""

import asyncio
import json
import os
import re
import time
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.async_utils import run_sync_in_thread
from app.models import FieldType, SchemaField

# Import new universal layers
from app.intent_parser import parse_user_intent, infer_schema_from_intent, get_universal_schema
from app.page_profiler import detect_page_structure, detect_value_patterns, find_data_containers
from app.semantic_mapper import match_values_to_intent, map_to_schema_fields, ai_repair_mapping
from app.validation import validate_records, compute_field_confidence, DEFAULT_MIN_CONFIDENCE
from app.semantic_segmentation import (
    expand_composite_records,
    is_likely_noise_field,
    segment_single_text,
    compute_semantic_density,
    StructuralMemoryTracker,
)
from app.semantic_pipeline import run_pipeline, strip_metadata, filter_noise_records

EMPTY_TOKENS = {
    "home",
    "about",
    "contact",
    "blog",
    "careers",
    "services",
    "gallery",
    "products",
    "offers",
    "projects",
    "sitemap",
    "privacy",
    "terms",
    "faq",
    "faq's",
    "faqs",
    "testimonials",
    "company",
}

COMPANY_NAME_NOISE = {
    "all filters",
}

NAME_FIELD_NOISE_PREFIXES = {
    "location",
    "rating",
    "any rating",
    "use my current location",
    "nearby locations",
}

LIKELY_LOCATION_WORDS = set()

PLACEHOLDER_PHRASES = {
    "click here",
    "read more",
    "learn more",
    "view more",
    "view details",
    "see more",
    "contact us",
    "call now",
    "book now",
    "know more",
    "details",
    "more",
}

ROW_NOISE_PHRASES = {
    "email us",
    "contact us",
    "popular choices",
    "useful links",
    "selling tools",
    "starting from",
    "years of experience",
}

AI_STRUCTURING_MAX_RECORDS = 240
AI_STRUCTURING_CHUNK_SIZE = 30
AI_STRUCTURING_CHUNK_TIMEOUT_SECONDS = 12
AI_SOURCE_STRUCTURING_TIMEOUT_SECONDS = 60


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


MAX_RECORDS_PER_SOURCE = _env_int("DATAFORGE_MAX_RECORDS_PER_SOURCE", 25, 5, 250)
AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES = _env_int(
    "DATAFORGE_AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES", 5, 1, 20
)


def _normalized_text_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").strip().lower()).strip()


def _is_placeholder_value(text: str) -> bool:
    key = _normalized_text_key(text)
    if not key:
        return True
    if key in EMPTY_TOKENS or key in PLACEHOLDER_PHRASES:
        return True
    if key.endswith(" page") and key.split()[0] in EMPTY_TOKENS:
        return True
    if key.startswith(("click ", "read ", "view ")):
        return True
    if re.fullmatch(r"\d+\s+more", key):
        return True
    return False


def _is_entity_name_field(field_name: str) -> bool:
    name = (field_name or "").lower()
    return any(token in name for token in ["company", "name", "title", "entity"])


def _is_noise_name_value(text: str) -> bool:
    val = _compact_text(text).lower()
    if not val:
        return True
    if _is_placeholder_value(val):
        return True
    if val in LIKELY_LOCATION_WORDS:
        return True
    if any(val.startswith(prefix) for prefix in NAME_FIELD_NOISE_PREFIXES):
        return True
    if re.search(r"\(\d+\)$", val):
        return True
    if any(token in val for token in ["show all", "nearby locations", "use my current location"]):
        return True
    return False


def _is_likely_noise_entity(text: str) -> bool:
    """Check if text is noise using semantic density analysis."""
    is_noise, conf, evidence = is_likely_noise_field("name", text)
    return is_noise


def _is_likely_noise_row(record: dict, schema_fields: list[SchemaField]) -> bool:
    """Determine if a record is noise using semantic density and structural analysis.

    Replaces hardcoded phrase lists with:
    - Semantic density analysis
    - Structural repetition checks
    - Content entropy evaluation
    """
    all_values = []
    for key, value in record.items():
        if value and not _is_empty_value(value):
            text = _compact_text(str(value)).lower()
            all_values.append(text)

    if not all_values:
        return True

    # Structural: all values identical (likely template noise)
    if len(all_values) >= 3 and len(set(all_values)) == 1:
        return True

    combined = " ".join(all_values)

    # Structural: if no entity field defined, check via semantic density
    entity_fields = [f.name for f in schema_fields if _is_entity_name_field(f.name)]
    if not entity_fields:
        seg = segment_single_text(combined)
        if not seg.structural_pattern and seg.overall_cohesion < 0.2:
            return True

    # Privacy/legal/navigation: these are structurally distinct
    nav_indicators = ["privacy policy", "terms of", "cookie", "about us"]
    if any(v in combined for v in nav_indicators):
        return True

    # Social media links: structural noise on listing pages
    social = ["facebook", "instagram", "twitter", "linkedin", "youtube"]
    if any(v in combined for v in social):
        return True

    # Entity field check: use semantic density on the name field
    entity_fields = [f.name for f in schema_fields if _is_entity_name_field(f.name)]
    if entity_fields:
        name_field = entity_fields[0]
        name_text = _compact_text(str(record.get(name_field) or ""))
        if name_text:
            # Semantic density analysis instead of phrase lists
            is_noise, conf, evidence = is_likely_noise_field(name_field, name_text)
            if is_noise:
                # Check if record has contact info (email/phone/website) to confirm noise
                email_present = any(
                    record.get(f.name) for f in schema_fields
                    if f.field_type == FieldType.EMAIL and not _is_empty_value(record.get(f.name))
                )
                phone_present = any(
                    record.get(f.name) for f in schema_fields
                    if f.field_type == FieldType.PHONE and not _is_empty_value(record.get(f.name))
                )
                url_field = next((f.name for f in schema_fields if f.field_type == FieldType.URL), "")
                website_present = bool(record.get(url_field)) if url_field else False

                if not (email_present or phone_present or website_present):
                    return True

        # Structural: name duplicated in address
        address_field = next(
            (f.name for f in schema_fields
             if f.field_type == FieldType.LOCATION or any(x in f.name.lower() for x in ["address", "location"])),
            ""
        )
        address_text = _compact_text(str(record.get(address_field) or "")) if address_field else ""
        if address_text and name_text and address_text.startswith(name_text[:40]) and not (email_present or phone_present or website_present):
            return True

    return False


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _is_empty_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        meaningful = []
        for item in value:
            if item is None:
                continue
            text = _compact_text(str(item))
            if not text or _is_placeholder_value(text):
                continue
            meaningful.append(text)
        return len(meaningful) == 0
    if isinstance(value, str):
        text = _compact_text(value)
        return text == "" or _is_placeholder_value(text)
    return False


def _extract_json_payload(text: str):
    raw = (text or "").strip()
    if not raw:
        return None

    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    for candidate in (raw,):
        try:
            return json.loads(candidate)
        except Exception:
            pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return None


def _should_retry_http_error(error: Exception) -> bool:
    if isinstance(error, requests.HTTPError):
        status = error.response.status_code if error.response is not None else None
        return status in {429, 500, 502, 503, 504}
    if isinstance(error, requests.RequestException):
        return True

    text = str(error).lower()
    return any(token in text for token in ["429", "timed out", "connection", "temporary"])


def _call_openai_compatible_json(
    endpoint: str,
    payload: dict,
    headers: dict | None = None,
    timeout: int = 45,
    max_attempts: int = 2,
    backoff_seconds: float = 0.8,
):
    last_error: Exception | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            response = requests.post(endpoint, json=payload, headers=headers or {}, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return _extract_json_payload(content)
        except Exception as error:
            last_error = error
            if attempt >= max_attempts or not _should_retry_http_error(error):
                raise
            time.sleep(backoff_seconds * attempt)

    if last_error:
        raise last_error
    return None


def _call_openai_compatible_text(
    endpoint: str,
    payload: dict,
    headers: dict | None = None,
    timeout: int = 45,
    max_attempts: int = 2,
    backoff_seconds: float = 0.8,
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            response = requests.post(endpoint, json=payload, headers=headers or {}, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
        except Exception as error:
            last_error = error
            if attempt >= max_attempts or not _should_retry_http_error(error):
                raise
            time.sleep(backoff_seconds * attempt)

    if last_error:
        raise last_error
    return ""


def _groq_model_candidates() -> list[str]:
    primary = (os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
    fallback = (os.getenv("GROQ_FALLBACK_MODEL") or "llama-3.1-8b-instant").strip()
    models: list[str] = []
    for model in [primary, fallback]:
        if model and model not in models:
            models.append(model)
    return models


def _llm_json(messages: list[dict], temperature: float = 0.1, timeout: int = 45):
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                parsed = _call_openai_compatible_json(
                    "https://api.groq.com/openai/v1/chat/completions",
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if parsed is not None:
                    return parsed
            except Exception as e:
                stage = "Groq JSON call" if idx == 0 else "Groq JSON fallback model call"
                print(f"[LLM] {stage} failed ({model}): {e}")

    try:
        payload = {
            "model": "openai",
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        parsed = _call_openai_compatible_json("https://text.pollinations.ai/openai", payload, timeout=timeout)
        if parsed is not None:
            return parsed
    except Exception as e:
        print(f"[LLM] Pollinations JSON call failed: {e}")

    try:
        from g4f.client import Client

        client = Client()
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            timeout=timeout,
        )
        content = res.choices[0].message.content.strip()
        parsed = _extract_json_payload(content)
        if parsed is not None:
            return parsed
    except Exception as e:
        print(f"[LLM] g4f JSON fallback failed: {e}")

    return {}


def _llm_json_fast(messages: list[dict], temperature: float = 0.0, timeout: int = 12):
    """Fast-path JSON call for throughput-sensitive cleaning tasks."""
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                parsed = _call_openai_compatible_json(
                    "https://api.groq.com/openai/v1/chat/completions",
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if parsed is not None:
                    return parsed
            except Exception as e:
                stage = "Groq fast JSON call" if idx == 0 else "Groq fast JSON fallback model call"
                print(f"[LLM] {stage} failed ({model}): {e}")

    try:
        payload = {
            "model": "openai",
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        parsed = _call_openai_compatible_json(
            "https://text.pollinations.ai/openai",
            payload,
            timeout=timeout,
        )
        if parsed is not None:
            return parsed
    except Exception as e:
        print(f"[LLM] Pollinations fast JSON call failed: {e}")

    return {}


def _llm_text(messages: list[dict], temperature: float = 0.4, timeout: int = 45) -> str:
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                text = _call_openai_compatible_text(
                    "https://api.groq.com/openai/v1/chat/completions",
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if text:
                    return text
            except Exception as e:
                stage = "Groq text call" if idx == 0 else "Groq text fallback model call"
                print(f"[LLM] {stage} failed ({model}): {e}")

    try:
        payload = {
            "model": "openai",
            "messages": messages,
            "temperature": temperature,
        }
        text = _call_openai_compatible_text("https://text.pollinations.ai/openai", payload, timeout=timeout)
        if text:
            return text
    except Exception as e:
        print(f"[LLM] Pollinations text call failed: {e}")

    try:
        from g4f.client import Client

        client = Client()
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            timeout=timeout,
        )
        return (res.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[LLM] g4f text fallback failed: {e}")
        return ""


async def fetch_page_content(url: str) -> str:
    """Load a URL in a headless browser and fallback to plain HTTP when needed."""
    browser = None
    context = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            async def _route_filter(route):
                if route.request.resource_type in {"image", "media", "font"}:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _route_filter)
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(1.5)
            html = await page.content()
            return html
    except Exception as e:
        print(f"[Scraper] Playwright failed for {url}: {e}. Falling back to requests")
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass

    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    return resp.text


def clean_html_for_selectors(html: str, max_chars: int = 16000) -> str:
    """Remove known-noise tags while preserving structure useful for selector discovery."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()

    for tag in soup.find_all(True):
        attrs_to_keep = ["class", "id", "href", "itemprop"]
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in attrs_to_keep}

    cleaned = soup.prettify()
    return cleaned[:max_chars]


def _detect_table_headers(html: str) -> list[dict]:
    """Detect table/grid headers from HTML to understand column semantics."""
    soup = BeautifulSoup(html, "html.parser")
    headers_info = []

    for th in soup.find_all(["th", "thead"]):
        text = _compact_text(th.get_text())
        if text:
            headers_info.append({
                "text": text,
                "class": " ".join(th.get("class", [])),
                "id": th.get("id", ""),
            })

    for header in soup.find_all(["h1", "h2", "h3", "h4"])[:5]:
        text = _compact_text(header.get_text())
        if text and len(text) < 50:
            headers_info.append({
                "text": text,
                "is_heading": True,
            })

    return headers_info


def _analyze_page_data_type(html: str, schema_fields: list[SchemaField]) -> dict:
    """
    Analyze page content using universal page profiler.
    
    This is now domain-agnostic - it detects structure and patterns,
    not "flight" vs "hotel" types.
    """
    # Use the new universal page profiler
    profile = detect_page_structure(html)
    patterns = detect_value_patterns(html)
    
    return {
        "structure_type": profile.structure_type,
        "structure_confidence": profile.structure_confidence,
        "headers": profile.headers,
        "patterns_detected": {
            "currencies": bool(patterns.currencies),
            "dates": bool(patterns.dates),
            "ratings": bool(patterns.ratings),
            "codes": bool(patterns.codes_3letter),
            "phones": bool(patterns.phones),
            "emails": bool(patterns.emails),
        }
    }


def _intelligent_column_mapping(html: str, schema_fields: list[SchemaField]) -> dict:
    """Analyze page structure to intelligently map columns to schema fields."""
    soup = BeautifulSoup(html, "html.parser")
    mapping_hints = {}

    table = soup.find("table") or soup.find("div", class_=lambda x: x and ("table" in x or "grid" in x))
    if not table:
        return mapping_hints

    headers = []
    for th in table.find_all(["th", "thead"]):
        headers.append(_compact_text(th.get_text()).lower())

    for field in schema_fields:
        field_keywords = _get_field_keywords(field.name)
        for i, header in enumerate(headers):
            for keyword in field_keywords:
                if keyword in header:
                    mapping_hints[field.name] = {"column_index": i, "matched_header": header}
                    break

    return mapping_hints


def _get_field_keywords(field_name: str) -> list[str]:
    """Get keywords for a field to match against page headers."""
    name_lower = field_name.lower().replace("_", " ")
    base = [name_lower]

    keywords_map = {
        "price": ["price", "cost", "amount", "rate", "fee", "fare"],
        "date": ["date", "day", "time", "start", "end", "begin", "schedule"],
        "time": ["time", "duration", "start", "end", "schedule"],
        "name": ["name", "title", "title", "company"],
        "phone": ["phone", "contact", "mobile", "call"],
        "email": ["email", "mail", "contact"],
        "address": ["address", "location", "place"],
        "rating": ["rating", "review", "star", "score"],
        "description": ["description", "about", "detail", "info"],
    }

    for key, synonyms in keywords_map.items():
        if key in name_lower:
            base.extend(synonyms)

    return base


def _infer_field_type_from_examples(examples: list[str], field_name: str) -> str:
    """Infer what field type should be based on sample values."""
    if not examples:
        return "string"

    name_lower = field_name.lower()

    if any(k in name_lower for k in ["price", "cost", "amount"]):
        return "currency"
    if any(k in name_lower for k in ["date", "time", "start", "end", "schedule"]):
        return "date"
    if any(k in name_lower for k in ["duration", "hours"]):
        return "duration"
    if any(k in name_lower for k in ["from", "origin", "source"]):
        return "location"
    if any(k in name_lower for k in ["to", "destination", "dst"]):
        return "location"

    sample = examples[0].lower().strip()

    if re.search(r"^\d+h\s*\d+m$", sample):
        return "duration"
    if re.search(r"\d+h$", sample):
        return "duration"
    if re.search(r"^\d+:\d{2}$", sample):
        return "duration"
    if re.search(r"\d+\s*hours?", sample):
        return "duration"

    if re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", sample, re.IGNORECASE):
        return "date"
    if re.search(r"\d{1,2}[/-]\d{1,2}[/-](\d{2}|\d{4})", sample):
        return "date"
    if re.search(r"\d{4}[-]\d{2}[-]\d{2}", sample):
        return "date"

    if re.search(r"^[\$\u20a8\u20ac\u00a3\u00a5]\s*\d+[\d,]*\.?\d*$", sample):
        return "currency"
    if re.search(r"\d+[\d,]*\s*(inr|usd|eur|gbp)$", sample, re.IGNORECASE):
        return "currency"

    return "string"


def build_selector_prompt(html_snippet: str, schema_fields: list[SchemaField], page_analysis: dict = None) -> str:
    """
    Build selector prompt using universal page structure info.
    
    Domain-agnostic - focuses on structure type (table/cards/list),
    not on "flight" vs "hotel" rules.
    """
    page_analysis = page_analysis or {}
    
    # Use universal structure detection instead of domain-specific
    structure_type = page_analysis.get("structure_type", "unknown")
    structure_confidence = page_analysis.get("structure_confidence", 0.0)
    headers = page_analysis.get("headers", [])
    patterns = page_analysis.get("patterns_detected", {})
    
    structure_context = f"""
PAGE STRUCTURE DETECTED: {structure_type.upper()} (confidence: {structure_confidence:.2f})
- This could be a table, card layout, list, or mixed structure
- Target the DATA CONTAINER, not header/footer/navigation
"""
    
    # Add detected patterns as hints
    if patterns:
        detected = [k for k, v in patterns.items() if v]
        if detected:
            structure_context += f"\nVALUE PATTERNS DETECTED: {', '.join(detected)}"
    
    # Headers
    header_context = ""
    if headers:
        header_context = f"\nDETECTED HEADERS: {headers[:8]}"
    
    # Schema fields
    field_hints = []
    for f in schema_fields:
        hint = f'  - "{f.name}"'
        hint += f' (type: {f.field_type.value})'
        if f.description:
            hint += f': {f.description}'
        field_hints.append(hint)

    schema_str = "\n".join(field_hints)

    return f"""You are an expert data extraction engineer.
Extract structured data from this HTML snippet.

{structure_context}
{header_context}

USER SCHEMA:
{schema_str}

CRITICAL EXCLUSIONS (apply to ANY page type):
- Navigation menus, header, footer
- Filter/sort options, sidebar content
- Login/signup forms, social media links
- Copyright/terms/privacy pages

EXTRACTION RULES:
1. Return ONLY JSON: {{"item_container": "selector", "fields": {{"field_name": "selector"}}}}
2. Target the repeating DATA CONTAINER (rows, cards, items) - NOT navigation
3. Use relative selectors (descendant or child)
4. Each schema field needs a selector or null

HTML SNIPPET:
```html
{html_snippet}
```"""


async def extract_css_selectors(prompt: str) -> dict:
    """Generate selector mapping through available LLM providers."""

    def _sync_call():
        messages = [
            {
                "role": "system",
                "content": (
                    "You output valid JSON objects for CSS selector extraction. "
                    "No markdown, no commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        response = _llm_json(messages, temperature=0.1)
        return response if isinstance(response, dict) else {}

    return await run_sync_in_thread(_sync_call)


def _valid_email(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if not match:
        return None

    email = match.group(0).lower().strip(" .,;:")
    local_part, _, domain = email.partition("@")
    if local_part in {"noreply", "no-reply", "donotreply", "do-not-reply", "test"}:
        return None
    if domain in {"example.com", "test.com", "localhost"}:
        return None
    if "invalid" in domain or "placeholder" in domain:
        return None
    return email


def _valid_phone(text: str) -> str | None:
    candidates = re.findall(r"(?:\+?\d[\d\s()\-]{6,}\d)", text)
    cleaned = []
    seen = set()
    for c in candidates:
        c_norm = _compact_text(c).strip("- ,")
        digits = re.sub(r"\D", "", c_norm)
        if len(digits) < 7 or len(digits) > 15:
            continue
        if c_norm not in seen:
            seen.add(c_norm)
            cleaned.append(c_norm)
    return cleaned[0] if cleaned else None


def _field_by_type(schema_fields: list[SchemaField], field_type: FieldType) -> SchemaField | None:
    return next((field for field in schema_fields if field.field_type == field_type), None)


def _extract_contacts_from_node(node) -> tuple[str | None, str | None]:
    if node is None:
        return None, None

    email = None
    phone = None

    try:
        text = _compact_text(node.get_text(separator=" ", strip=True))
        if text:
            email = _valid_email(text)
            phone = _valid_phone(text)
    except Exception:
        text = ""

    for link in node.select("a[href]"):
        href = _compact_text(link.get("href") or "")
        if not href:
            continue

        label = _compact_text(link.get_text(separator=" ", strip=True))
        href_lower = href.lower()

        if href_lower.startswith("mailto:") and not email:
            raw = unquote(href.split(":", 1)[1]).split("?", 1)[0]
            email = _valid_email(raw) or _valid_email(label)
        elif href_lower.startswith("tel:") and not phone:
            raw = unquote(href.split(":", 1)[1]).split("?", 1)[0]
            phone = _valid_phone(raw) or _valid_phone(label)

        if email and phone:
            break

    return email, phone


def _looks_like_url_text(text: str) -> bool:
    value = _compact_text(text).lower()
    if value.startswith(("http://", "https://", "www.")):
        return True
    if "@" in value:
        return False
    return bool(re.search(r"\b[\w.-]+\.[a-z]{2,}(?:/\S*)?\b", value))


def _sanitize_field_value(field: SchemaField, value, base_url: str = ""):
    if value is None:
        return None

    if field.field_type == FieldType.LIST_STRING:
        if not isinstance(value, list):
            value = [value]
        normalized = []
        for item in value:
            text = _compact_text(str(item))
            if not text:
                continue
            if _is_placeholder_value(text):
                continue
            normalized.append(text)
        return normalized or None

    text = _compact_text(str(value))
    if not text:
        return None

    if _is_placeholder_value(text):
        return None

    if _is_entity_name_field(field.name) and _is_noise_name_value(text):
        return None

    # Prevent semantic leakage into company/name fields.
    if _is_entity_name_field(field.name):
        if _valid_email(text) or _valid_phone(text) or _looks_like_url_text(text):
            return None

    if field.field_type == FieldType.EMAIL:
        return _valid_email(text)

    if field.field_type == FieldType.PHONE:
        return _valid_phone(text)

    if field.field_type == FieldType.URL:
        if text.startswith("/"):
            return urljoin(base_url, text)
        if text.startswith("//"):
            return "https:" + text
        if text.startswith("http://") or text.startswith("https://"):
            return text
        if "@" not in text and re.match(r"^[\w.-]+\.[a-z]{2,}(?:/.*)?$", text, flags=re.IGNORECASE):
            return "https://" + text
        return None

    if field.field_type == FieldType.INTEGER:
        match = re.search(r"-?\d+", text)
        return int(match.group(0)) if match else None

    if field.field_type in (FieldType.FLOAT, FieldType.CURRENCY, FieldType.PERCENTAGE):
        match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", text)
        return match.group(0) if match else None

    if field.field_type == FieldType.BOOLEAN:
        lowered = text.lower()
        if lowered in {"true", "yes", "1", "y"}:
            return True
        if lowered in {"false", "no", "0", "n"}:
            return False
        return None

    if field.field_type == FieldType.LOCATION:
        text = re.sub(r"\s*(call|phone|email)\s*:\s*.*$", "", text, flags=re.IGNORECASE)
        text = _compact_text(text)
        if _is_placeholder_value(text):
            return None
        return text if len(text) >= 5 else None

    field_name = field.name.lower()
    if field.field_type == FieldType.STRING and ("name" in field_name or "company" in field_name or field_name.endswith("title")):
        if _valid_email(text) or _valid_phone(text) or _looks_like_url_text(text):
            return None

        # Remove listing-site metadata that often gets concatenated into company labels.
        text = re.sub(r"\bAverage\s*rating\s*:\s*.*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+(?:\.\d+)?\s+out\s+of\s+5\s+stars\b.*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+(?:\.\d+)?\s+\d+\s+Reviews?\b.*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bRead\s+More\b.*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bSend\s+Message\b.*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^In\s+[A-Za-z\s]+,\s*", "", text, flags=re.IGNORECASE)
        text = _compact_text(text).strip("|-:, ")

        if re.match(r"^\+\s*\d+\s+More$", text, flags=re.IGNORECASE):
            return None

        if not text or text.lower() in COMPANY_NAME_NOISE:
            return None

        if _is_likely_noise_entity(text):
            return None

        if not re.search(r"[a-zA-Z]", text):
            return None

        return text

    return text


def _enrich_record_contacts(
    record: dict,
    schema_fields: list[SchemaField],
    node,
    page_email: str | None = None,
    page_phone: str | None = None,
    allow_page_fallback: bool = False,
) -> dict:
    email_field = _field_by_type(schema_fields, FieldType.EMAIL)
    phone_field = _field_by_type(schema_fields, FieldType.PHONE)
    if not email_field and not phone_field:
        return record

    enriched = dict(record)
    node_email, node_phone = _extract_contacts_from_node(node)

    if email_field and _is_empty_value(enriched.get(email_field.name)):
        email_candidate = node_email or (page_email if allow_page_fallback else None)
        if email_candidate:
            enriched[email_field.name] = _sanitize_field_value(email_field, email_candidate)

    if phone_field and _is_empty_value(enriched.get(phone_field.name)):
        phone_candidate = node_phone or (page_phone if allow_page_fallback else None)
        if phone_candidate:
            enriched[phone_field.name] = _sanitize_field_value(phone_field, phone_candidate)

    return enriched


def _apply_page_level_contact_fallback(
    records: list[dict],
    schema_fields: list[SchemaField],
    page_email: str | None,
    page_phone: str | None,
) -> list[dict]:
    if not records:
        return records

    email_field = _field_by_type(schema_fields, FieldType.EMAIL)
    phone_field = _field_by_type(schema_fields, FieldType.PHONE)
    if not email_field and not phone_field:
        return records

    has_any_email = bool(email_field) and any(not _is_empty_value(r.get(email_field.name)) for r in records)
    has_any_phone = bool(phone_field) and any(not _is_empty_value(r.get(phone_field.name)) for r in records)

    needs_email = bool(email_field) and not has_any_email and bool(page_email)
    needs_phone = bool(phone_field) and not has_any_phone and bool(page_phone)
    if not (needs_email or needs_phone):
        return records

    updated = list(records)
    best_idx = max(range(len(updated)), key=lambda idx: float(updated[idx].get("record_score") or 0.0))
    updated[best_idx] = _enrich_record_contacts(
        updated[best_idx],
        schema_fields=schema_fields,
        node=None,
        page_email=page_email if needs_email else None,
        page_phone=page_phone if needs_phone else None,
        allow_page_fallback=True,
    )
    updated[best_idx]["record_score"] = score_record_quality(updated[best_idx], schema_fields)
    return updated


def _extract_page_contacts(html: str) -> tuple[str | None, str | None]:
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return None, None
    return _extract_contacts_from_node(soup)


def _boost_contacts_with_page_html(
    rows: list[dict],
    schema_fields: list[SchemaField],
    html: str,
) -> list[dict]:
    page_email, page_phone = _extract_page_contacts(html)
    if not page_email and not page_phone:
        return rows
    return _apply_page_level_contact_fallback(rows, schema_fields, page_email, page_phone)


def _value_quality(field: SchemaField, value) -> float:
    if _is_empty_value(value):
        return 0.0

    if isinstance(value, list):
        return 1.0 if value else 0.0

    text = _compact_text(str(value))
    if _is_placeholder_value(text):
        return 0.0

    if _is_entity_name_field(field.name) and _is_noise_name_value(text):
        return 0.0

    if field.field_type == FieldType.EMAIL:
        return 1.0 if _valid_email(text) else 0.0

    if field.field_type == FieldType.PHONE:
        return 1.0 if _valid_phone(text) else 0.0

    if field.field_type == FieldType.URL:
        return 1.0 if text.startswith("http://") or text.startswith("https://") else 0.0

    if field.field_type == FieldType.INTEGER:
        return 1.0 if re.search(r"-?\d+", text) else 0.0

    if field.field_type in (FieldType.FLOAT, FieldType.CURRENCY, FieldType.PERCENTAGE):
        return 1.0 if re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", text) else 0.0

    if field.field_type == FieldType.LOCATION:
        return 1.0 if len(text) >= 5 else 0.0

    if _is_entity_name_field(field.name):
        if len(text.split()) == 1 and len(text) <= 8:
            return 0.3
        return 1.0

    if field.field_type == FieldType.STRING and ("name" in field.name.lower() or "company" in field.name.lower()):
        if re.match(r"^\+\s*\d+\s+More$", text, flags=re.IGNORECASE):
            return 0.0
        if text.lower() in COMPANY_NAME_NOISE:
            return 0.0
        if not re.search(r"[a-zA-Z]", text):
            return 0.0
        return 1.0 if len(text) >= 3 else 0.0

    return 1.0 if len(text) >= 2 else 0.0


def score_record_quality(record: dict, schema_fields: list[SchemaField]) -> float:
    if not schema_fields:
        non_empty = sum(0 if _is_empty_value(v) else 1 for v in record.values())
        return round(1.0 if non_empty else 0.0, 3)

    required_fields = [f for f in schema_fields if f.required]
    valid_required = sum(1 for f in required_fields if _value_quality(f, record.get(f.name)) >= 0.5)
    required_ratio = (valid_required / len(required_fields)) if required_fields else 0.0

    # Required fields must not be entirely placeholder/invalid.
    if required_fields and required_ratio == 0:
        return 0.0

    non_empty_total = sum(1 for f in schema_fields if _value_quality(f, record.get(f.name)) > 0)
    fill_ratio = non_empty_total / len(schema_fields)

    quality_checks = []
    for field in schema_fields:
        value = record.get(field.name)
        if _is_empty_value(value):
            continue
        quality_checks.append(_value_quality(field, value))
    type_quality = (sum(quality_checks) / len(quality_checks)) if quality_checks else 0.0

    textual_values = [
        _compact_text(str(record.get(f.name))).lower()
        for f in schema_fields
        if not _is_empty_value(record.get(f.name)) and not isinstance(record.get(f.name), list)
    ]
    unique_values = len(set(v for v in textual_values if v))
    repetition_penalty = 0.0
    if non_empty_total >= 3 and unique_values <= 1:
        repetition_penalty = 0.2
    elif non_empty_total >= 3 and unique_values == 2:
        repetition_penalty = 0.1

    score = (0.5 * required_ratio) + (0.3 * fill_ratio) + (0.2 * type_quality) - repetition_penalty
    score = max(0.0, min(1.0, score))
    return round(score, 3)


def normalize_scraped_record(record: dict, schema_fields: list[SchemaField]) -> dict:
    """Ensure schema fields exist and extra keys are preserved."""
    normalized = {f.name: record.get(f.name) for f in schema_fields}
    for key, value in record.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def _validate_extracted_data(record: dict, schema_fields: list[SchemaField]) -> bool:
    """Validate that extracted data looks reasonable for its field type."""
    for field in schema_fields:
        value = record.get(field.name)
        if not value or _is_empty_value(value):
            continue

        text = str(value).lower()

        # Very strict checks only - allow most data through
        if field.field_type == FieldType.PHONE:
            if "@" in text:
                return False

        if field.field_type == FieldType.EMAIL:
            if not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
                if len(text) > 50:
                    return False

        # Be more lenient with date, currency, and string fields
        # Don't reject composite data that might contain useful information

    return True


def _semantic_column_remap(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    """Post-extraction: Detect and fix column misalignments based on content patterns."""
    if not records or not schema_fields:
        return records

    field_types = {f.name: f.field_type for f in schema_fields}

    extracted_values_by_field = {}
    for field_name in field_types:
        values = []
        for record in records:
            v = record.get(field_name)
            if v and not _is_empty_value(v):
                values.append(str(v))
        extracted_values_by_field[field_name] = values[:5]

    corrections = {}

    for field_name, field_type in field_types.items():
        actual_values = extracted_values_by_field[field_name]
        if not actual_values:
            continue

        actual_type = _infer_field_type_from_examples(actual_values, field_name)

        if actual_type != field_type.value and actual_type != "string":
            target_field = None
            if actual_type == "date" and field_type != FieldType.DATE:
                for f in schema_fields:
                    if f.field_type == FieldType.DATE and not corrections.get(f.name):
                        target_field = f.name
                        break
            elif actual_type == "currency" and field_type != FieldType.CURRENCY:
                for f in schema_fields:
                    if f.field_type == FieldType.CURRENCY and not corrections.get(f.name):
                        target_field = f.name
                        break
            elif actual_type == "duration":
                for f in schema_fields:
                    if f.field_type == FieldType.STRING and any(k in f.name.lower() for k in ["duration", "time"]):
                        target_field = f.name
                        break

            if target_field:
                corrections[field_name] = target_field

    if not corrections:
        return records

    print(f"[Scraper] Semantic remapping detected: {corrections}")

    remapped = []
    for record in records:
        new_record = dict(record)
        temp_values = {}

        for src_field, dst_field in corrections.items():
            if src_field in new_record and new_record[src_field]:
                temp_values[dst_field] = new_record[src_field]
                new_record[src_field] = None

        for dst_field, value in temp_values.items():
            if new_record.get(dst_field) is None:
                new_record[dst_field] = value

        remapped.append(new_record)

    return remapped


def apply_selectors(html: str, selectors_map: dict, schema_fields: list[SchemaField], base_url: str = "") -> list[dict]:
    """Execute generated CSS selectors on full HTML and score extracted records."""
    container_sel = selectors_map.get("item_container")
    field_sels = selectors_map.get("fields", {}) or {}

    if not container_sel:
        print("[Scraper] No item_container selector generated")
        return []

    soup = BeautifulSoup(html, "html.parser")
    if str(container_sel).lower() in ("body", "html", "main"):
        containers = [soup]
    else:
        containers = soup.select(container_sel)

    print(f"[Scraper] Containers found with '{container_sel}': {len(containers)}")
    page_email, page_phone = _extract_contacts_from_node(soup)
    allow_page_contact_fallback = len(containers) == 1
    results = []

    for container in containers:
        record = {}
        for field in schema_fields:
            selector = field_sels.get(field.name)
            if not selector:
                record[field.name] = None
                continue

            try:
                nodes = container.select(selector)
            except Exception as e:
                print(f"[Scraper] Invalid selector '{selector}' for {field.name}: {e}")
                record[field.name] = None
                continue

            if not nodes:
                record[field.name] = None
                continue

            if field.field_type == FieldType.LIST_STRING:
                values = [_sanitize_field_value(field, n.get_text(" ", strip=True), base_url=base_url) for n in nodes]
                values = [v for v in values if v is not None]
                record[field.name] = values or None
                continue

            node = nodes[0]
            if field.field_type == FieldType.URL:
                href = None
                if node.name == "a":
                    href = node.get("href")
                else:
                    link = node.find("a")
                    href = link.get("href") if link else None
                record[field.name] = _sanitize_field_value(field, href, base_url=base_url)
                continue

            raw_text = node.get_text(separator=" ", strip=True)
            if "rating" in field.name.lower() or "star" in field.name.lower():
                classes = node.get("class", [])
                rating_words = [c for c in classes if c in ["One", "Two", "Three", "Four", "Five"]]
                if rating_words:
                    raw_text = rating_words[0]

            record[field.name] = _sanitize_field_value(field, raw_text, base_url=base_url)

        normalized = normalize_scraped_record(record, schema_fields)
        if not any(not _is_empty_value(normalized.get(f.name)) for f in schema_fields):
            continue

        normalized = _enrich_record_contacts(
            normalized,
            schema_fields=schema_fields,
            node=container,
            page_email=page_email,
            page_phone=page_phone,
            allow_page_fallback=allow_page_contact_fallback,
        )

        normalized["record_score"] = score_record_quality(normalized, schema_fields)
        results.append(normalized)

    return _apply_page_level_contact_fallback(results, schema_fields, page_email, page_phone)


def extract_with_regex(html: str, schema_fields: list[SchemaField], base_url: str = "") -> list[dict]:
    """Fallback extraction path when selector generation fails."""
    soup = BeautifulSoup(html, "html.parser")
    page_email, page_phone = _extract_contacts_from_node(soup)
    containers = list(soup.find_all(["article", "li", "tr", "div"], class_=re.compile(r"product|item|card|listing|row", re.I)))
    if not containers:
        headers = soup.find_all(["h2", "h3", "h4"])
        containers = [h.parent for h in headers if h.parent]
    if not containers:
        containers = list(soup.find_all("tr")[1:])
        
    if soup.body:
        containers.append(soup.body)

    results = []
    for container in containers[:300]:
        text = _compact_text(container.get_text(separator=" ", strip=True))
        if len(text) < 5:
            continue

        record = {}
        text_field = schema_fields[0].name if schema_fields else "text"
        for field in schema_fields:
            field_name = field.name.lower()

            if field.field_type == FieldType.URL:
                link = container.find("a")
                record[field.name] = _sanitize_field_value(field, link.get("href") if link else None, base_url=base_url)
            elif field.field_type == FieldType.EMAIL:
                record[field.name] = _sanitize_field_value(field, text)
            elif field.field_type == FieldType.PHONE:
                record[field.name] = _sanitize_field_value(field, text)
            elif any(k in field_name for k in ["title", "name", "company"]):
                heading = container.find(["h1", "h2", "h3", "h4", "a", "strong"])
                candidate = heading.get_text(" ", strip=True) if heading else text[:70]
                record[field.name] = _sanitize_field_value(field, candidate)
            elif field.name == text_field:
                # First non-special field gets full composite text for segmentation
                record[field.name] = _sanitize_field_value(field, text)
            else:
                # Extra fields left empty; mapper fills from segmented candidates
                record[field.name] = None

        normalized = normalize_scraped_record(record, schema_fields)
        if not any(not _is_empty_value(normalized.get(f.name)) for f in schema_fields):
            continue

        if _is_likely_noise_row(normalized, schema_fields):
            continue

        normalized = _enrich_record_contacts(
            normalized,
            schema_fields=schema_fields,
            node=container,
            page_email=page_email,
            page_phone=page_phone,
            allow_page_fallback=False,
        )

        normalized["record_score"] = score_record_quality(normalized, schema_fields)
        results.append(normalized)

    return _apply_page_level_contact_fallback(results, schema_fields, page_email, page_phone)


def _dedupe_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    key_fields = [f.name for f in schema_fields] if schema_fields else []
    seen = set()
    deduped = []
    for record in sorted(records, key=lambda r: r.get("record_score", 0), reverse=True):
        if key_fields:
            key = tuple(_compact_text(str(record.get(k, ""))).lower() for k in key_fields)
        else:
            key = tuple(sorted((k, str(v)) for k, v in record.items() if k != "record_score"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _limit_source_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    if len(records) <= MAX_RECORDS_PER_SOURCE:
        return records

    email_field = _field_by_type(schema_fields, FieldType.EMAIL)
    phone_field = _field_by_type(schema_fields, FieldType.PHONE)

    def _has_contact(record: dict) -> bool:
        has_email = bool(email_field) and not _is_empty_value(record.get(email_field.name))
        has_phone = bool(phone_field) and not _is_empty_value(record.get(phone_field.name))
        return has_email or has_phone

    prioritized = sorted(
        records,
        key=lambda record: (
            1 if _has_contact(record) else 0,
            float(record.get("record_score") or 0.0),
        ),
        reverse=True,
    )
    trimmed = prioritized[:MAX_RECORDS_PER_SOURCE]
    trimmed.sort(key=lambda record: float(record.get("record_score") or 0.0), reverse=True)
    print(
        f"[Scraper] Trimmed source records {len(records)} -> {len(trimmed)} "
        f"(limit {MAX_RECORDS_PER_SOURCE})"
    )
    return trimmed


def _trim_prompt_value(value, max_chars: int = 180):
    if value is None:
        return None
    if isinstance(value, list):
        compact_items = []
        for item in value[:6]:
            if item is None:
                continue
            compact_items.append(_compact_text(str(item))[:max_chars])
        return compact_items
    return _compact_text(str(value))[:max_chars]


def _prepare_records_for_ai(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    schema_keys = [f.name for f in schema_fields]
    optional_keys = ["source_url", "source_type", "source_trust_score"]

    prepared = []
    for record in records:
        item = {}
        for key in schema_keys:
            item[key] = _trim_prompt_value(record.get(key))

        for key in optional_keys:
            if key in record:
                item[key] = _trim_prompt_value(record.get(key))

        prepared.append(item)
    return prepared


def _extract_ai_records(payload) -> list[dict]:
    if isinstance(payload, dict):
        rows = payload.get("records")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    elif isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def _sanitize_structured_record(candidate: dict, schema_fields: list[SchemaField], fallback: dict) -> dict:
    base_url = str(candidate.get("source_url") or fallback.get("source_url") or "")
    cleaned = {}

    for field in schema_fields:
        # Preserve explicit nulls from AI output; fallback only when key is missing.
        if field.name in candidate:
            value = candidate.get(field.name)
        else:
            value = fallback.get(field.name)
        cleaned[field.name] = _sanitize_field_value(field, value, base_url=base_url)

    for extra in ["source_url", "source_type", "source_trust_score"]:
        if extra in candidate:
            cleaned[extra] = candidate.get(extra)
        elif extra in fallback:
            cleaned[extra] = fallback.get(extra)

    normalized = normalize_scraped_record(cleaned, schema_fields)
    normalized["record_score"] = score_record_quality(normalized, schema_fields)
    return normalized


async def ai_clean_and_align_records(
    records: list[dict],
    schema_fields: list[SchemaField],
    min_record_score: float = 0.0,
    page_type: str = "general",
    user_intent: str = "",
) -> tuple[list[dict], dict]:
    """
    Use AI to clean messy values and align them into the exact schema columns.
    
    NOW DOMAIN-AGNOSTIC: Works for ANY data type by matching values to semantic needs
    (price, date, rating, location) rather than domain-specific fields.
    """
    report = {
        "applied": False,
        "input_records": len(records),
        "output_records": len(records),
        "total_chunks": 0,
        "ai_chunks": 0,
        "fallback_chunks": 0,
        "model_fallback_mode": False,
        "noise_rows_removed": 0,
        "capped_records": 0,
        "quality_filtered_after_ai": 0,
        "page_type": "universal",  # Changed from domain-specific
    }

    if not records or not schema_fields:
        return records, report

    report["applied"] = True
    working = records[:AI_STRUCTURING_MAX_RECORDS]
    overflow = records[AI_STRUCTURING_MAX_RECORDS:]
    report["capped_records"] = len(overflow)

    schema_descriptor = [
        {
            "name": f.name,
            "field_type": f.field_type.value,
            "required": bool(f.required),
            "description": f.description or "",
        }
        for f in schema_fields
    ]

    # UNIVERSAL SEMANTIC RULES - works for ANY data type
    # Match by what values ARE (currency, date, rating), not by domain
    universal_rules = """
UNIVERSAL SEMANTIC MAPPING RULES:
The key insight: Match by WHAT VALUES LOOK LIKE, not by WHERE THEY CAME FROM.

VALUE TYPE DETECTION:
- CURRENCY values: Look for "£238", "$450", "₹5,200", "5000 INR", patterns
- DATE values: Look for "22-05-2026", "14:30", "May 22", "2h 30m" patterns
- RATING values: Look for "4.5/5", "★★★★☆", "8.5/10", "4 stars" patterns  
- LOCATION values: Look for city names, airport codes (LON, PAR), addresses
- PHONE values: Look for "+91 98765", "(555) 123" patterns
- EMAIL values: Look for "name@domain.com" patterns

TASK:
For each extracted value, determine:
1. What TYPE of value is it? (currency, date, rating, etc.)
2. Which schema field should it go in based on its type?

EXAMPLE:
- "£238" is CURRENCY - map to fields that expect price/cost/fare
- "22-05-2026" is DATE - map to fields that expect date/time
- "4.5/5" is RATING - map to fields that expect rating/score
- "LON" is CODE - map to fields that expect location/code

VALIDATION RULES:
- A value in the wrong type field should be flagged, not just moved
- Empty fields are OK; wrong values are NOT
- If you cannot confidently map a value, leave it as null
"""

    output: list[dict] = []
    consecutive_model_failures = 0
    skip_model_calls = False

    for start in range(0, len(working), AI_STRUCTURING_CHUNK_SIZE):
        chunk = working[start:start + AI_STRUCTURING_CHUNK_SIZE]
        if not chunk:
            continue

        report["total_chunks"] += 1
        prompt_rows = _prepare_records_for_ai(chunk, schema_fields)

        intent_context = f"\nUSER INTENT: {user_intent}" if user_intent else ""

        prompt = (
            "You are an intelligent data cleaning and schema mapping engine.\n"
            f"Return ONLY JSON with shape: {{'records': [ ... ]}}.{intent_context}\n"
            f"{universal_rules}\n"
            "CRITICAL NOISE FILTERING - MUST DROP THESE:\n"
            "- Navigation links: 'About Us', 'Contact Us', 'Privacy Policy', 'Terms', 'FAQ', 'Help', 'Support'\n"
            "- Menu items: 'Home', 'Menu', 'Search', 'Filter', 'Sort By', 'Show All', 'View All'\n"
            "- Footer links: 'Facebook', 'Twitter', 'Instagram', 'LinkedIn', 'YouTube', 'Social Media'\n"
            "- Single words that are page labels, not data\n"
            "- Copyright: 'Copyright', 'All Rights Reserved', 'Powered By'\n\n"
            "UNIVERSAL DATA PATTERN RULES:\n"
            "- DATE/TIME: Look for '12 May', '15 Jun 2024', '14:30', '2:30 PM', '01:30', 'Saturday'\n"
            "- PRICE/CURRENCY: Look for '₹5,200', '$450', 'INR 3000', 'Rs. 1500', '50K', '50,000', '£'\n"
            "- DURATION: Look for '2h 30m', '1h 45m', '03:15', '3 hours'\n"
            "- RATINGS: Look for '4.5/5', '8.5/10', '★★★★☆', '4.5 stars'\n"
            "- LOCATION: Look for city names, addresses, airport codes (LON, PAR, BOM, DEL)\n"
            "- PHONE: Look for '+91 98765 43210', '020 8178 8835', '9876543210'\n"
            "- EMAIL: Look for 'name@domain.com'\n\n"
            "Rules:\n"
            "- Keep the same row order as input and keep one output row per input row.\n"
            "- INTELLIGENTLY map any value to the correct schema column based on content pattern and column meaning.\n"
            "- STRICTLY DROP any row that is: navigation, menu, footer, filter option, label, or non-data text.\n"
            "- A valid data row must contain meaningful entity information (name, price, date, location).\n"
            "- If a row is not an actual data row (menu/category/link block), set _drop_row to true.\n"
            "- Do not invent values; use null when unknown.\n"
            "- Output keys must include all schema columns exactly.\n"
            "- Each output row may include optional boolean key _drop_row.\n"
            "- Preserve source_url/source_type/source_trust_score when present.\n\n"
            f"SCHEMA:\n{json.dumps(schema_descriptor, ensure_ascii=True)}\n\n"
            f"INPUT_ROWS:\n{json.dumps(prompt_rows, ensure_ascii=True)}"
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict data cleaning and schema mapping engine. "
                    "Return valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        if skip_model_calls:
            ai_rows = []
            report["fallback_chunks"] += 1
        else:
            try:
                payload = await run_sync_in_thread(
                    _llm_json_fast,
                    messages,
                    0.0,
                    AI_STRUCTURING_CHUNK_TIMEOUT_SECONDS,
                )
                ai_rows = _extract_ai_records(payload)
                # Recovery path: if fast route returns no structured rows,
                # make one standard JSON attempt before treating chunk as fallback.
                if not ai_rows:
                    recovery_payload = await run_sync_in_thread(
                        _llm_json,
                        messages,
                        0.0,
                        max(20, AI_STRUCTURING_CHUNK_TIMEOUT_SECONDS * 2),
                    )
                    ai_rows = _extract_ai_records(recovery_payload)
                if ai_rows:
                    report["ai_chunks"] += 1
                    consecutive_model_failures = 0
                else:
                    report["fallback_chunks"] += 1
                    consecutive_model_failures += 1
            except Exception:
                ai_rows = []
                report["fallback_chunks"] += 1
                consecutive_model_failures += 1

            if consecutive_model_failures >= AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES:
                skip_model_calls = True
                report["model_fallback_mode"] = True

        # Never lose records because of model output shape drift.
        if ai_rows:
            merged_rows = ai_rows[:len(chunk)]
            if len(merged_rows) < len(chunk):
                merged_rows.extend(chunk[len(merged_rows):])
        else:
            merged_rows = chunk

        for idx, row in enumerate(merged_rows):
            candidate = row if isinstance(row, dict) else {}
            if candidate.get("_drop_row") is True:
                report["noise_rows_removed"] += 1
                continue
            fallback = chunk[idx] if idx < len(chunk) else {}
            cleaned = _sanitize_structured_record(candidate, schema_fields, fallback)
            if _is_likely_noise_row(cleaned, schema_fields):
                report["noise_rows_removed"] += 1
                continue
            if any(not _is_empty_value(cleaned.get(f.name)) for f in schema_fields):
                output.append(cleaned)

    # Overflow records are still cleaned deterministically (without AI call)
    for row in overflow:
        cleaned = _sanitize_structured_record({}, schema_fields, row)
        if _is_likely_noise_row(cleaned, schema_fields):
            report["noise_rows_removed"] += 1
            continue
        if any(not _is_empty_value(cleaned.get(f.name)) for f in schema_fields):
            output.append(cleaned)

    if min_record_score > 0:
        before = len(output)
        output = [r for r in output if float(r.get("record_score") or 0.0) >= min_record_score]
        report["quality_filtered_after_ai"] = before - len(output)

    report["output_records"] = len(output)
    return output, report


async def scrape_url(url: str, schema_fields: list[SchemaField], min_record_score: float = 0.35, user_intent: str = "") -> list[dict]:
    """
    Universal semantic extraction pipeline:
    
    1. Parse user intent → semantic needs (price, date, location, etc.)
    2. Profile page structure → table/cards/list/key-value
    3. Extract raw values → CSS selectors or regex fallback
    4. Semantic mapping → match values to intent by WHAT THEY ARE
    5. Validation → confidence scoring, reject wrong, allow empty
    6. Repair → fix low-confidence mappings via AI
    
    NO domain-specific logic - works for any data type.
    """
    print(f"[Scraper] Fetching: {url}")
    html = await fetch_page_content(url)
    if len(html) < 100:
        return []

    # STEP 1: Parse user intent to semantic needs
    intent = None
    if user_intent:
        try:
            from app.intent_parser import parse_user_intent
            intent = parse_user_intent(user_intent)
            print(f"[Scraper] User intent: {intent.semantic_needs}")
        except Exception as e:
            print(f"[Scraper] Intent parsing failed: {e}")

    # STEP 2: Profile page structure (universal)
    page_profile = detect_page_structure(html)
    value_patterns = detect_value_patterns(html)
    print(f"[Scraper] Page structure: {page_profile.structure_type} (confidence: {page_profile.structure_confidence:.2f})")
    
    # Get headers for semantic mapping
    headers = page_profile.headers or []

    # STEP 3: Extract raw values
    html_snippet = clean_html_for_selectors(html, max_chars=12000)
    prompt = build_selector_prompt(html_snippet, schema_fields, page_analysis={
        "structure_type": page_profile.structure_type,
        "structure_confidence": page_profile.structure_confidence,
        "headers": headers,
        "patterns_detected": {
            "currencies": bool(value_patterns.currencies),
            "dates": bool(value_patterns.dates),
            "ratings": bool(value_patterns.ratings),
        }
    })

    print("[Scraper] Requesting CSS selector mapping")
    selectors_map = await extract_css_selectors(prompt)

    results = []
    if selectors_map and "item_container" in selectors_map:
        print("[Scraper] Selector map generated")
        results = apply_selectors(html, selectors_map, schema_fields, base_url=url)

    if not results:
        print("[Scraper] Falling back to regex extraction")
        results = extract_with_regex(html, schema_fields, base_url=url)

    # STEP 3b-6: Run clean semantic pipeline
    # Strips metadata, filters noise, segments composites, allocates roles, validates
    if results and schema_fields:
        schema_names = [f.name for f in schema_fields]
        results = run_pipeline(results, schema_names)
        print(f"[Scraper] Pipeline: {len(results)} semantic records")

    # Deduplication and limit
    deduped = _dedupe_records(results, schema_fields)
    return _limit_source_records(deduped, schema_fields)


def _slug_field_name(name: str, index: int) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return cleaned or f"field_{index}"


def _normalize_field_type(value: str) -> str:
    raw = (value or "").strip().lower()
    try:
        return FieldType(raw).value
    except Exception:
        return FieldType.STRING.value


async def suggest_schema_from_intent(intent: str, max_fields: int = 8) -> dict:
    """Infer topic, location hints, and schema fields from natural language intent."""

    def _fallback() -> dict:
        fields = [
            {
                "name": "name",
                "field_type": "string",
                "description": "Primary entity name",
                "required": True,
            },
            {
                "name": "phone",
                "field_type": "phone",
                "description": "Contact phone number",
                "required": False,
            },
            {
                "name": "email",
                "field_type": "email",
                "description": "Contact email",
                "required": False,
            },
            {
                "name": "address",
                "field_type": "location",
                "description": "Address or location",
                "required": False,
            },
        ][:max_fields]

        location_match = re.search(r"\bin\s+([A-Za-z][A-Za-z\s,.-]{2,})", intent)
        location = _compact_text(location_match.group(1)) if location_match else ""

        return {
            "topic": _compact_text(intent),
            "location": location,
            "origin_location": location,
            "max_distance_km": None,
            "fields": fields,
            "notes": "Fallback schema was used because LLM suggestion was unavailable.",
        }

    def _sync_call() -> dict:
        prompt = f"""Convert this scraping intent into a JSON plan.

Intent:
{intent}

Return ONLY JSON with this shape:
{{
  "topic": "short search topic",
  "location": "city/region if present else empty string",
  "origin_location": "best center point for distance filtering if present else empty string",
  "max_distance_km": number or null,
  "fields": [
    {{"name": "snake_case", "field_type": "string|integer|float|boolean|email|url|phone|location|date|list_string|currency|percentage", "description": "short", "required": true_or_false}}
  ],
  "notes": "very short rationale"
}}

Rules:
- Keep fields concise and practical.
- Use at most {max_fields} fields.
- Prefer business-ready schema quality.
"""

        messages = [
            {
                "role": "system",
                "content": "You generate strict JSON plans for structured web scraping.",
            },
            {"role": "user", "content": prompt},
        ]
        raw = _llm_json(messages, temperature=0.2)
        if not isinstance(raw, dict):
            return _fallback()

        parsed_fields = []
        for idx, field in enumerate(raw.get("fields", [])[:max_fields], start=1):
            if not isinstance(field, dict):
                continue
            name = _slug_field_name(str(field.get("name") or ""), idx)
            parsed_fields.append(
                {
                    "name": name,
                    "field_type": _normalize_field_type(str(field.get("field_type") or "string")),
                    "description": _compact_text(str(field.get("description") or "")),
                    "required": bool(field.get("required", True)),
                }
            )

        if not parsed_fields:
            return _fallback()

        radius = raw.get("max_distance_km")
        if radius is not None:
            try:
                radius = float(radius)
                if radius < 0:
                    radius = None
            except Exception:
                radius = None

        return {
            "topic": _compact_text(str(raw.get("topic") or intent)),
            "location": _compact_text(str(raw.get("location") or "")),
            "origin_location": _compact_text(str(raw.get("origin_location") or "")),
            "max_distance_km": radius,
            "fields": parsed_fields,
            "notes": _compact_text(str(raw.get("notes") or "")),
        }

    return await run_sync_in_thread(_sync_call)


async def generate_data_insight(records: list[dict]) -> str:
    """Generate a concise summary for the scraped dataset."""

    def _sync_call() -> str:
        data_str = json.dumps(records[:50])
        prompt = (
            "Analyze this structured data array and provide a concise executive summary in at most 2 sentences. "
            "Highlight patterns, major distributions, or quality concerns.\n"
            f"Data: {data_str}"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a data analyst. Provide direct analysis only. "
                    "No preamble and no markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        response = _llm_text(messages, temperature=0.5, timeout=20)
        return response or "Analysis generation encountered an upstream model error."

    return await run_sync_in_thread(_sync_call)
