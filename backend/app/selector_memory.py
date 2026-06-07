"""Selector Memory — persistent learning for domain-specific extraction.

Remembers successful CSS selectors for domains to:
  1. Skip LLM discovery on subsequent scrapes (speed & cost)
  2. Track selector "survival" (how long a selector remains valid)
  3. Provide historical confidence for domain extraction
  4. Auto-cleanup selectors below confidence threshold (NEW)

Confidence Scoring:
  - Score = (successes / (successes + failures)) * age_factor * freshness_factor
  - Selectors below SELECTOR_CONFIDENCE_THRESHOLD (default 0.5) are auto-deleted
  - age_factor: decays selectors older than 14 days
  - freshness_factor: penalizes selectors not used in 7 days
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)

# Confidence scoring thresholds
# Minimum confidence to keep selector
DEFAULT_SELECTOR_CONFIDENCE_THRESHOLD = 0.5
SELECTOR_CLEANUP_CHECK_INTERVAL = 86400  # Run cleanup every 24 hours
SELECTOR_AGE_DECAY_THRESHOLD = 14 * 86400  # Start decaying after 14 days
SELECTOR_FRESHNESS_THRESHOLD = 7 * 86400  # Penalize if not used in 7 days


@dataclass
class SelectorConfidenceScore:
    """Confidence metrics for a selector."""

    raw_confidence: float  # success/(success+failure)
    age_factor: float  # Decay based on age
    freshness_factor: float  # Decay based on lack of recent use
    final_score: float  # Final weighted score
    reason: str  # Explanation of the score


class SelectorMemory:
    """Persistent memory of successful selectors per domain."""

    def __init__(self, storage_path: str | None = None) -> None:
        if storage_path is None:
            storage_path = str(Path(__file__).resolve().parent.parent / "data" / "selector_memory.json")
        self.path = Path(storage_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, dict] = {}
        self._last_cleanup: float = 0.0  # Track when we last cleaned up
        self._load()
        self._auto_cleanup()  # Clean up on initialization

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self._memory = json.load(f)
            except (OSError, json.JSONDecodeError):
                logger.exception("Failed to load selector memory")
                self._memory = {}

    def _save(self) -> None:
        try:
            with open(self.path, "w") as f:
                json.dump(self._memory, f, indent=2)
        except (OSError, TypeError):
            logger.exception("Failed to save selector memory")

    def _compute_confidence(self, entry: dict) -> SelectorConfidenceScore:
        """Compute confidence score for a selector entry.

        Formula:
          raw_confidence = successes / (successes + failures + 1)  # +1 to avoid div by zero
          age_factor = 1.0 if age < 14 days else exponential decay
          freshness_factor = 1.0 if used in last 7 days else linear decay
          final_score = raw_confidence * age_factor * freshness_factor
        """
        now = time.time()
        successes = entry.get("success_count", 0)
        failures = entry.get("failure_count", 0)
        first_seen = entry.get("first_seen", now)
        last_success = entry.get("last_success", now)

        # 1. Raw success rate
        total = successes + failures + 1  # +1 to avoid division by zero
        raw_confidence = successes / total

        # 2. Age decay (selectors older than 14 days start decaying)
        age_seconds = now - first_seen
        if age_seconds < SELECTOR_AGE_DECAY_THRESHOLD:
            age_factor = 1.0
        else:
            # Exponential decay: each additional day reduces by 5%
            extra_days = (age_seconds - SELECTOR_AGE_DECAY_THRESHOLD) / 86400
            age_factor = max(0.0, 1.0 - (0.05 * extra_days))

        # 3. Freshness decay (not used in last 7 days)
        last_used_ago = now - last_success
        if last_used_ago < SELECTOR_FRESHNESS_THRESHOLD:
            freshness_factor = 1.0
        else:
            # Linear decay: each day without use reduces by 10%
            extra_days = (last_used_ago - SELECTOR_FRESHNESS_THRESHOLD) / 86400
            freshness_factor = max(0.0, 1.0 - (0.1 * extra_days))

        # 4. Final score
        final_score = raw_confidence * age_factor * freshness_factor

        reason = (
            f"raw={raw_confidence:.2f} (success={successes}/{total - 1}), "
            f"age={age_factor:.2f} (age={age_seconds / 86400:.1f}d), "
            f"freshness={freshness_factor:.2f} (last_used={last_used_ago / 86400:.1f}d ago)"
        )

        return SelectorConfidenceScore(
            raw_confidence=raw_confidence,
            age_factor=age_factor,
            freshness_factor=freshness_factor,
            final_score=final_score,
            reason=reason,
        )

    def _auto_cleanup(self, force: bool = False) -> dict:
        """Auto-cleanup low-confidence selectors.

        Returns:
            dict with cleanup stats (domains_checked, selectors_deleted, etc.)

        """
        now = time.time()
        # Only run cleanup every SELECTOR_CLEANUP_CHECK_INTERVAL seconds
        if not force and (now - self._last_cleanup) < SELECTOR_CLEANUP_CHECK_INTERVAL:
            return {}

        threshold: float = (
            getattr(settings, "SELECTOR_CONFIDENCE_THRESHOLD", DEFAULT_SELECTOR_CONFIDENCE_THRESHOLD)
            or DEFAULT_SELECTOR_CONFIDENCE_THRESHOLD
        )
        stats: dict[str, Any] = {
            "domains_checked": 0,
            "selectors_deleted": 0,
            "deleted_domains": [],
            "low_confidence_selectors": [],
        }

        domains_to_delete: list[str] = []

        for domain, entry in self._memory.items():
            stats["domains_checked"] = int(stats["domains_checked"]) + 1
            confidence = self._compute_confidence(entry)

            if confidence.final_score < threshold:
                logger.info(
                    "Deleting low-confidence selector for %s (score=%.2f, %s)",
                    domain,
                    confidence.final_score,
                    confidence.reason,
                )
                stats["selectors_deleted"] = int(stats["selectors_deleted"]) + 1
                stats["deleted_domains"].append(domain)
                stats["low_confidence_selectors"].append(
                    {"domain": domain, "score": confidence.final_score, "reason": confidence.reason},
                )
                domains_to_delete.append(domain)

        # Delete low-confidence entries
        for domain in domains_to_delete:
            del self._memory[domain]

        if domains_to_delete:
            self._save()

        self._last_cleanup = now

        if int(stats["selectors_deleted"]) > 0:
            logger.info(
                "Selector cleanup complete: %d deleted from %d domains",
                int(stats["selectors_deleted"]),
                int(stats["domains_checked"]),
            )

        return stats

    def get_selector_confidence(self, url: str) -> SelectorConfidenceScore | None:
        """Get confidence score for selectors of a domain."""
        domain = self._extract_domain(url)
        if not domain:
            return None

        entry = self._memory.get(domain)
        if not entry:
            return None

        return self._compute_confidence(entry)

    def get_selectors(self, url: str) -> dict | None:
        """Get remembered selectors for a domain with aging and trust decay.

        Also triggers cleanup if it's time.
        """
        # Trigger auto-cleanup if needed (non-blocking)
        self._auto_cleanup()

        domain = self._extract_domain(url)
        if not domain:
            return None

        entry = self._memory.get(domain)
        if not entry:
            return None

        # 1. Failure Threshold
        if entry.get("failure_count", 0) > settings.SELECTOR_MEMORY_MAX_FAILURES:
            logger.debug("Selector memory for %s is suspended (failures: %d)", domain, entry["failure_count"])
            return None

        # 2. Aging (Time-based decay)
        # If the selector is very old (e.g. 30 days), we might want to re-validate it
        # for now we just track it.
        last_success = entry.get("last_success", 0)
        age_days = (time.time() - last_success) / 86400
        if age_days > 30:
            logger.info("Selector memory for %s is aged (%.1f days). Re-discovery recommended.", domain, age_days)
            # We still return it, but could trigger a "soft re-discovery" in
            # orchestrator

        return entry.get("selectors")

    def record_success(self, url: str, selectors: dict) -> None:
        """Record a successful extraction with these selectors."""
        domain = self._extract_domain(url)
        if not domain:
            return

        now = time.time()
        entry = self._memory.get(
            domain,
            {
                "selectors": selectors,
                "success_count": 0,
                "failure_count": 0,
                "first_seen": now,
                "last_success": now,
                "lineage": [],  # Track previous successful selector hashes
            },
        )

        # Update if selectors changed or it's a new entry
        if entry["selectors"] != selectors:
            # Store old selector hash in lineage
            old_hash = str(hash(json.dumps(entry["selectors"], sort_keys=True)))
            if "lineage" not in entry:
                entry["lineage"] = []
            entry["lineage"].append({"hash": old_hash, "replaced_at": now, "successes": entry["success_count"]})

            entry["selectors"] = selectors
            entry["failure_count"] = 0  # Reset failures on change
            entry["last_updated"] = now
            entry["success_count"] = 0

        entry["success_count"] += 1
        entry["last_success"] = now
        self._memory[domain] = entry
        self._save()

    def record_failure(self, url: str) -> None:
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

    def has_memory_for(self, url: str) -> bool:
        """Public predicate: True if a memory entry exists for the URL's domain."""
        domain = self._extract_domain(url)
        return bool(domain and domain in self._memory)

    def invalidate_domain(self, url: str) -> bool:
        """Forget any cached selectors for the URL's domain.

        Returns True if an entry was removed, False if there was nothing
        to forget (or the URL had no parseable domain). Persists the
        updated state to disk so the next process sees the change.

        This is the public replacement for direct ``_memory`` /
        ``_save`` access from recovery handlers and other kernel code.
        """
        domain = self._extract_domain(url)
        if not domain or domain not in self._memory:
            return False
        logger.info("Invalidating selector memory for domain %s", domain)
        del self._memory[domain]
        self._save()
        return True

    def get_memory_stats(self) -> dict[str, Any]:
        """Get current selector memory statistics.

        Returns:
            dict with memory stats (total domains, avg confidence, etc.)

        """
        if not self._memory:
            return {
                "total_domains": 0,
                "avg_confidence": 0.0,
                "total_selectors": 0,
                "high_confidence": 0,
                "medium_confidence": 0,
                "low_confidence": 0,
                "by_confidence": {},
            }

        stats: dict[str, Any] = {
            "total_domains": len(self._memory),
            "avg_confidence": 0.0,
            "total_selectors": len(self._memory),
            "high_confidence": 0,  # >= 0.75
            "medium_confidence": 0,  # 0.5 - 0.74
            "low_confidence": 0,  # < 0.5
            "by_confidence": {},
        }

        total_score = 0.0
        for entry in self._memory.values():
            confidence = self._compute_confidence(entry)
            total_score += confidence.final_score

            score_bucket = f"{confidence.final_score:.2f}"
            bucket = stats["by_confidence"]
            bucket[score_bucket] = bucket.get(score_bucket, 0) + 1

            if confidence.final_score >= 0.75:
                stats["high_confidence"] = int(stats["high_confidence"]) + 1
            elif confidence.final_score >= 0.5:
                stats["medium_confidence"] = int(stats["medium_confidence"]) + 1
            else:
                stats["low_confidence"] = int(stats["low_confidence"]) + 1

        stats["avg_confidence"] = total_score / len(self._memory) if self._memory else 0.0

        return stats

    def force_cleanup(self) -> dict:
        """Force cleanup of low-confidence selectors (ignore interval check)."""
        return self._auto_cleanup(force=True)

    @staticmethod
    def _extract_domain(url: str) -> str | None:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or None
        except (ValueError, AttributeError):
            return None


# Global singleton
_memory: SelectorMemory | None = None


def get_selector_memory() -> SelectorMemory:
    global _memory
    if _memory is None:
        _memory = SelectorMemory()
    return _memory
