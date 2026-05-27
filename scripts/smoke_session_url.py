#!/usr/bin/env python3
"""Manual smoke test for session-bound URLs — run against real websites.

Usage:
    python scripts/smoke_session_url.py "https://example.com/search/id/token123"

Prints session-bound detection, browser state evidence, extraction quality,
and secret leakage status. Does NOT persist raw secrets.
"""

import json
import sys
import time
import asyncio
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.session_url_detector import detect_session_params
from app.page_evidence_collector import collect_page_evidence
from app.models import SchemaField, FieldType


async def fetch_with_playwright(url: str) -> tuple[str, dict]:
    """Fetch a URL with Playwright and capture browser state."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "", {"error": "playwright not installed"}
    state = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = await page.content()
            state["cookies"] = [
                {"name": c["name"], "domain": c.get("domain", "")}
                for c in await page.context.cookies()
            ]
            state["localStorage_keys"] = await page.evaluate(
                "() => Object.keys(localStorage)"
            )
            state["sessionStorage_keys"] = await page.evaluate(
                "() => Object.keys(sessionStorage)"
            )
            state["title"] = await page.title()
        except Exception as e:
            html = ""
            state["error"] = str(e)
        finally:
            await browser.close()
    return html, state


def check_secret_leakage(data: dict) -> list[str]:
    """Check if raw secrets leak into serialized output."""
    leaked = []
    serialized = json.dumps(data)
    secret_keys = (
        "cookie", "localStorage", "sessionStorage", "auth_token",
        "bearer", "csrf", "session_id", "api_key",
    )
    for key in secret_keys:
        if key in serialized.lower():
            leaked.append(key)
    return leaked


async def smoke(url: str):
    print(f"\n{'='*60}")
    print(f"Smoke Test: {url}")
    print(f"{'='*60}")

    # 1. Session detection
    session = detect_session_params(url)
    print(f"\n  session_bound:       {session.get('is_session_bound')}")
    print(f"  canonical_url:       {session.get('canonical_url')}")
    print(f"  ephemeral_params:    {session.get('ephemeral_params')}")
    print(f"  confidence:          {session.get('confidence', 0):.2f}")

    # 2. Fetch with browser
    print(f"\n  Fetching with Playwright...")
    html, browser_state = await fetch_with_playwright(url)
    if browser_state.get("error"):
        print(f"  ERROR: {browser_state['error']}")
        return
    print(f"  HTML length:         {len(html)} chars")
    print(f"  Page title:          {browser_state.get('title', 'N/A')}")
    print(f"  Cookies:             {len(browser_state.get('cookies', []))} found")
    print(f"  localStorage keys:   {browser_state.get('localStorage_keys', [])}")
    print(f"  sessionStorage keys: {browser_state.get('sessionStorage_keys', [])}")

    # 3. Evidence collection
    if html:
        evidence = collect_page_evidence(html, url=url)
        print(f"\n  DOM nodes:           {evidence.dom_node_count}")
        print(f"  Containers found:    {len(evidence.candidate_containers)}")
        print(f"  Visible text length: {evidence.visible_text_length}")
        print(f"  Page structure:      {evidence.page_structure}")

    # 4. Try basic extraction with generic schema
    if html and evidence.candidate_containers:
        from app.selector_engine import apply_selectors
        best = evidence.candidate_containers[0]
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING),
            SchemaField(name="price", field_type=FieldType.CURRENCY),
        ]
        selectors = {
            "item_container": best.selector,
            "fields": {"name": "", "price": ""},
        }
        result = apply_selectors(html, selectors, schema)
        records = result if isinstance(result, list) else result[0]
        print(f"\n  Records extracted:   {len(records)}")
        if records:
            sample = {k: v for k, v in records[0].items() if v and k != "record_score"}
            print(f"  Sample record:       {json.dumps(sample)[:200]}")
            print(f"  Avg record_score:    {sum(r.get('record_score',0) for r in records)/len(records):.2f}")

    # 5. Secret leak check
    leaked = check_secret_leakage({
        "html_preview": html[:500] if html else "",
        "browser_state": browser_state,
    })
    if leaked:
        print(f"\n  WARNING: Potential secret keys found: {leaked}")
    else:
        print(f"\n  raw_secrets_persisted: false")

    print(f"\n{'='*60}")
    print("Done.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/smoke_session_url.py <URL>")
        print("Example: python scripts/smoke_session_url.py 'https://example.com/search/id/token'")
        sys.exit(1)
    asyncio.run(smoke(sys.argv[1]))
