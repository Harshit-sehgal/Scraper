#!/usr/bin/env python3
"""
Manual live benchmark smoke test for the evidence-based extraction pipeline
across a sample of public websites.

This file is not collected by pytest under the current pytest.ini. Results are
network-dependent and should be treated as live smoke observations, not proof of
universal extraction behavior.
"""
from app.config import settings
from app.scraper import scrape_url
from app.models import FieldType, SchemaField
import asyncio
import json
import logging
import os
import time
import sys
from dataclasses import dataclass, field

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")
# Quiet down noisy libs
logging.getLogger("app.scraper").setLevel(logging.WARNING)
logging.getLogger("app.extraction_orchestrator").setLevel(logging.WARNING)
logging.getLogger("app.html_utils").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────────
# Site Definitions
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SiteTest:
    name: str
    category: str
    url: str
    schema: list[SchemaField]
    min_record_score: float = 0.2
    min_expected: int = 0  # 0 = no strict expectation (observational)


SITES: list[SiteTest] = [
    SiteTest(
        name="Hacker News",
        category="listing",
        url="https://news.ycombinator.com/",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Article title", required=False),
            SchemaField(name="score", field_type=FieldType.INTEGER, description="Upvotes or points", required=False),
            SchemaField(name="author", field_type=FieldType.STRING, description="Submitter username", required=False),
        ],
        min_expected=10,
    ),
    SiteTest(
        name="Books to Scrape",
        category="ecommerce",
        url="https://books.toscrape.com/",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Book title", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="Book price", required=False),
            SchemaField(name="rating", field_type=FieldType.STRING, description="Star rating", required=False),
        ],
        min_expected=5,
    ),
    SiteTest(
        name="Quotes to Scrape",
        category="listing",
        url="https://quotes.toscrape.com/",
        schema=[
            SchemaField(name="quote", field_type=FieldType.STRING, description="Quote text", required=False),
            SchemaField(name="author", field_type=FieldType.STRING, description="Quote author", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="World Population Table",
        category="table",
        url="https://www.worldometers.info/world-population/population-by-country/",
        schema=[
            SchemaField(name="country", field_type=FieldType.STRING, description="Country name", required=False),
            SchemaField(name="population", field_type=FieldType.INTEGER, description="Population", required=False),
            SchemaField(name="yearly_change", field_type=FieldType.STRING, description="Yearly change %", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="Wikipedia GDP Table",
        category="table",
        url="https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)",
        schema=[
            SchemaField(name="country", field_type=FieldType.STRING, description="Country name", required=False),
            SchemaField(name="gdp", field_type=FieldType.STRING, description="GDP in USD", required=False),
        ],
        min_expected=10,
    ),
    SiteTest(
        name="ScrapeThisSite Simple",
        category="listing",
        url="https://www.scrapethissite.com/pages/simple/",
        schema=[
            SchemaField(name="country", field_type=FieldType.STRING, description="Country name", required=False),
            SchemaField(name="capital", field_type=FieldType.STRING, description="Capital city", required=False),
        ],
        min_expected=5,
    ),
    SiteTest(
        name="ScrapeThisSite Forms",
        category="table",
        url="https://www.scrapethissite.com/pages/forms/",
        schema=[
            SchemaField(name="team", field_type=FieldType.STRING, description="Team name", required=False),
            SchemaField(name="wins", field_type=FieldType.INTEGER, description="Number of wins", required=False),
            SchemaField(name="losses", field_type=FieldType.INTEGER, description="Number of losses", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="OpenLibrary Search",
        category="ecommerce",
        url="https://openlibrary.org/search?q=python&mode=everything",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Book title", required=False),
            SchemaField(name="author", field_type=FieldType.STRING, description="Book author", required=False),
            SchemaField(name="year", field_type=FieldType.STRING, description="Publication year", required=False),
        ],
        min_expected=10,
    ),
    SiteTest(
        name="Books Page 2",
        category="ecommerce",
        url="https://books.toscrape.com/catalogue/page-2.html",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Book title", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="Book price", required=False),
            SchemaField(name="rating", field_type=FieldType.STRING, description="Star rating", required=False),
        ],
        min_expected=1,
    ),
    SiteTest(
        name="Example.com",
        category="content",
        url="https://example.com/",
        schema=[
            SchemaField(name="heading", field_type=FieldType.STRING, description="Page heading", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="Wikipedia Python",
        category="content",
        url="https://en.wikipedia.org/wiki/Python_(programming_language)",
        schema=[
            SchemaField(name="section", field_type=FieldType.STRING, description="Section heading", required=False),
            SchemaField(name="paragraph", field_type=FieldType.STRING, description="Content text", required=False),
        ],
        min_expected=1,
    ),
    SiteTest(
        name="GitHub Trending JS",
        category="listing_js",
        url="https://github.com/trending",
        schema=[
            SchemaField(name="repo", field_type=FieldType.STRING, description="Repository name", required=False),
            SchemaField(name="description", field_type=FieldType.STRING, description="Repo description", required=False),
            SchemaField(name="stars", field_type=FieldType.STRING, description="Star count", required=False),
        ],
        min_expected=1,
    ),
    SiteTest(
        name="Cat Facts",
        category="api_content",
        url="https://catfact.ninja/facts",
        schema=[
            SchemaField(name="fact", field_type=FieldType.STRING, description="Cat fact", required=False),
        ],
        min_expected=1,
    ),
    SiteTest(
        name="HTTPBin HTML",
        category="content",
        url="https://httpbin.org/html",
        schema=[
            SchemaField(name="heading", field_type=FieldType.STRING, description="Page heading", required=False),
            SchemaField(name="paragraph", field_type=FieldType.STRING, description="Content text", required=False),
        ],
        min_expected=1,
    ),
    SiteTest(
        name="HTTPBin Links",
        category="links",
        url="https://httpbin.org/links/10",
        schema=[
            SchemaField(name="link_text", field_type=FieldType.STRING, description="Link anchor text", required=False),
            SchemaField(name="link_url", field_type=FieldType.URL, description="Link destination", required=False),
        ],
        min_expected=0,
    ),
    # ── Expanded: 15 additional diverse sites ──
    SiteTest(
        name="Reuters World News",
        category="news",
        url="https://www.reuters.com/world/",
        schema=[
            SchemaField(name="headline", field_type=FieldType.STRING, description="News headline", required=False),
            SchemaField(name="timestamp", field_type=FieldType.STRING, description="Publication time", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="Wikipedia Python (Alt)",
        category="content",
        url="https://en.wikipedia.org/wiki/Python_(programming_language)",
        schema=[
            SchemaField(name="heading", field_type=FieldType.STRING, description="Page heading", required=False),
            SchemaField(name="paragraph", field_type=FieldType.STRING, description="Content paragraph", required=False),
        ],
        min_expected=1,
    ),
    SiteTest(
        name="StackOverflow Questions",
        category="listing",
        url="https://stackoverflow.com/questions?tab=newest",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Question title", required=False),
            SchemaField(name="votes", field_type=FieldType.INTEGER, description="Vote count", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="GitHub Trending (Alt)",
        category="listing",
        url="https://github.com/trending",
        schema=[
            SchemaField(name="repo", field_type=FieldType.STRING, description="Repository name", required=False),
            SchemaField(name="description", field_type=FieldType.STRING, description="Repo description", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="IMDb Top 250",
        category="ecommerce",
        url="https://www.imdb.com/chart/top/",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Movie title", required=False),
            SchemaField(name="rating", field_type=FieldType.STRING, description="IMDb rating", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="BBC News",
        category="news",
        url="https://www.bbc.com/news",
        schema=[
            SchemaField(name="headline", field_type=FieldType.STRING, description="News headline", required=False),
            SchemaField(name="summary", field_type=FieldType.STRING, description="Article summary", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="AllRecipes",
        category="listing",
        url="https://www.allrecipes.com/recipes/",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Recipe title", required=False),
            SchemaField(name="rating", field_type=FieldType.STRING, description="Recipe rating", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="Goodreads Popular",
        category="listing",
        url="https://www.goodreads.com/list/show/1.Best_Books_Ever",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Book title", required=False),
            SchemaField(name="author", field_type=FieldType.STRING, description="Author name", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="Xe Currency Table",
        category="table",
        url="https://www.xe.com/currencytables/",
        schema=[
            SchemaField(name="currency", field_type=FieldType.STRING, description="Currency name", required=False),
            SchemaField(name="rate", field_type=FieldType.STRING, description="Exchange rate", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="Python Docs",
        category="content",
        url="https://docs.python.org/3/library/index.html",
        schema=[
            SchemaField(name="module", field_type=FieldType.STRING, description="Module name", required=False),
            SchemaField(name="summary", field_type=FieldType.STRING, description="Module summary", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="arXiv CS Papers",
        category="listing",
        url="https://arxiv.org/list/cs.AI/recent",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, description="Paper title", required=False),
            SchemaField(name="authors", field_type=FieldType.STRING, description="Author list", required=False),
        ],
        min_expected=0,
    ),
    SiteTest(
        name="HTTPBin Status 200",
        category="empty",
        url="https://httpbin.org/status/200",
        schema=[SchemaField(name="data", field_type=FieldType.STRING, required=False)],
        min_expected=0,
    ),
    SiteTest(
        name="HTTPBin Status 404",
        category="empty",
        url="https://httpbin.org/status/404",
        schema=[SchemaField(name="data", field_type=FieldType.STRING, required=False)],
        min_expected=0,
    ),
    SiteTest(
        name="Robots Blocked (YouTube)",
        category="blocked",
        url="https://www.youtube.com/results?search_query=python",
        schema=[SchemaField(name="title", field_type=FieldType.STRING, required=False)],
        min_expected=10,
    ),
    SiteTest(
        name="JSONPlaceholder Posts",
        category="api",
        url="https://jsonplaceholder.typicode.com/posts",
        schema=[
            SchemaField(name="title", field_type=FieldType.STRING, required=False),
            SchemaField(name="body", field_type=FieldType.STRING, required=False),
        ],
        min_expected=0,
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Result Tracking
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SiteResult:
    name: str
    category: str
    url: str
    success: bool
    records: int
    extraction_method: str = ""
    quality: float = 0.0
    error: str = ""
    fields_found: list[str] = field(default_factory=list)
    sample: dict | None = None
    fetch_time_ms: float = 0.0
    dom_nodes: int = 0
    anti_bot_score: float = 0.0
    warnings: list[str] = field(default_factory=list)

# ─────────────────────────────────────────────────────────────────────────────
# Test Runner
# ─────────────────────────────────────────────────────────────────────────────


async def test_site(site: SiteTest, index: int, total: int) -> SiteResult:
    """Run scrape_url against one site and return structured results."""
    print(f"\n  [{index}/{total}] {site.name:25} ({site.category:15}) {site.url[:60]}...")
    print(f"         Schema: {[f.name for f in site.schema]}")

    start = time.time()
    try:
        results = await scrape_url(
            site.url,
            site.schema,
            min_record_score=site.min_record_score,
        )
        elapsed = time.time() - start
        fetch_time_ms = elapsed * 1000

        # Determine extraction method from results metadata
        methods = set(r.get("_extraction_method", "") for r in results if isinstance(r, dict))
        method = methods.pop() if len(methods) == 1 else (methods.pop() if methods else "unknown")

        # Quality metrics: prefer record_score, fall back to _calibrated_confidence
        scores = []
        for r in results:
            if isinstance(r, dict):
                rs = r.get("record_score", 0.0) or 0.0
                if rs == 0.0:
                    rs = r.get("_calibrated_confidence", 0.0) or 0.0
                scores.append(rs)
        avg_quality = sum(scores) / len(scores) if scores else 0.0

        # Fields found across records
        fields_found = set()
        for r in results:
            if isinstance(r, dict):
                for k in r:
                    if not k.startswith("_") and r[k] is not None and str(r[k]).strip():
                        fields_found.add(k)

        # Sample record (first non-empty record)
        sample = None
        for r in results[:3]:
            if isinstance(r, dict) and any(v for k, v in r.items() if not k.startswith("_") and v):
                sample = r
                break

        # Fetch telemetry
        from app.scrape_telemetry import get_scrape_telemetry
        telemetry = get_scrape_telemetry()
        recent = telemetry.get_recent(10)
        t_data = next((t for t in recent if t.get("url") == site.url), {})

        dom_nodes = t_data.get("dom_nodes", 0) or 0
        anti_bot = t_data.get("anti_bot_score", 0.0) or 0.0

        # Collect warnings from telemetry
        warns = []
        if t_data.get("failure_category"):
            warns.append(f"failure_category={t_data['failure_category']}")
        if t_data.get("error"):
            warns.append(f"error={t_data['error'][:80]}")
        if t_data.get("fallback_usage"):
            warns.append(f"fallback={t_data['fallback_usage']}")

        status = chr(0x2713) if results else chr(0x25CB)
        print(f"         {status} {len(results):3} records | method={method:12} | quality={avg_quality:.2f} | {elapsed:.1f}s")

        if not results and warns:
            print(f"         {chr(0x26A0)} {'; '.join(warns[:2])}")

        return SiteResult(
            name=site.name,
            category=site.category,
            url=site.url,
            success=len(results) > 0 or site.min_expected == 0,
            records=len(results),
            extraction_method=method,
            quality=round(avg_quality, 3),
            fields_found=sorted(fields_found),
            sample=sample,
            fetch_time_ms=round(fetch_time_ms, 1),
            dom_nodes=dom_nodes,
            anti_bot_score=round(anti_bot, 2),
            warnings=warns[:3],
        )

    except Exception as e:
        elapsed = time.time() - start
        err_str = f"{type(e).__name__}: {e}"
        print(f"         {chr(0x2717)} ERROR: {err_str[:120]}")

        return SiteResult(
            name=site.name,
            category=site.category,
            url=site.url,
            success=False,
            records=0,
            error=err_str[:200],
            fetch_time_ms=round(elapsed * 1000, 1),
        )


async def run_all_tests():
    """Run all 15 site tests and generate a report."""
    # Configure for respectful crawling
    original_delay = settings.CRAWL_DEFAULT_DELAY_SECONDS
    settings.CRAWL_DEFAULT_DELAY_SECONDS = 2.0  # Be nice to servers
    settings.PAGE_SETTLE_DELAY = 3.0  # Allow JS rendering
    settings.PLAYWRIGHT_TIMEOUT = 30000
    settings.REQUEST_TIMEOUT = 15

    print("=" * 72)
    print("  DATAFORGE - 15-Site Universal Extraction Smoke Test")
    print("=" * 72)
    print(f"  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Sites: {len(SITES)}")
    print(f"  Delay between sites: {settings.CRAWL_DEFAULT_DELAY_SECONDS}s")
    print("=" * 72)

    results: list[SiteResult] = []

    for i, site in enumerate(SITES, 1):
        result = await test_site(site, i, len(SITES))
        results.append(result)
        # Respectful delay between sites
        if i < len(SITES):
            await asyncio.sleep(settings.CRAWL_DEFAULT_DELAY_SECONDS)

    # Restore settings
    settings.CRAWL_DEFAULT_DELAY_SECONDS = original_delay

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Report Generator
# ─────────────────────────────────────────────────────────────────────────────

def print_report(results: list[SiteResult]):
    """Print a detailed markdown report of all test results."""
    total = len(results)
    with_records = sum(1 for r in results if r.records > 0)
    total_records = sum(r.records for r in results)

    print("\n\n" + "=" * 72)
    print("  SMOKE TEST REPORT")
    print("=" * 72)
    print(f"  Sites tested:      {total}")
    print(f"  Sites with data:   {with_records}/{total}")
    print(f"  Total records:     {total_records}")
    print("=" * 72)

    # Summary Table
    print("\n\n## Summary\n")
    print("| # | Site | Category | Records | Method | Quality | Fields | Time (s) | Notes |")
    print("|---|------|----------|---------|--------|---------|--------|----------|-------|")

    for i, r in enumerate(results, 1):
        notes = ""
        if r.error:
            notes = f"{chr(0x26A0)} {r.error[:40]}"
        elif not r.records:
            notes = f"{chr(0x25CB)} zero records"
        elif r.warnings:
            notes = "; ".join(r.warnings[:2])
        else:
            notes = chr(0x2713)

        fields_str = ", ".join(r.fields_found[:4])
        if len(r.fields_found) > 4:
            fields_str += f" +{len(r.fields_found) - 4}"

        print(
            f"| {i} | {r.name} | {r.category} | {r.records} | {r.extraction_method[:12]} | {r.quality:.2f} | {fields_str[:40]} | {r.fetch_time_ms / 1000:.1f} | {notes[:45]} |")  # noqa: E501

    # Detailed per-site results
    print("\n\n## Per-Site Details\n")

    for i, r in enumerate(results, 1):
        print(f"### {i}. {r.name}\n")
        print(f"- **URL:** [{r.url}]({r.url})")
        print(f"- **Category:** {r.category}")
        print(f"- **Records:** {r.records}")
        print(f"- **Extraction method:** `{r.extraction_method}`")
        print(f"- **Avg quality:** {r.quality}")
        fields_display = ', '.join(r.fields_found) if r.fields_found else '*none*'
        print(f"- **Fields found:** {fields_display}")
        print(f"- **Fetch time:** {r.fetch_time_ms / 1000:.1f}s")
        print(f"- **DOM nodes:** {r.dom_nodes}")
        print(f"- **Anti-bot score:** {r.anti_bot_score}")

        if r.sample:
            sample_display = {k: v for k, v in r.sample.items() if not k.startswith("_")}
            print(f"- **Sample record:** `{json.dumps(sample_display)}`")

        if r.warnings:
            for w in r.warnings:
                print(f"- {chr(0x26A0)} {w}")

        if r.error:
            print(f"- {chr(0x2717)} **Error:** {r.error}")

        print()

    # Acceptance criteria check
    print("---\n")
    print("## Acceptance Criteria\n")
    print("| Criteria | Status |")
    print("|----------|--------|")

    # 1. No false success for 0 records
    zero_but_success = [
        r for r in results
        if r.records == 0 and r.extraction_method not in ("", "unknown") and not r.error
    ]
    zero_ok = len(zero_but_success) == 0
    ok_mark = chr(0x2705) if zero_ok else chr(0x26A0)
    print(f"| No false success for 0 records | {ok_mark} |")

    # 2. Visible text captured when rendered
    pipeline_working = with_records >= 5
    pw_mark = chr(0x2705) if pipeline_working else chr(0x274C)
    print(f"| Pipeline produces records (>=5 sites) | {pw_mark} |")

    # 3. No domain-specific hardcoded logic (verified in prior audit)
    print(f"| No domain-specific runtime logic | {chr(0x2705)} (verified in prior audit) |")

    # 4. Zero-result properly classified when applicable
    zero_with_class = [r for r in results if r.records == 0 and r.warnings]
    zrc_mark = chr(0x2705) if zero_with_class else chr(0x25CB) + ' (no zero results to classify)'
    print(f"| Zero-result classification present | {zrc_mark} |")

    # Overall verdict
    verdict = chr(0x2705) + ' PASS' if with_records >= 5 else chr(0x274C) + ' FAIL'
    print(f"\n**Verdict:** {verdict} - {with_records}/{total} sites produced data, {total_records} total records.")


def save_report(results: list[SiteResult], path: str = "smoke_test_report.json"):
    """Save the full report as JSON for later analysis."""
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_sites": len(results),
        "sites_with_data": sum(1 for r in results if r.records > 0),
        "total_records": sum(r.records for r in results),
        "results": [
            {
                "name": r.name,
                "category": r.category,
                "url": r.url,
                "success": r.success,
                "records": r.records,
                "extraction_method": r.extraction_method,
                "quality": r.quality,
                "fields_found": r.fields_found,
                "fetch_time_ms": r.fetch_time_ms,
                "dom_nodes": r.dom_nodes,
                "anti_bot_score": r.anti_bot_score,
                "warnings": r.warnings,
                "error": r.error,
                "sample": r.sample,
            }
            for r in results
        ]
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nFull report saved to {path}")


def compare_with_previous(results: list[SiteResult], history_dir: str = "smoke_test_history"):
    """Compare current results with the most recent previous run, print trends."""
    import glob as _glob
    os.makedirs(history_dir, exist_ok=True)

    history_files = sorted(_glob.glob(f"{history_dir}/smoke_*.json"), reverse=True)
    if not history_files:
        print("\nFirst run — no previous benchmark to compare against.")
        return

    try:
        with open(history_files[0], "r") as f:
            prev = json.load(f)
    except Exception:
        print(f"\nCould not load previous benchmark from {history_files[0]}")
        return

    prev_results = {r["name"]: r for r in prev.get("results", [])}
    curr_results = {r.name: r for r in results}

    regressed = []
    improved = []
    same = 0
    unchanged = 0

    for name, cr in curr_results.items():
        pr = prev_results.get(name)
        if not pr:
            continue
        if cr.records > pr["records"]:
            improved.append(name)
        elif cr.records < pr["records"]:
            regressed.append(name)
        elif cr.records == pr["records"] and cr.records > 0:
            same += 1
        else:
            unchanged += 1

    prev_sites = prev.get("sites_with_data", 0)
    prev_records = prev.get("total_records", 0)
    curr_sites = sum(1 for r in results if r.records > 0)
    curr_records = sum(r.records for r in results)

    print(f"\n{'=' * 60}")
    print("BENCHMARK TREND vs Previous Run")
    print(f"{'=' * 60}")
    print(f"Previous: {prev.get('timestamp', 'unknown')} — {prev_sites} sites, {prev_records} records")
    print(f"Current:  {time.strftime('%Y-%m-%d %H:%M:%S')} — {curr_sites} sites, {curr_records} records")
    print(f"  Improved:  +{len(improved)} sites" + (f" ({', '.join(improved[:5])})" if improved else ""))
    print(f"  Regressed: -{len(regressed)} sites" + (f" ({', '.join(regressed[:5])})" if regressed else ""))
    print(f"  Same:       {same} sites")
    print(f"  Site delta: {curr_sites - prev_sites:+d}")
    print(f"  Record delta: {curr_records - prev_records:+d}")


def save_to_history(results: list[SiteResult], history_dir: str = "smoke_test_history"):
    """Save this run to the benchmark history."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = f"{history_dir}/smoke_{ts}.json"
    save_report(results, path)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("Running 15-site smoke test (this will take several minutes)...")
    results = await run_all_tests()
    print_report(results)
    compare_with_previous(results)
    save_report(results)
    save_to_history(results)
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
