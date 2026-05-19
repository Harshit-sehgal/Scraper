"""
Crawl Policy Engine — operational governance for the scraper.

Provides:
  - Per-domain concurrency budgets
  - Global concurrency cap
  - Request pacing (min delay between requests to same domain)
  - Retry ceilings per domain with cooldown
  - Best-effort robots.txt awareness
  - Domain reputation tracking

Usage:
    policy = get_crawl_policy()
    await policy.check_domain("example.com")
    # ... fetch ...
    policy.record_result("example.com", success=True)
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Domain State ───────────────────────────────────────────────────────

@dataclass
class DomainState:
    """Tracks operational state for a single domain."""
    domain: str
    active_fetches: int = 0
    consecutive_failures: int = 0
    total_fetches: int = 0
    last_fetch_time: float = 0.0
    cooldown_until: float = 0.0
    robots_disallowed: set[str] = field(default_factory=set)
    robots_checked: bool = False
    crawl_delay: float = 0.0  # robots.txt Crawl-Delay if specified


class CrawlPolicyEngine:
    """Governs domain-level crawling behaviour."""

    def __init__(self) -> None:
        self._domains: dict[str, DomainState] = defaultdict(lambda: DomainState(domain=""))
        self._global_active_fetches = 0
        self._max_concurrency = settings.CRAWL_PER_DOMAIN_CONCURRENCY
        self._max_global_concurrency = settings.CRAWL_MAX_TOTAL_CONCURRENCY
        self._default_delay = settings.CRAWL_DEFAULT_DELAY_SECONDS
        self._max_retries = settings.CRAWL_MAX_RETRIES_PER_DOMAIN
        self._cooldown_seconds = settings.CRAWL_COOLDOWN_SECONDS
        self._respect_robots = settings.CRAWL_RESPECT_ROBOTS
        self._max_pages_per_domain = settings.CRAWL_MAX_PAGES_PER_DOMAIN

    # ─── Public API ────────────────────────────────────────────────────

    async def check_domain(self, url: str) -> Optional[str]:
        """Check whether a URL can be fetched under crawl policy.

        Returns:
            None if allowed, or an error message string if blocked.
        """
        domain = self._extract_domain(url)
        if not domain:
            return "Invalid URL"

        # Global concurrency check
        if self._global_active_fetches >= self._max_global_concurrency:
            return f"Global concurrency limit reached ({self._max_global_concurrency})"

        state = self._get_state(domain)

        # Cooldown check
        if time.time() < state.cooldown_until:
            remaining = int(state.cooldown_until - time.time())
            logger.info("Domain %s in cooldown for %ds (%d consecutive failures)",
                        domain, remaining, state.consecutive_failures)
            return f"Domain {domain} in cooldown ({remaining}s remaining)"

        # Page budget check
        if state.total_fetches >= self._max_pages_per_domain:
            return f"Domain {domain} reached page budget ({self._max_pages_per_domain})"

        # Concurrency budget check
        if state.active_fetches >= self._max_concurrency:
            return f"Domain {domain} at max concurrency ({self._max_concurrency})"

        # Delay check
        elapsed = time.time() - state.last_fetch_time
        required_delay = max(state.crawl_delay, self._default_delay)
        if elapsed < required_delay:
            wait = required_delay - elapsed
            return f"Domain {domain} delay not met (wait {wait:.1f}s)"

        # robots.txt check (best-effort, cached)
        if self._respect_robots and not state.robots_checked:
            await self._check_robots_txt(domain)

        if self._respect_robots:
            path = self._extract_path(url)
            if self._is_path_disallowed(path, state.robots_disallowed):
                logger.info("robots.txt disallows %s on %s", path, domain)
                return f"robots.txt disallows {path} on {domain}"

        # All checks passed — increment active fetches
        state.active_fetches += 1
        self._global_active_fetches += 1
        return None

    def record_result(self, url: str, success: bool) -> None:
        """Record the outcome of a fetch for a domain."""
        domain = self._extract_domain(url)
        if not domain:
            return

        state = self._get_state(domain)
        state.active_fetches = max(0, state.active_fetches - 1)
        self._global_active_fetches = max(0, self._global_active_fetches - 1)
        state.last_fetch_time = time.time()
        state.total_fetches += 1

        if success:
            state.consecutive_failures = 0
        else:
            state.consecutive_failures += 1
            if state.consecutive_failures >= self._max_retries:
                state.cooldown_until = time.time() + self._cooldown_seconds
                logger.warning(
                    "Domain %s: %d consecutive failures, cooling down for %ds",
                    domain, state.consecutive_failures, self._cooldown_seconds,
                )

    def get_domain_state(self, domain: str) -> Optional[dict]:
        """Get the current state for a domain (for observability)."""
        state = self._domains.get(domain)
        if not state:
            return None
        return {
            "domain": state.domain,
            "active_fetches": state.active_fetches,
            "consecutive_failures": state.consecutive_failures,
            "total_fetches": state.total_fetches,
            "cooldown": max(0.0, state.cooldown_until - time.time()),
            "robots_checked": state.robots_checked,
        }

    def get_domain_health_score(self, domain: str) -> float:
        """Calculate a health score [0, 1] for a domain based on recent successes/failures."""
        state = self._domains.get(domain)
        if not state or state.total_fetches == 0:
            return 1.0
        
        # Linear penalty for consecutive failures
        failure_penalty = (state.consecutive_failures / self._max_retries) * 0.8
        
        # Simple success ratio component
        # Note: we don't track total successes explicitly, but we can infer it
        # for a better metric we might want to track windowed success rate
        
        score = 1.0 - failure_penalty
        if time.time() < state.cooldown_until:
            score *= 0.2 # Severely penalized if in cooldown
            
        return round(max(0.0, score), 2)

    def get_all_domain_states(self) -> dict[str, dict]:
        """Get states for all tracked domains."""
        states = {
            d: s
            for d in sorted(self._domains.keys())
            if (s := self.get_domain_state(d))
        }
        # Add global summary
        states["_global"] = {
            "active_fetches": self._global_active_fetches,
            "max_concurrency": self._max_global_concurrency,
            "tracked_domains": len(self._domains)
        }
        return states

    def reset_domain(self, url_or_domain: str) -> None:
        """Reset a domain's state (e.g. after manual override)."""
        domain = self._extract_domain(url_or_domain) or url_or_domain
        self._domains.pop(domain, None)
        logger.info("Crawl policy: reset state for domain %s", domain)

    # ─── Internal Helpers ──────────────────────────────────────────────

    def _get_state(self, domain: str) -> DomainState:
        if domain not in self._domains:
            self._domains[domain] = DomainState(domain=domain)
        return self._domains[domain]

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or None
        except Exception:
            return None

    @staticmethod
    def _extract_path(url: str) -> str:
        try:
            return urlparse(url).path or "/"
        except Exception:
            return "/"

    async def _check_robots_txt(self, domain: str) -> None:
        """Fetch and parse robots.txt for a domain (best-effort)."""
        state = self._get_state(domain)
        state.robots_checked = True

        try:
            import httpx
            url = f"https://{domain}/robots.txt"
            async with httpx.AsyncClient(
                timeout=settings.ROBOTS_TIMEOUT,
                headers={"User-Agent": settings.USER_AGENT},
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return

                text = resp.text
                current_agent = None
                disallowed_paths: set[str] = set()
                crawl_delay = 0.0

                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if line.lower().startswith("user-agent:"):
                        agent = line.split(":", 1)[1].strip().lower()
                        current_agent = agent if agent == "*" else None
                        continue

                    if current_agent != "*":
                        continue

                    if line.lower().startswith("disallow:"):
                        path = line.split(":", 1)[1].strip()
                        if path:
                            disallowed_paths.add(path)

                    if line.lower().startswith("crawl-delay:"):
                        try:
                            crawl_delay = float(line.split(":", 1)[1].strip())
                        except ValueError:
                            pass

                state.robots_disallowed = disallowed_paths
                state.crawl_delay = crawl_delay

                if disallowed_paths:
                    logger.debug("robots.txt for %s: %d disallowed paths, delay=%.1fs",
                                 domain, len(disallowed_paths), crawl_delay)

        except Exception as e:
            logger.debug("Failed to fetch robots.txt for %s: %s", domain, e)
            # Non-fatal — proceed without robots.txt constraints

    @staticmethod
    def _is_path_disallowed(path: str, disallowed: set[str]) -> bool:
        """Check if a path is disallowed by robots.txt rules."""
        if not disallowed:
            return False
        for pattern in disallowed:
            if pattern == "/":
                return True
            if pattern.endswith("*"):
                if path.startswith(pattern[:-1]):
                    return True
            elif path == pattern or path.startswith(pattern):
                return True
        return False


# ─── Singleton Accessor ─────────────────────────────────────────────────

_policy_engine: CrawlPolicyEngine | None = None


def get_crawl_policy() -> CrawlPolicyEngine:
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = CrawlPolicyEngine()
    return _policy_engine
