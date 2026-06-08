"""Standalone regex extraction test — no Playwright, no g4f, just BS4."""

import re
from pathlib import Path

from bs4 import BeautifulSoup


def main() -> None:
    with open(Path(__file__).parent / "test_page.html") as f:  # noqa: PTH123
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")

    # Find articles with class product
    containers = soup.find_all("article", class_=re.compile(r"product", re.IGNORECASE))

    results = []
    for c in containers:
        title_el = c.find("h3")
        link = title_el.find("a") if title_el else None
        title = link.get("title", link.get_text(strip=True)) if link else "N/A"

        price_el = c.find(class_=re.compile(r"price_color", re.IGNORECASE))
        price = price_el.get_text(strip=True) if price_el else "N/A"

        star_el = c.find(class_=re.compile(r"star|rating", re.IGNORECASE))
        rating = "N/A"
        if star_el:
            classes = star_el.get("class")
            class_list: list[str] = []
            if isinstance(classes, list):
                class_list = classes
            elif isinstance(classes, str):
                class_list = [classes]
            for cls in class_list:
                for w in ["One", "Two", "Three", "Four", "Five"]:
                    if w in cls:
                        rating = w

        stock_el = c.find(class_=re.compile(r"avail|stock", re.IGNORECASE))
        stock = stock_el.get_text(strip=True) if stock_el else "N/A"

        results.append(
            {
                "book_title": title,
                "price": price,
                "rating": rating,
                "availability": stock,
            },
        )

    for _r in results:
        pass


if __name__ == "__main__":
    main()
