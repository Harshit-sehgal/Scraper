"""
Scrape Telemetry — per-URL observability for the scraping pipeline.

Tracks:
  - Fetch timing (Playwright vs httpx)
  - DOM node count
  - Selector quality & success rate
  - Fallback triggers
  - Records extracted vs discarded
  - Anti-bot detection signals

Emits structured telemetry events that flow into the semantic world state's
observability layer for dashboard visualisation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScrapeTelemetry:
    """Telemetry snapshot for a single URL scrape."""

    url: str = ""
    fetch_method: str = ""                 # "playwright" | "httpx"
    fetch_ms: float = 0.0                  # Total fetch time in ms
    dom_nodes: int = 0                     # Approximate DOM node count
    selector_success: bool = False         # Whether LLM selectors produced results
    selector_count: int = 0                # Number of field selectors generated
    fallback_triggered: bool = False       # Whether regex fallback was used
    records_extracted: int = 0             # Raw records from selectors
    records_after_scoring: int = 0         # After quality score threshold
    records_after_dedup: int = 0           # After dedup
    records_final: int = 0                 # After pipeline
    profile_match: bool = False            # Whether a selector profile was found
    profile_records: int = 0               # Records from profile extraction
    anti_bot_score: float = 0.0            # 0.0 = none, 1.0 = certain anti-bot detected
    retry_count: int = 0                   # Number of fetch retries
    fallback_usage: str = "none"           # "none" | "regex" | "httpx"
    
    # Granular Metrics (Grounding abstractions)
    selector_hit_rate: float = 0.0          # Percentage of fields successfully matched
    dom_mutation_rate: float = 0.0         # Rough proxy for dynamic behavior/instability
    token_density: float = 0.0             # Text characters per DOM node
    js_render_delay_ms: float = 0.0        # Time spent waiting for JS/DOM quiescence
    confidence_map: dict = field(default_factory=dict) # Per-field extraction confidence scores
    
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class ScrapeTelemetryCollector:
    """Collects and emits scrape telemetry for observability."""

    def __init__(self) -> None:
        self._history: list[ScrapeTelemetry] = []

    def record(self, url: str, **kwargs) -> ScrapeTelemetry:
        """Record a scrape telemetry event."""
        telemetry = ScrapeTelemetry(url=url, **kwargs)
        self._history.append(telemetry)

        # Emit to semantic world state observability if available
        try:
            from app.semantic_world_state import get_world_state
            ws = get_world_state()
            ws.record_degradation(
                subsystem="scraper",
                severity="info",
                cause=f"Scraped {url}: {telemetry.records_final} records in {telemetry.fetch_ms:.0f}ms"
                + (f" (profile)" if telemetry.profile_match else "")
                + (f" (fallback)" if telemetry.fallback_triggered else ""),
            )
            ws.emit_telemetry("scrape", {
                "url": url,
                "records": telemetry.records_final,
                "fetch_ms": telemetry.fetch_ms,
                "render_delay_ms": telemetry.js_render_delay_ms,
                "selector_hit_rate": telemetry.selector_hit_rate,
                "selector_ok": telemetry.selector_success,
                "fallback": telemetry.fallback_triggered,
                "fallback_type": telemetry.fallback_usage,
                "profile": telemetry.profile_match,
                "anti_bot": telemetry.anti_bot_score,
                "retries": telemetry.retry_count,
            })
        except Exception:
            pass

        return telemetry

    def get_recent(self, n: int = 20) -> list[dict]:
        """Get the N most recent telemetry snapshots."""
        return [t.to_dict() for t in self._history[-n:]]

    def clear(self) -> None:
        self._history.clear()


# Module-level singleton
_collector: ScrapeTelemetryCollector | None = None


def get_scrape_telemetry() -> ScrapeTelemetryCollector:
    global _collector
    if _collector is None:
        _collector = ScrapeTelemetryCollector()
    return _collector


# ─── Anti-bot Detection Helpers ──────────────────────────────────────────

ANTI_BOT_SIGNALS = {
    "challenge-platform": 0.9,
    "cf-browser-verification": 0.9,
    "cf-turnstile": 0.9,
    "g-recaptcha": 0.9,
    "h-captcha": 0.9,
    "blocked": 0.7,
    "access denied": 0.7,
    "please verify": 0.6,
    "security check": 0.6,
    "sorry, you have been blocked": 0.95,
    "enable javascript": 0.5,
    "javascript is required": 0.5,
    "ddos-guard": 0.8,
    "perimeterx": 0.8,
    "akamai": 0.7,
    "cloudflare": 0.6,
}


def detect_anti_bot(html: str) -> float:
    """Score how likely this page is an anti-bot / challenge page.

    Returns 0.0 (no anti-bot) to 1.0 (definitely blocked).
    """
    if not html:
        return 0.0
    lower = html.lower()
    max_score = 0.0
    for signal, score in ANTI_BOT_SIGNALS.items():
        if signal in lower:
            max_score = max(max_score, score)
    return max_score


def estimate_dom_nodes(html: str) -> int:
    """Quick approximate DOM node count from raw HTML."""
    if not html:
        return 0
    # Count opening tags as a rough proxy
    import re
    return len(re.findall(r"<[a-zA-Z][^>]*>", html))
