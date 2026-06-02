import asyncio
import csv

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


async def scrape_threebest():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"  # noqa: E501
        )
        page = await context.new_page()
        print("Navigating to Three Best Rated...")
        await page.goto("https://threebestrated.in/interior-designers-in-chennai", wait_until="networkidle")

        # Scrape content
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # ThreeBestRated usually wraps businesses in specific article or div elements
        # Usually it's `.single-business` or similar class
        businesses = soup.select(".list-item")
        if not businesses:
            businesses = soup.select(".gb-list > li")
        if not businesses:
            businesses = soup.select(".rating-list > div, .rating-list li")
        if not businesses:
            businesses = soup.select("div.col-md-4")

        # Let's try broad selection if class names change
        print(f"Discovered {len(businesses)} potential elements. Refining...")

        # We can also just read the raw text block if classes fail
        soup.get_text(separator="\n").split("\n")

        # A more dynamic fallback: iterate strong headers
        businesses = []
        h2s = soup.find_all("h2")
        h3s = soup.find_all("h3")
        headers = h2s + h3s
        for header in headers:
            text = header.get_text(strip=True)
            if len(text) > 3 and "interior" not in text.lower() and "best" not in text.lower():
                parent = header.parent
                if parent:
                    desc_text = parent.get_text(separator=" | ")

                    # Extract phone number via regex
                    import re

                    phone = re.search(r"\+91[\s\-]?\d{4,5}[\s\-]?\d{4,5}|\b\d{10}\b", desc_text)
                    phone_str = phone.group(0) if phone else "Not Found"

                    # Extract typical rating (e.g. 4.9/5)
                    rating = re.search(r"\d\.\d\s?(?:Star|/5|Stars)?", desc_text)
                    rating_str = rating.group(0) if rating else "Not Found"

                    businesses.append(
                        {
                            "company_name": text,
                            "phone": phone_str.strip(),
                            "address_or_location": "Chennai",  # generic
                            "rating": rating_str.strip(),
                        }
                    )

        await browser.close()

        # The above logic might be noisy, let's keep only items with a matched phone number or rating
        valid_businesses = [b for b in businesses if b["phone"] != "Not Found" or b["rating"] != "Not Found"]

        # Deduplicate
        seen = set()
        unique_designers = []
        for b in valid_businesses:
            if b["company_name"] not in seen:
                seen.add(b["company_name"])
                unique_designers.append(b)

        print(f"Extracted {len(unique_designers)} verified designers.")

        with open(
            "/home/harshit/Documents/Work/Money/scraper/chennai_interior_designers.csv", "w", newline="", encoding="utf-8"
        ) as f:  # noqa: E501
            writer = csv.DictWriter(f, fieldnames=["company_name", "phone", "address_or_location", "rating"])
            writer.writeheader()
            writer.writerows(unique_designers)
        print("Saved to CSV.")


if __name__ == "__main__":
    asyncio.run(scrape_threebest())
