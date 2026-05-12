#!/usr/bin/env python3
"""Standalone regex extraction test — no Playwright, no g4f, just BS4."""
import json
import re
import sys

sys.path.insert(0, '/home/harshit/Documents/Work/Money/scraper/backend')

from bs4 import BeautifulSoup

html = open('/home/harshit/Documents/Work/Money/scraper/backend/test_page.html').read()
print(f"HTML length: {len(html)}")

soup = BeautifulSoup(html, "html.parser")

# Find articles with class product
containers = soup.find_all("article", class_=re.compile(r'product', re.I))
print(f"Found {len(containers)} product containers")

results = []
for c in containers:
    title_el = c.find("h3")
    link = title_el.find("a") if title_el else None
    title = link.get("title", link.get_text(strip=True)) if link else "N/A"
    
    price_el = c.find(class_=re.compile(r'price_color', re.I))
    price = price_el.get_text(strip=True) if price_el else "N/A"
    
    star_el = c.find(class_=re.compile(r'star|rating', re.I))
    rating = "N/A"
    if star_el:
        for cls in star_el.get("class", []):
            for w in ['One','Two','Three','Four','Five']:
                if w in cls:
                    rating = w
    
    stock_el = c.find(class_=re.compile(r'avail|stock', re.I))
    stock = stock_el.get_text(strip=True) if stock_el else "N/A"
    
    results.append({
        "book_title": title,
        "price": price,
        "rating": rating,
        "availability": stock,
    })

print(f"\n=== RESULTS: {len(results)} records ===\n")
for r in results:
    print(json.dumps(r, indent=2))
