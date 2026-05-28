#!/usr/bin/env python3
"""Manual smoke test for session-bound URLs — run against real websites.

Usage:
    python scripts/smoke_session_url.py "https://example.com/search/id/token123"

Prints session-bound detection, network captures, source arbitration, and security checks.
"""

import json
import sys
import re
import asyncio
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.session_url_detector import detect_session_params
from app.models import SchemaField, FieldType
from app.network_payload_extractor import (
    find_record_arrays,
    extract_from_network_payloads,
    arbitrate_sources,
)
from app.page_evidence_collector import collect_page_evidence
from app.selector_engine import apply_selectors


async def fetch_and_capture(url: str) -> tuple[str, list[dict], dict]:
    """Fetch URL and capture HTML, network JSON payloads, and cookies/session keys."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Error: Playwright is not installed.")
        sys.exit(1)

    html = ""
    captured_payloads = []
    state = {}

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
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
            state["cookies"] = [
                {"name": c["name"], "domain": c.get("domain", "")}
                for c in await context.cookies()
            ]
            state["localStorage"] = await page.evaluate("() => ({...localStorage})")
            state["sessionStorage"] = await page.evaluate("() => ({...sessionStorage})")
            state["title"] = await page.title()
        except Exception as e:
            state["error"] = str(e)
        finally:
            await browser.close()

    return html, captured_payloads, state


def check_secret_leakage(data: dict) -> bool:
    """Check if raw secrets leak into serialized output."""
    serialized = json.dumps(data).lower()
    secret_patterns = (
        "bearer", "csrf", "session_id", "api_key", "password",
        "secret", "token", "jwt", "cookie"
    )
    # If any secret pattern is found in key mapping/extraction metadata
    # but not inside expected fields
    for pattern in secret_patterns:
        if pattern in serialized:
            return True
    return False


async def smoke(url: str):
    # 1. Session detection
    session = detect_session_params(url)
    session_bound = session.get("is_session_bound", False)
    canonical = session.get("canonical_url", url)

    # 2. Fetch and capture
    html, payloads, state = await fetch_and_capture(url)

    # Count record arrays found in network payloads
    record_arrays_found = 0
    schema_fields = [
        SchemaField(name="name", field_type=FieldType.STRING, required=False),
        SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        SchemaField(name="description", field_type=FieldType.STRING, required=False),
    ]

    for p in payloads:
        candidates = find_record_arrays(p)
        record_arrays_found += len(candidates)

    # 3. Extract from Network Payloads
    net_result = extract_from_network_payloads(payloads, schema_fields)

    # 4. Extract from DOM (using container discovery / default fallback step)
    dom_records = []
    dom_score = 0.0
    if html:
        evidence = collect_page_evidence(html, url=url)
        if evidence.candidate_containers:
            best = evidence.candidate_containers[0]
            selectors = {
                "item_container": best.selector,
                "fields": {"name": "", "price": "", "description": ""},
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

    best_source = "dom"
    if winning_source != "dom" and net_result:
        best_source = f"network_payload ({net_result.source})"

    # Calculate coverage
    if winning_source == "dom":
        coverage = sum(
            1 for r in winning_records[:20] for f in schema_fields
            if r.get(f.name) is not None and str(r.get(f.name, "")).strip()
        ) / max(len(winning_records[:20]) * len(schema_fields), 1)
    else:
        coverage = net_result.field_coverage if net_result else 0.0

    # 6. Check for secret leakage
    secrets_leaked = False
    if net_result:
        # Check if the field map contains mapped paths with tokens/cookies
        secrets_leaked = check_secret_leakage(net_result.field_map)

    # Output formatting
    print(f"session_bound: {str(session_bound).lower()}")
    print(f"canonical_url: {canonical}")
    print(f"network_payloads_found: {len(payloads)}")
    print(f"record_arrays_found: {record_arrays_found}")
    print(f"best_source: {best_source}")
    print(f"records_extracted: {len(winning_records)}")
    print(f"field_coverage: {coverage:.2f}")
    print(f"raw_secrets_persisted: {str(secrets_leaked).lower()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/smoke_session_url.py <URL>")
        sys.exit(1)
    asyncio.run(smoke(sys.argv[1]))
