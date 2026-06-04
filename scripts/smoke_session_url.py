#!/usr/bin/env python3
"""Manual smoke test for session-bound URLs — run against real websites.

Usage:
    python scripts/smoke_session_url.py "https://example.com/search/id/token123"

Prints session-bound detection, network captures, source arbitration, and security checks.
"""

import asyncio
import json
import sys
import typing
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.models import FieldType, SchemaField
from app.network_payload_extractor import (
    _is_candidate_secret_heavy,
    _sanitize_payload,
    arbitrate_sources,
    extract_from_network_payloads,
    find_record_arrays,
    score_record_array,
)
from app.page_evidence_collector import collect_page_evidence
from app.selector_engine import apply_selectors
from app.session_url_detector import detect_session_params


async def fetch_and_capture(url: str) -> tuple[str, list[str | dict], dict]:
    """Fetch URL and capture HTML, network JSON payloads, and cookies/session keys."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Error: Playwright is not installed.")
        sys.exit(1)

    html = ""
    captured_payloads: list[str | dict] = []
    state: dict[str, typing.Any] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        async def on_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "application/json" in ct or "json" in response.url:
                    text = await response.text()
                    try:
                        obj = json.loads(text)
                        captured_payloads.append(obj)
                    except (json.JSONDecodeError, ValueError):  # nosec B110 — non-JSON response bodies are dropped by design
                        # Best-effort capture: non-JSON bodies are not JSON
                        # payloads. Dropping them is the intended behavior.
                        pass
            except Exception:  # nosec B110 — network/transport errors on a single response must not abort the whole scrape
                # Best-effort capture: network/transport errors on a single
                # response should not abort the whole scrape.
                pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
            state["cookies"] = [{"name": c["name"], "domain": c.get("domain", "")} for c in await context.cookies()]
            state["localStorage"] = await page.evaluate("() => ({...localStorage})")
            state["sessionStorage"] = await page.evaluate("() => ({...sessionStorage})")
            state["title"] = await page.title()
        except Exception as e:
            state["error"] = str(e)
        finally:
            await browser.close()

    return html, captured_payloads, state


def check_secret_leakage(records: list[dict], field_map: typing.Any) -> bool:
    """Check if raw secrets leak into serialized output."""
    data_to_serialize = {"records": records, "field_map": {k: v.__dict__ for k, v in field_map.items()} if field_map else {}}
    serialized = json.dumps(data_to_serialize).lower()
    secret_patterns = ("bearer", "csrf", "session_id", "api_key", "password", "secret", "token", "jwt", "cookie")
    for pattern in secret_patterns:
        if pattern in serialized:
            return True
    return False


async def smoke(url: str, fields_str: str | None = None):
    # 1. Session detection
    session = detect_session_params(url)
    session_bound = session.get("is_session_bound", False)
    canonical = session.get("canonical_url", url)

    # 2. Fetch and capture
    html, payloads, _state = await fetch_and_capture(url)

    # Parse custom fields
    if fields_str:
        field_names = [f.strip() for f in fields_str.split(",") if f.strip()]
        schema_fields = []
        for name in field_names:
            name_lower = name.lower()
            if any(
                syn in name_lower for syn in ("price", "fare", "cost", "total", "amount", "fee", "rate", "value", "sum", "charge")
            ):
                f_type = FieldType.CURRENCY
            elif any(syn in name_lower for syn in ("date", "day", "time", "schedule")):
                f_type = FieldType.DATE
            elif "rating" in name_lower or "score" in name_lower:
                f_type = FieldType.NUMBER
            else:
                f_type = FieldType.STRING
            schema_fields.append(SchemaField(name=name, field_type=f_type, required=False, description=""))
    else:
        schema_fields = [
            SchemaField(name="name", field_type=FieldType.STRING, required=False, description=""),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="description", field_type=FieldType.STRING, required=False, description=""),
        ]

    # Find record arrays found in network payloads, printing their candidate paths and details
    candidates_list = []
    for p in payloads:
        candidates = find_record_arrays(p)
        for c in candidates:
            is_secret = _is_candidate_secret_heavy(c)
            # Sanitized records
            sanitized_records = _sanitize_payload(c.records)
            c.records = sanitized_records
            score = score_record_array(c, schema_fields)
            candidates_list.append(
                {"path": c.path, "record_count": len(sanitized_records), "score": round(score, 1), "is_secret_heavy": is_secret},
            )

    # 3. Extract from Network Payloads
    net_result = extract_from_network_payloads(payloads, schema_fields)

    # 4. Extract from DOM (using container discovery / default fallback step)
    dom_records: list[dict] = []
    dom_score = 0.0
    if html:
        evidence = collect_page_evidence(html, url=url)
        if evidence.candidate_containers:
            best = evidence.candidate_containers[0]
            selectors = {
                "item_container": best.selector,
                "fields": {sf.name: "" for sf in schema_fields},
            }
            res = apply_selectors(html, selectors, schema_fields)
            dom_records = res if isinstance(res, list) else res[0]
            scores = [r.get("record_score", 0.0) for r in dom_records]
            dom_score = sum(scores) / len(scores) if scores else 0.0

    # 5. Source Arbitration
    winning_records, winning_source, field_map = arbitrate_sources(
        dom_records,
        dom_score,
        net_result,
        schema_fields,
    )

    # Calculate coverage
    if winning_source == "dom":
        coverage = sum(
            1 for r in winning_records[:20] for f in schema_fields if r.get(f.name) is not None and str(r.get(f.name, "")).strip()
        ) / max(len(winning_records[:20]) * len(schema_fields), 1)
    else:
        coverage = net_result.field_coverage if net_result else 0.0

    # 6. Check for secret leakage
    secrets_leaked = check_secret_leakage(winning_records, field_map)

    # Output formatting
    print(f"session_bound: {str(session_bound).lower()}")
    print(f"canonical_url: {canonical}")
    print(f"network_payloads_found: {len(payloads)}")
    print(f"record_array_candidates: {json.dumps(candidates_list)}")
    print(f"winning_source: {winning_source}")
    print(f"record_count: {len(winning_records)}")
    print(f"field_coverage: {coverage:.2f}")

    provenance_paths = {k: v.mapped_from for k, v in field_map.items()} if field_map else {}
    print(f"provenance_paths: {json.dumps(provenance_paths)}")
    print(f"raw_secrets_persisted: {str(secrets_leaked).lower()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/smoke_session_url.py <URL> [comma_separated_schema_fields]")
        sys.exit(1)
    url = sys.argv[1]
    fields_str = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(smoke(url, fields_str))
