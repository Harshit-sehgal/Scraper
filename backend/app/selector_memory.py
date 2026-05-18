"""
Selector Memory — persistent learning for domain-specific extraction.

Remembers successful CSS selectors for domains to:
  1. Skip LLM discovery on subsequent scrapes (speed & cost)
  2. Track selector "survival" (how long a selector remains valid)
  3. Provide historical confidence for domain extraction
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)


class SelectorMemory:
    """Persistent memory of successful selectors per domain."""

    def __init__(self, storage_path: str = "backend/data/selector_memory.json"):
        self.path = Path(storage_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    self._memory = json.load(f)
            except Exception as e:
                logger.error("Failed to load selector memory: %s", e)
                self._memory = {}

    def _save(self):
        try:
            with open(self.path, "w") as f:
                json.dump(self._memory, f, indent=2)
        except Exception as e:
            logger.error("Failed to save selector memory: %s", e)

    def get_selectors(self, url: str) -> Optional[dict]:
        """Get remembered selectors for a domain."""
        domain = self._extract_domain(url)
        if not domain:
            return None

        entry = self._memory.get(domain)
        if not entry:
            return None

        # Check if it has failed too many times recently
        if entry.get("failure_count", 0) > settings.SELECTOR_MEMORY_MAX_FAILURES:
            logger.debug("Selector memory for %s is suspended (failures: %d)", 
                         domain, entry["failure_count"])
            return None

        return entry.get("selectors")

    def record_success(self, url: str, selectors: dict):
        """Record a successful extraction with these selectors."""
        domain = self._extract_domain(url)
        if not domain:
            return

        now = time.time()
        entry = self._memory.get(domain, {
            "selectors": selectors,
            "success_count": 0,
            "failure_count": 0,
            "first_seen": now,
            "last_success": now,
        })

        # Update if selectors changed or it's a new entry
        if entry["selectors"] != selectors:
            entry["selectors"] = selectors
            entry["failure_count"] = 0  # Reset failures on change
            entry["last_updated"] = now

        entry["success_count"] += 1
        entry["last_success"] = now
        self._memory[domain] = entry
        self._save()

    def record_failure(self, url: str):
        """Record a failure of remembered selectors for a domain."""
        domain = self._extract_domain(url)
        if not domain:
            return

        entry = self._memory.get(domain)
        if not entry:
            return

        entry["failure_count"] = entry.get("failure_count", 0) + 1
        entry["last_failure"] = time.time()
        self._memory[domain] = entry
        self._save()

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or None
        except Exception:
            return None


# Global singleton
_memory: SelectorMemory | None = None

def get_selector_memory() -> SelectorMemory:
    global _memory
    if _memory is None:
        _memory = SelectorMemory()
    return _memory
