#!/usr/bin/env python3
"""Enrich curated Chennai interior designer leads with contact details."""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 15

BLOCKED_DOMAINS = {
    "houzz.in",
    "justdial.com",
    "magicbricks.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "x.com",
    "twitter.com",
    "pinterest.com",
    "maps.google.com",
    "google.com",
    "g.co",
    "yelp.com",
    "wikipedia.org",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_FULL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s()\-]{8,}\d)")
PIN_RE = re.compile(r"\b\d{6}\b")

PLACEHOLDER_VALUES = {
    "home",
    "contact",
    "contact us",
    "about",
    "about us",
    "learn more",
    "read more",
    "view more",
    "click here",
    "details",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "-",
    "--",
}

INVALID_EMAIL_DOMAINS = {
    "example.com",
    "test.com",
    "domain.com",
    "localhost",
}


@dataclass
class EnrichmentContext:
    city: str
    niche: str
    country_name: str
    country_code: str


CITY_COUNTRY_MAP = {
    "chennai": ("India", "+91"),
    "mumbai": ("India", "+91"),
    "delhi": ("India", "+91"),
    "bangalore": ("India", "+91"),
    "bengaluru": ("India", "+91"),
    "kolkata": ("India", "+91"),
    "london": ("United Kingdom", "+44"),
    "paris": ("France", "+33"),
    "new york": ("United States", "+1"),
    "nyc": ("United States", "+1"),
    "san francisco": ("United States", "+1"),
    "chicago": ("United States", "+1"),
    "los angeles": ("United States", "+1"),
    "lax": ("United States", "+1"),
}


def infer_enrichment_context(input_file: Path, records: list[dict]) -> EnrichmentContext:
    filename = input_file.stem.lower()
    words = re.split(r"\W+|_", filename)
    
    city = None
    country_name = None
    country_code = None
    niche_words = []
    
    for word in words:
        if word in CITY_COUNTRY_MAP:
            city = word.title()
            country_name, country_code = CITY_COUNTRY_MAP[word]
        elif word in ["interior", "design", "designer", "designers", "architect", "architects", "lead", "leads", "leadlist"]:
            niche_words.append(word)
            
    if not city and records:
        for r in records:
            addr = str(r.get("address") or r.get("address_or_location") or r.get("location") or "").lower()
            if not addr:
                continue
            for k, (cntry, code) in CITY_COUNTRY_MAP.items():
                if k in addr:
                    city = k.title()
                    country_name = cntry
                    country_code = code
                    break
            if city:
                break
                
    if not city:
        city = "Chennai"
        country_name = "India"
        country_code = "+91"
        
    assert country_name is not None and country_code is not None, "country name/code must be set"
        
    niche = " ".join(niche_words).title() if niche_words else "Interior Designer"
    niche = niche.replace("Designers", "Designer").replace("Architects", "Architect")
    
    return EnrichmentContext(
        city=city,
        niche=niche,
        country_name=country_name,
        country_code=country_code
    )


@dataclass
class ContactData:
    emails: list[str]
    phones: list[str]
    addresses: list[str]


def workspace_root() -> Path:
    return Path(__file__).resolve().parent.parent


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception as e:
        import logging
        logging.exception(e)
        return ""


def is_blocked_domain(url: str) -> bool:
    d = domain_of(url)
    return any(d == b or d.endswith(f".{b}") for b in BLOCKED_DOMAINS)


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for v in values:
        if not v:
            continue
        key = v.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(v.strip())
    return result


def normalized_text_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def is_placeholder_text(value: str) -> bool:
    key = normalized_text_key(value)
    if not key:
        return True
    if key in PLACEHOLDER_VALUES:
        return True
    if key.startswith(("read ", "learn ", "click ", "view ")) and "more" in key:
        return True
    if re.fullmatch(r"\+?\d+\s+more", key):
        return True
    return False


def normalize_phone(value: str, country_code: str = "+91") -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -:;,.|")
    if not text or is_placeholder_text(text):
        return None

    digits = re.sub(r"\D", "", text)
    # Support shorter local numbers in some countries (minimum 7 digits)
    if len(digits) < 7 or len(digits) > 15:
        return None
    if len(set(digits)) <= 2:
        return None

    prefix_clean = country_code.replace("+", "")
    
    if text.startswith("+"):
        return text

    if country_code == "+91":
        if len(digits) == 10:
            return f"+91 {digits}"
        if len(digits) == 11 and digits.startswith("0"):
            return f"+91 {digits[1:]}"
        if len(digits) == 12 and digits.startswith("91"):
            return f"+91 {digits[2:]}"
    elif country_code == "+44":
        if len(digits) == 10:
            return f"+44 {digits}"
        if len(digits) == 11 and digits.startswith("0"):
            return f"+44 {digits[1:]}"
        if len(digits) == 12 and digits.startswith("44"):
            return f"+44 {digits[2:]}"
    elif country_code == "+1":
        if len(digits) == 10:
            return f"+1 {digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+1 {digits[1:]}"

    if digits.startswith(prefix_clean):
        return f"{country_code} {digits[len(prefix_clean):]}"
    if digits.startswith("0"):
        return f"{country_code} {digits[1:]}"
    return f"{country_code} {digits}"


def valid_email(value: str) -> bool:
    lower = str(value or "").lower().strip(" .,;:")
    if not EMAIL_FULL_RE.match(lower):
        return False

    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")):
        return False
    local_part, _, domain = lower.partition("@")
    if local_part in {"noreply", "no-reply", "donotreply", "do-not-reply", "test"}:
        return False
    if domain in INVALID_EMAIL_DOMAINS:
        return False
    if "invalid" in domain or "placeholder" in domain:
        return False
    return True


def normalize_email(value: str) -> str | None:
    email = str(value or "").strip().lower().strip(" .,;:")
    return email if valid_email(email) else None


def normalize_address(value: str) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,;:-")
    if len(text) < 12:
        return None
    if is_placeholder_text(text):
        return None
    if not re.search(r"[A-Za-z]", text):
        return None
    return text


def normalize_website(value: str) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "https://" + url.lstrip("/")
    return url


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception as e:
        import logging
        logging.exception(e)
        return default


def fetch_html(url: str) -> str:
    normalized_url = normalize_website(url)
    if not normalized_url:
        raise ValueError("Empty URL")

    headers = {"User-Agent": USER_AGENT}
    response = requests.get(normalized_url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response.text


def extract_addresses_from_json_ld(soup: BeautifulSoup) -> list[str]:
    addresses: list[str] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(tag.get_text(strip=True) or "{}")
        except Exception as e:
            import logging
            logging.exception(e)
            continue

        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            addr = node.get("address")
            if isinstance(addr, dict):
                parts = [
                    addr.get("streetAddress") or "",
                    addr.get("addressLocality") or "",
                    addr.get("addressRegion") or "",
                    addr.get("postalCode") or "",
                ]
                joined = ", ".join(p.strip() for p in parts if p and str(p).strip())
                if joined:
                    addresses.append(joined)
    return dedupe_keep_order(addresses)


def extract_contact_data_from_html(html: str, context: EnrichmentContext) -> ContactData:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.extract()

    email_candidates: list[str] = []
    phone_candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        href_lower = href.lower()
        if href_lower.startswith("mailto:"):
            candidate = href.split(":", 1)[1].split("?", 1)[0]
            email = normalize_email(candidate)
            if email:
                email_candidates.append(email)
        elif href_lower.startswith("tel:"):
            candidate = href.split(":", 1)[1].split("?", 1)[0]
            phone = normalize_phone(candidate, country_code=context.country_code)
            if phone:
                phone_candidates.append(phone)

    text = soup.get_text("\n", strip=True)

    for e in EMAIL_RE.findall(text):
        email = normalize_email(e)
        if email:
            email_candidates.append(email)
    emails = dedupe_keep_order(email_candidates)

    for p in PHONE_RE.findall(text):
        n = normalize_phone(p, country_code=context.country_code)
        if n:
            phone_candidates.append(n)
    phones = dedupe_keep_order(phone_candidates)

    addresses = extract_addresses_from_json_ld(soup)

    if not addresses:
        lines = re.split(r"[\n|]", text)
        city_lower = context.city.lower()
        country_lower = context.country_name.lower()
        for line in lines:
            line = re.sub(r"\s+", " ", line).strip(" ,")
            if len(line) < 20:
                continue
            if "http://" in line.lower() or "https://" in line.lower() or "@" in line:
                continue
            if city_lower in line.lower() and (
                country_lower in line.lower()
                or any(w in line.lower() for w in ["road", "street", "building", "floor", "avenue", "lane", "postal"])
                or PIN_RE.search(line)
            ):
                addresses.append(line[:220])

    addresses = dedupe_keep_order([a for a in (normalize_address(a) for a in addresses) if a])

    return ContactData(emails=emails, phones=phones, addresses=addresses)


def candidate_contact_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    normalized_base = normalize_website(base_url)
    base_domain = domain_of(normalized_base)
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        href_lower = href.lower()
        if href_lower.startswith("mailto:") or href_lower.startswith("tel:") or href_lower.startswith("javascript:"):
            continue

        full = urljoin(normalized_base, href).split("#", 1)[0]
        full_domain = domain_of(full)
        if full_domain != base_domain:
            continue

        low = full.lower()
        anchor_text = (a.get_text(" ", strip=True) or "").lower()
        if any(
            k in low or k in anchor_text
            for k in ["contact", "about", "reach", "get-in-touch", "connect", "enquiry"]
        ):
            links.append(full)
    return dedupe_keep_order(links)[:2]


def _company_tokens(company_name: str) -> list[str]:
    return [t for t in re.split(r"\W+", (company_name or "").lower()) if len(t) > 2][:5]


def _score_website_candidate(result: dict, company_name: str) -> float:
    url = normalize_website(result.get("href") or "")
    if not url or is_blocked_domain(url):
        return -1.0

    domain = domain_of(url)
    title = (result.get("title") or "").lower()
    body = (result.get("body") or "").lower()
    blob = f"{title} {body}"
    tokens = _company_tokens(company_name)

    score = 0.0
    if domain:
        score += 0.2
    if "official" in blob:
        score += 0.15
    if any(k in domain for k in ["interior", "design", "studio", "decor", "architect"]):
        score += 0.1
    if any(k in domain for k in ["list", "directory", "best", "top"]):
        score -= 0.25

    domain_hits = sum(1 for t in tokens if t in domain)
    blob_hits = sum(1 for t in tokens if t in blob)
    score += min(domain_hits * 0.35, 1.05)
    score += min(blob_hits * 0.12, 0.36)
    return score


def search_official_website(company_name: str, context: EnrichmentContext) -> str | None:
    query = f"{company_name} {context.city} {context.niche} official website"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=8))
    except Exception as e:
        import logging
        logging.exception(e)
        return None

    ranked: list[tuple[float, str]] = []
    for r in results:
        url = normalize_website((r.get("href") or "").strip())
        if not url:
            continue
        score = _score_website_candidate(r, company_name=company_name)
        if score <= 0:
            continue
        ranked.append((score, url))

    if not ranked:
        return None

    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


def enrich_lead(lead: dict, context: EnrichmentContext) -> dict:
    enriched = dict(lead)

    company_name = str(lead.get("company_name") or "").strip()
    email = (lead.get("email") or "").strip()
    source_url = (lead.get("source_url") or "").strip()

    if not company_name or company_name == "null" or "File not found" in company_name or len(company_name) < 3:
        inferred = ""
        if source_url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(source_url).netloc.lower().replace("www.", "")
                part = domain.split(".")[0]
                if part and len(part) >= 3:
                    inferred = part.replace("-", " ").replace("_", " ").title()
            except Exception:
                pass
        if not inferred and email and "@" in email:
            try:
                domain = email.split("@")[1]
                part = domain.split(".")[0]
                if part and len(part) >= 3:
                    inferred = part.replace("-", " ").replace("_", " ").title()
            except Exception:
                pass
        company_name = inferred or "Unknown Studio"

    enriched["company_name"] = company_name
    website = normalize_website(lead.get("website") or "")
    if website and is_blocked_domain(website):
        website = ""

    existing_phone = normalize_phone(enriched.get("phone") or enriched.get("contact_phone") or "", country_code=context.country_code)
    existing_email = normalize_email(enriched.get("email") or "")
    existing_address = normalize_address(enriched.get("address") or enriched.get("address_or_location") or "")

    if existing_phone:
        enriched["phone"] = existing_phone
    elif "phone" in enriched:
        enriched["phone"] = ""

    if existing_email:
        enriched["email"] = existing_email
    elif "email" in enriched:
        enriched["email"] = ""

    if existing_address:
        enriched["address"] = existing_address
    elif "address" in enriched:
        enriched["address"] = ""

    official_website = None
    if website:
        official_website = website
    else:
        official_website = search_official_website(company_name, context=context)

    emails: list[str] = []
    phones: list[str] = []
    addresses: list[str] = []
    sources: list[str] = []

    targets = []
    if official_website:
        targets.append(official_website)
    if website and website != official_website:
        targets.append(website)

    for idx, url in enumerate(dedupe_keep_order(targets)):
        try:
            html = fetch_html(url)
        except Exception as e:
            import logging
            logging.exception(e)
            continue

        data = extract_contact_data_from_html(html, context=context)
        emails.extend(data.emails)
        phones.extend(data.phones)
        addresses.extend(data.addresses)
        sources.append(normalize_website(url))

        if idx < 2:
            for cl in candidate_contact_links(url, html):
                try:
                    contact_html = fetch_html(cl)
                except Exception as e:
                    import logging
                    logging.exception(e)
                    continue
                cdata = extract_contact_data_from_html(contact_html, context=context)
                emails.extend(cdata.emails)
                phones.extend(cdata.phones)
                addresses.extend(cdata.addresses)
                sources.append(normalize_website(cl))
                time.sleep(0.3)

        if emails or phones:
            break

    emails = dedupe_keep_order([e for e in (normalize_email(v) for v in emails) if e])
    phones = dedupe_keep_order([p for p in (normalize_phone(v, country_code=context.country_code) for v in phones) if p])
    addresses = dedupe_keep_order([a for a in (normalize_address(v) for v in addresses) if a])

    if phones and not normalize_phone(enriched.get("phone") or "", country_code=context.country_code):
        enriched["phone"] = phones[0]
    if emails and not normalize_email(enriched.get("email") or ""):
        enriched["email"] = emails[0]
    if addresses and not normalize_address(enriched.get("address") or ""):
        enriched["address"] = addresses[0]

    enriched["official_website"] = official_website
    enriched["emails_found"] = emails
    enriched["phones_found"] = phones
    enriched["addresses_found"] = addresses
    enriched["enrichment_sources"] = dedupe_keep_order(sources)

    confidence = 0.0
    has_phone = bool(normalize_phone(enriched.get("phone") or "", country_code=context.country_code))
    has_email = bool(normalize_email(enriched.get("email") or ""))
    has_address = bool(normalize_address(enriched.get("address") or ""))

    if enriched.get("official_website"):
        confidence += 0.3
    if has_phone:
        confidence += 0.35
    if has_email:
        confidence += 0.25
    if has_address:
        confidence += 0.1
    if len(enriched.get("enrichment_sources") or []) >= 2:
        confidence += 0.05

    enriched["enrichment_confidence"] = round(min(confidence, 1.0), 2)
    if has_phone or has_email:
        enriched["enrichment_status"] = "enriched"
    elif enriched.get("official_website"):
        enriched["enrichment_status"] = "website_only"
    else:
        enriched["enrichment_status"] = "not_found"

    return enriched


def main() -> None:
    import sys
    root = workspace_root()

    input_json = None
    if len(sys.argv) > 1:
        input_json = Path(sys.argv[1])
    else:
        # Heuristically scan for lead files in workspace root
        candidates = list(root.glob("*leads*.json")) + list(root.glob("*cleaned*.json"))
        # Exclude already enriched files
        candidates = [c for c in candidates if "enriched" not in c.name]
        if candidates:
            input_json = candidates[0]
        else:
            input_json = root / "chennai_leads.json"

    if not input_json.exists():
        print(f"Error: Lead file not found at {input_json}. Please run the scraper first.")
        return

    print(f"Processing lead file: {input_json}")
    leads = json.loads(input_json.read_text(encoding="utf-8"))

    # Dynamic Context Auto-Analysis & Parameter Inference
    context = infer_enrichment_context(input_json, leads)
    print("\n" + "="*40)
    print(" DYNAMIC ENRICHMENT CONTEXT INFERRED")
    print("="*40)
    print(f"  Target City:   {context.city}")
    print(f"  Target Niche:  {context.niche}")
    print(f"  Country Name:  {context.country_name}")
    print(f"  Dial Code:     {context.country_code}")
    print("="*40 + "\n")

    # Dynamic Output Paths
    stem = input_json.stem
    base_name = re.sub(r"(_cleaned|_leads)$", "", stem)
    out_json = root / f"{base_name}_enriched.json"
    out_csv = root / f"{base_name}_enriched.csv"

    enriched_rows = []
    enriched_count = 0
    with_phone = 0
    with_email = 0
    with_address = 0

    for i, lead in enumerate(leads, start=1):
        name = lead.get("company_name") or "<unknown>"
        print(f"[{i}/{len(leads)}] Enriching: {name}")
        try:
            row = enrich_lead(lead, context=context)
        except Exception as e:
            import logging
            logging.exception(e)
            row = dict(lead)
            row["enrichment_status"] = f"error: {e}"
            row["enrichment_confidence"] = 0.0
            row["official_website"] = row.get("website")
            row["emails_found"] = []
            row["phones_found"] = []
            row["addresses_found"] = []
            row["enrichment_sources"] = []

        enriched_rows.append(row)

        if row.get("enrichment_status") == "enriched":
            enriched_count += 1
        if normalize_phone(row.get("phone") or "", country_code=context.country_code):
            with_phone += 1
        if normalize_email(row.get("email") or ""):
            with_email += 1
        if normalize_address(row.get("address") or ""):
            with_address += 1

        time.sleep(0.4)

    status_rank = {"enriched": 0, "website_only": 1, "not_found": 2}
    enriched_rows.sort(
        key=lambda r: (
            status_rank.get(str(r.get("enrichment_status") or ""), 3),
            -safe_float(r.get("enrichment_confidence"), default=0.0),
            str(r.get("company_name") or "").lower(),
        )
    )

    out_json.write_text(json.dumps(enriched_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    fieldnames = [
        "company_name",
        "phone",
        "email",
        "website",
        "official_website",
        "address",
        "source_url",
        "record_score",
        "enrichment_status",
        "enrichment_confidence",
        "emails_found",
        "phones_found",
        "addresses_found",
        "enrichment_sources",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in enriched_rows:
            payload = {k: row.get(k) for k in fieldnames}
            for key in ["emails_found", "phones_found", "addresses_found", "enrichment_sources"]:
                value = payload.get(key)
                if isinstance(value, list):
                    payload[key] = " | ".join(str(v) for v in value)
            writer.writerow(payload)

    print("\n=== ENRICHMENT SUMMARY ===")
    print(f"Total rows: {len(enriched_rows)}")
    print(f"Rows enriched (phone/email found): {enriched_count}")
    print(f"Rows with phone: {with_phone}")
    print(f"Rows with email: {with_email}")
    print(f"Rows with address: {with_address}")
    print(f"JSON: {out_json}")
    print(f"CSV:  {out_csv}")


if __name__ == "__main__":
    main()
