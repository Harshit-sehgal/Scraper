"""
Scraper Diagnostics — Deep introspection for extraction analysis.

Provides detailed breakdown of what happened during a scrape:
- Fetch metadata (latency, method, headers)
- DOM characteristics (size, complexity, anti-bot signals)
- Selector performance (which succeeded, which failed)
- Memory hits/misses
- Quality scoring breakdown per record
"""

from __future__ import annotations

import time
import logging


from app.models import SchemaField
from app.html_utils import fetch_page_content
from app.scrape_telemetry import detect_anti_bot, estimate_dom_nodes
from app.selector_memory import get_selector_memory
from app.extraction_orchestrator import orchestrate_extraction
from app.data_utils import process_raw_records

logger = logging.getLogger(__name__)


class ScraperDiagnosticReport:
    def __init__(self, url: str):
        self.url = url
        self.start_time = time.time()
        self.fetch_ms: float = 0
        self.fetch_method: str = ""
        self.dom_nodes: int = 0
        self.anti_bot_score: float = 0
        self.extraction_method: str = ""
        self.selector_success: bool = False
        self.memory_hit: bool = False
        self.raw_records_count: int = 0
        self.final_records_count: int = 0
        self.record_samples: list[dict] = []
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "latency_ms": round((time.time() - self.start_time) * 1000, 2),
            "fetch": {
                "ms": round(self.fetch_ms, 2),
                "method": self.fetch_method
            },
            "dom": {
                "nodes": self.dom_nodes,
                "anti_bot": round(self.anti_bot_score, 3)
            },
            "extraction": {
                "method": self.extraction_method,
                "selector_success": self.selector_success,
                "memory_hit": self.memory_hit
            },
            "results": {
                "raw_count": self.raw_records_count,
                "final_count": self.final_records_count,
                "samples": self.record_samples[:3]
            },
            "errors": self.errors
        }


async def run_diagnostics(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float = 0.3
) -> ScraperDiagnosticReport:
    """Run a deep diagnostic scrape for a URL."""
    report = ScraperDiagnosticReport(url)
    
    try:
        # 1. Fetch
        f_start = time.time()
        html, render_delay, method, retries = await fetch_page_content(url)
        report.fetch_ms = (time.time() - f_start) * 1000
        report.fetch_method = method
        
        # 2. Page Analysis
        report.dom_nodes = estimate_dom_nodes(html)
        report.anti_bot_score = detect_anti_bot(html)
        
        # 3. Extraction
        memory = get_selector_memory()
        report.memory_hit = memory.get_selectors(url) is not None
        
        ext_result = await orchestrate_extraction(url, html, schema_fields, min_record_score)
        report.extraction_method = ext_result.method
        report.selector_success = ext_result.selector_success
        report.raw_records_count = len(ext_result.records)
        
        # 4. Processing
        final_results = process_raw_records(ext_result.records, schema_fields, min_record_score)
        report.final_records_count = len(final_results)
        report.record_samples = final_results
        
    except Exception as e:
        logger.exception("Diagnostics failed for %s", url)
        report.errors.append(str(e))
        
    return report
