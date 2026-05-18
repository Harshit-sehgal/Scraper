"""
Custom scraper for flightsnholidays.co.uk — ASP.NET flight search results.

Uses Playwright with site-specific CSS selectors discovered by inspecting
the actual DOM structure. This bypasses the generic LLM-selector pipeline
which struggles with complex ASP.NET table-based layouts.

Target structure:
  - Result cards: div.flight-result-box (inside #grvResult / #bkg_container01)
  - Origin/destination: .flt-dest-dep span
  - Date: .flt-dest-date
  - Price: .price-main span
  - Stops: .dep-flt-stop
"""

import asyncio
import logging
import re
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


async def scrape_flightsnholidays(url: str, max_wait: int = 30) -> list[dict]:
    """Scrape flight search results from flightsnholidays.co.uk.

    Args:
        url: Full flight search result URL (e.g., flight-result.aspx?...)
        max_wait: Maximum seconds to wait for flight results to render.

    Returns:
        List of dicts with keys: origin, destination, date, price, stops
    """
    logger.info("[FlightScraper] Fetching: %s (max_wait=%ds)", url, max_wait)

    browser = None
    context = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            # Block images/media/fonts for speed
            async def _route_filter(route):
                if route.request.resource_type in {"image", "media", "font"}:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _route_filter)

            try:
                await page.goto(url, wait_until="networkidle", timeout=45000)
            except Exception:
                logger.warning("[FlightScraper] networkidle timeout, trying domcontentloaded")
                await page.goto(url, wait_until="domcontentloaded", timeout=35000)

            # Wait for the flight result cards to appear
            try:
                await page.wait_for_selector("div.flight-result-box", timeout=max_wait * 1000)
                # Extra buffer for any remaining JS rendering
                await asyncio.sleep(2.0)
            except Exception:
                logger.warning("[FlightScraper] No flight-result-box elements found within %ds", max_wait)
                return []

            records = await page.evaluate("""
                () => {
                    const cards = document.querySelectorAll('div.flight-result-box');
                    return Array.from(cards).map(card => {
                        // --- Helper to get clean text from a selector within the card ---
                        const text = (sel) => {
                            const el = card.querySelector(sel);
                            return el ? el.textContent.trim() : null;
                        };

                        // Origin/destination: two spans inside .flt-dest-dep
                        const depSpans = card.querySelectorAll('.flt-dest-dep span');
                        const origin = depSpans.length > 0 ? depSpans[0].textContent.trim() : null;
                        const destination = depSpans.length > 1 ? depSpans[1].textContent.trim() : null;

                        // Date
                        const date = text('.flt-dest-date');

                        // Price
                        const price = text('.price-main span');

                        // Stops
                        const stops = text('.dep-flt-stop');

                        return { origin, destination, date, price, stops };
                    });
                }
            """)

            logger.info("[FlightScraper] Extracted %d records", len(records))
            return records

    except Exception as e:
        logger.exception("[FlightScraper] Fatal error: %s", e)
        return []
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


def parse_price(price_str: Optional[str]) -> Optional[float]:
    """Extract numeric price from a string like '£238' or 'AED 500'."""
    if not price_str:
        return None
    match = re.search(r"[\d,]+(?:\.\d+)?", price_str.replace(",", ""))
    if match:
        return float(match.group(0).replace(",", ""))
    return None


def parse_airport(code: Optional[str]) -> Optional[str]:
    """Normalize airport code — strip whitespace and uppercase."""
    if not code:
        return None
    code = code.strip().upper()
    # Some cards put airline names before airport codes; try to extract the code
    match = re.search(r"\b([A-Z]{3})\b", code)
    return match.group(1) if match else code


if __name__ == "__main__":
    """Quick manual test — run directly:
    python -m app.custom_scrapers.flightsnholidays
    """
    logging.basicConfig(level=logging.INFO)

    test_url = (
        "https://www.flightsnholidays.co.uk/flight-result.aspx"
        "?From=LON&To=PAR&ddate=05/30/2026&retdate=06/01/2026"
        "&Adult=1&Child=0&Infant=0&Class=Economy&FType=-1&IsReturn=1"
    )

    results = asyncio.run(scrape_flightsnholidays(test_url))
    print(f"\nExtracted {len(results)} records:\n")
    for i, r in enumerate(results, 1):
        print(f"  Record {i}:")
        print(f"    Origin:      {r.get('origin')}")
        print(f"    Destination: {r.get('destination')}")
        print(f"    Date:        {r.get('date')}")
        print(f"    Price:       {r.get('price')}")
        print(f"    Stops:       {r.get('stops')}")
        parsed_price = parse_price(r.get("price"))
        if parsed_price:
            print(f"    Price (num):  £{parsed_price:.2f}")
        print()
