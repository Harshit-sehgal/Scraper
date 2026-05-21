"""
Auto-Discovery Engine: Given a topic/query, automatically finds the best
web pages to scrape by searching the web and ranking results.
Uses free search via DuckDuckGo.
"""

import logging
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse, urlunparse

from ddgs import DDGS

from app.async_utils import run_sync_in_thread
from app.config import settings
from app.models import SourcePolicy

NOISY_URL_PARTS = (
    "/login",
    "/signin",
    "/signup",
    "/cart",
    "/privacy",
    "/terms",
    "/tag/",
    "/wp-admin",
    "facebook.com/sharer",
    "linkedin.com/share",
)

LISTING_HINTS = (
    "directory",
    "listing",
    "best",
    "top",
    "near me",
    "companies",
    "services",
    "providers",
    "contact",
)

SOCIAL_ROOT_DOMAINS = set(d.strip() for d in settings.DISCOVERY_SOCIAL_DOMAINS.split(","))

DIRECTORY_ROOT_DOMAINS = set(d.strip() for d in settings.DISCOVERY_DIRECTORY_DOMAINS.split(","))

SEARCH_ROOT_DOMAINS = set(d.strip() for d in settings.DISCOVERY_SEARCH_DOMAINS.split(","))

SOURCE_TRUST_SCORE = {
    "official": settings.SOURCE_TRUST_OFFICIAL,
    "directory": settings.SOURCE_TRUST_DIRECTORY,
    "social": settings.SOURCE_TRUST_SOCIAL,
    "search_result": settings.SOURCE_TRUST_SEARCH,
}

# Domains that repeatedly fail to resolve/connect can be excluded from discovery.
def _get_blocked_domains() -> set[str]:
    from app.config import settings
    return {
        token.strip().lower()
        for token in (settings.BLOCKED_DISCOVERY_DOMAINS or "").split(",")
        if token.strip()
    }


BLOCKED_DISCOVERY_ROOT_DOMAINS = _get_blocked_domains()


def _root_domain(domain: str) -> str:
    parts = [p for p in (domain or "").lower().split(".") if p]
    if len(parts) < 2:
        return domain.lower()
    return ".".join(parts[-2:])


def _domain_matches(domain: str, allowed_domains: set[str]) -> bool:
    """Match either an exact hostname or its root domain."""
    domain = (domain or "").lower().strip()
    if not domain:
        return False
    if domain in allowed_domains:
        return True
    return _root_domain(domain) in allowed_domains


def _canonicalize_url(url: str) -> str:
    try:
        p = urlparse((url or "").strip())
        if not p.scheme or not p.netloc:
            return ""
        path = (p.path or "/").rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", "", ""))
    except Exception as e:
        logging.exception(e)
        return ""


def infer_source_metadata(url: str, title: str = "", body: str = "") -> dict:
    source_domain = _extract_domain(url)

    if _domain_matches(source_domain, SOCIAL_ROOT_DOMAINS):
        source_type = "social"
    elif _domain_matches(source_domain, DIRECTORY_ROOT_DOMAINS):
        source_type = "directory"
    elif _domain_matches(source_domain, SEARCH_ROOT_DOMAINS):
        source_type = "search_result"
    else:
        blob = f"{title} {body} {(url or '').lower()}"
        if any(h in blob for h in ["directory", "listing", "best", "top", "near me"]):
            source_type = "directory"
        else:
            source_type = "official"

    return {
        "source_domain": source_domain,
        "source_type": source_type,
        "source_trust_score": SOURCE_TRUST_SCORE.get(source_type, 0.4),
    }


def _source_allowed(source_type: str, source_policy: SourcePolicy | str) -> bool:
    policy = source_policy.value if isinstance(source_policy, SourcePolicy) else str(source_policy)
    if policy == SourcePolicy.OFFICIAL_ONLY.value:
        return source_type == "official"
    if policy == SourcePolicy.OFFICIAL_PLUS_DIRECTORY.value:
        return source_type in {"official", "directory"}
    return True


def _source_bonus(source_type: str) -> float:
    if source_type == "official":
        return 0.28
    if source_type == "directory":
        return 0.1
    if source_type == "social":
        return -0.08
    if source_type == "search_result":
        return -0.2
    return 0.0


def _has_query_signal(query: str, blob: str) -> bool:
    terms = [t for t in query.lower().split() if len(t) > 3][:4]
    if not terms:
        return True

    hits = sum(1 for t in terms if t in blob)
    required = 1 if len(terms) <= 2 else 2
    return hits >= required


def _build_search_query(
    query: str,
    location: str,
    domain: str,
    data_fields: list[str],
    origin_location: str,
    max_distance_km: Optional[float],
) -> str:
    parts: list[str] = [query.strip()]

    compact_fields = [f.strip().replace("_", " ") for f in data_fields if f and f.strip()]
    if compact_fields:
        parts.append(" ".join(compact_fields[:4]))

    if location:
        parts.append(f"in {location.strip()}")

    if origin_location and max_distance_km is not None and max_distance_km > 0:
        parts.append(f"within {int(max_distance_km)} km of {origin_location.strip()}")

    if domain:
        parts.append(f"site:{domain.strip()}")

    return " ".join(p for p in parts if p)


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception as e:
        logging.exception(e)
        return ""


def _looks_noisy_url(url: str) -> bool:
    u = (url or "").lower().strip()
    if not u.startswith("http"):
        return True
    if u.endswith(".pdf"):
        return True
    domain = _extract_domain(u)
    if domain and _domain_matches(domain, BLOCKED_DISCOVERY_ROOT_DOMAINS):
        return True
    return any(part in u for part in NOISY_URL_PARTS)


def _contact_fields_requested(data_fields: list[str]) -> bool:
    merged = " ".join(f.replace("_", " ").lower() for f in data_fields if f)
    return any(token in merged for token in ["phone", "email", "contact", "whatsapp"])


def _score_result(item: dict, query: str, location: str, data_fields: list[str], source_type: str) -> float:
    title = (item.get("title") or "").lower()
    body = (item.get("body") or "").lower()
    href = (item.get("href") or "").lower()
    blob = f"{title} {body} {href}"

    score = 0.1

    query_terms = [t for t in query.lower().split() if len(t) > 2][:6]
    score += sum(0.25 for t in query_terms if t in blob)

    if location:
        loc_terms = [t for t in location.lower().split() if len(t) > 2][:4]
        score += sum(0.2 for t in loc_terms if t in blob)

    field_terms = [f.replace("_", " ").lower() for f in data_fields if f]
    score += sum(0.15 for f in field_terms if f in blob)

    if any(h in blob for h in LISTING_HINTS):
        score += 0.35

    if "contact" in href or "directory" in href or "list" in href:
        score += 0.25

    if _contact_fields_requested(data_fields):
        if source_type == "directory":
            score += 0.35
        elif source_type == "official":
            score += 0.05

    if _looks_noisy_url(href):
        score -= 1.0

    score += _source_bonus(source_type)

    return round(score, 3)


async def discover_urls(
    query: str,
    domain: str = "",
    num_results: int = 10,
    location: str = "",
    data_fields: Optional[list[str]] = None,
    origin_location: str = "",
    max_distance_km: Optional[float] = None,
    source_policy: SourcePolicy = SourcePolicy.ALL_SOURCES,
    max_per_domain: int = 4,
) -> list[dict]:
    """
    Auto-discover the best URLs to scrape for a given query.
    Uses DDG search and lightweight ranking to prioritize high-signal pages.
    """
    data_fields = data_fields or []

    search_query = _build_search_query(
        query=query,
        location=location,
        domain=domain,
        data_fields=data_fields,
        origin_location=origin_location,
        max_distance_km=max_distance_km,
    )

    logging.info("DuckDuckGo query: '%s' (max %d)", search_query, num_results)

    results = []
    try:
        def fetch_ddg():
            with DDGS() as ddgs:
                max_fetch = max(num_results * 3, num_results)
                max_fetch = min(max_fetch, 80)
                return list(ddgs.text(search_query, max_results=max_fetch))

        raw_results = await run_sync_in_thread(fetch_ddg)

        seen_urls = set()
        ranked: list = []
        for r in raw_results:
            url = (r.get("href") or "").strip()
            canonical = _canonicalize_url(url)
            if not canonical or canonical in seen_urls or _looks_noisy_url(url):
                continue
            seen_urls.add(canonical)

            title = (r.get("title") or "").lower()
            body = (r.get("body") or "").lower()
            blob = f"{title} {body} {url.lower()}"
            if not _has_query_signal(query=query, blob=blob):
                continue

            metadata = infer_source_metadata(
                url=url,
                title=(r.get("title") or ""),
                body=(r.get("body") or ""),
            )
            if not _source_allowed(metadata["source_type"], source_policy):
                continue

            score = _score_result(
                r,
                query=query,
                location=location,
                data_fields=data_fields,
                source_type=metadata["source_type"],
            )
            score += metadata["source_trust_score"] * 0.1
            
            # Semantic Steering (Phase 20)
            # Discovery adapts to the current state of the semantic field.
            from app.semantic_world_state import get_world_state
            ws = get_world_state()
            field_pressure = ws.metrics.field_pressure
            global_entropy = ws.metrics.global_entropy
            
            # Causal Steering:
            # 1. High entropy (disorder) rewards domain novelty (Exploration)
            if global_entropy > 0.7:
                # Roughly check if domain is novel (not in top results yet)
                domain = _extract_domain(url)
                if domain not in [r[2].get("source_domain") for r in ranked[:5]]:
                    score += 0.2
            
            # 2. High pressure (stress) rewards high-trust markers (Stabilization)
            if field_pressure > 0.6:
                if metadata["source_type"] == "official":
                    score += 0.15
            
            if score <= 0:
                continue
            ranked.append((score, r, metadata, canonical))

        ranked.sort(key=lambda x: x[0], reverse=True)

        per_domain_counts: dict[str, int] = defaultdict(int)
        domain_limit = max(1, int(max_per_domain or 4))

        for score, r, metadata, canonical in ranked:
            url = r.get("href")
            reason = (r.get("body") or "")[:170]

            domain_name = metadata["source_domain"] or _extract_domain(url)
            if per_domain_counts[domain_name] >= domain_limit:
                continue
            per_domain_counts[domain_name] += 1

            source_type = metadata["source_type"]
            trust = metadata["source_trust_score"]

            results.append({
                "url": url,
                "canonical_url": canonical,
                "title": r.get("title", "Found Object"),
                "reason": (reason + "...") if reason else "Likely relevant search result",
                "source_domain": domain_name,
                "source_type": source_type,
                "source_trust_score": trust,
                "relevance_score": score,
                "expected_records": 10 if source_type == "directory" or any(h in (r.get("title", "").lower() + " " + r.get("body", "").lower()) for h in LISTING_HINTS) else 1,
            })

            if len(results) >= num_results:
                break

        logging.info("Found %d real URLs.", len(results))
        return results
    except Exception as e:
        logging.exception("Discovered error: %s", e)
        return []


async def smart_query_builder(topic: str, data_fields: list[str]) -> str:
    """
    Deterministically build an optimized query from topic and desired fields.
    """
    return _build_search_query(
        query=topic,
        location="",
        domain="",
        data_fields=data_fields,
        origin_location="",
        max_distance_km=None,
    )
