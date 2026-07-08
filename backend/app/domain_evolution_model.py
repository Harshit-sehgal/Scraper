"""
Domain Evolution Model — Tracks and models behavioral evolution of scraped domains.

Provides:
  - Mutation frequency tracking (how often does a domain's structure change?)
  - Layout drift detection (selector effectiveness degradation over time)
  - Anti-bot intensification patterns (escalation detection)
  - Stability scoring per domain
  - Predictive re-scheduling for volatile domains

Architecture:
  - Extends DomainIntelligence with evolution-specific metrics
  - Tracks per-domain structual mutation events
  - Models anti-bot escalation as a state machine
  - Produces a "volatility index" for crawl scheduling decisions

LAW: Domains are living systems. Their behavior evolves over time.
The architecture must model and anticipate these changes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict
from collections import deque

from app.selector_memory import get_selector_memory

logger = logging.getLogger(__name__)


async def _trigger_webhook(url: str, payload: dict):
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                logger.warning("Alert webhook returned status code %d", response.status_code)
    except Exception as e:
        logger.warning("Failed to deliver alert webhook: %s", e)


@dataclass
class DomainEvolutionMetrics:
    """Evolution metrics for a single domain."""
    
    domain: str
    mutation_count: int = 0                  # Number of structural changes detected
    layout_drift_events: int = 0             # Number of layout change events
    anti_bot_escalations: int = 0            # Times anti-bot level increased
    current_anti_bot_level: str = "none"     # "none" | "basic" | "moderate" | "aggressive"
    
    avg_stability_window_days: float = 0.0   # Rolling 7-day stability
    selector_lifespan_avg_hours: float = 0.0 # Average selector lifespan
    mutation_frequency: float = 0.0          # Mutations per day
    layout_drift_rate: float = 0.0           # Drift events per day
    
    first_tracked: float = 0.0               # First observation timestamp
    last_mutation: float = 0.0               # Last structural change
    last_anti_bot_change: float = 0.0        # Last anti-bot level change
    
    # Time-series data
    mutation_timeline: deque = field(default_factory=lambda: deque(maxlen=100))
    anti_bot_escalation_timeline: deque = field(default_factory=lambda: deque(maxlen=20))
    
    volatility_index: float = 0.0  # 0.0 (stable) to 1.0 (extremely volatile)
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["mutation_timeline"] = list(self.mutation_timeline)
        d["anti_bot_escalation_timeline"] = list(self.anti_bot_escalation_timeline)
        return d


class DomainEvolutionModel:
    """Models behavioral evolution of domains over time.
    
    Tracks three types of domain evolution:
      1. **Structural mutations**: DOM layout changes detected via selector failure
      2. **Anti-bot escalation**: Intensification of anti-bot measures
      3. **Layout drift**: Gradual degradation of selector accuracy
    
    Produces a **volatility index** per domain that influences:
      - Crawl scheduling (frequent re-checks for volatile domains)
      - Re-discovery frequency (more proactive re-discovery for unstable domains)
      - Resource allocation (conservative for volatile domains)
    """
    
    def __init__(self) -> None:
        self._domains: Dict[str, DomainEvolutionMetrics] = {}
        
        # Anti-bot level thresholds for escalation detection
        self._anti_bot_levels = {
            "none": 0.0,
            "basic": 0.3,
            "moderate": 0.6,
            "aggressive": 0.8,
        }
    
    def _get_or_create(self, domain: str) -> DomainEvolutionMetrics:
        if domain not in self._domains:
            self._domains[domain] = DomainEvolutionMetrics(
                domain=domain,
                first_tracked=time.time(),
            )
        return self._domains[domain]
    
    def record_mutation(self, domain: str) -> None:
        """Record a structural mutation (layout/selector change)."""
        metrics = self._get_or_create(domain)
        metrics.mutation_count += 1
        metrics.last_mutation = time.time()
        metrics.mutation_timeline.append(time.time())
        metrics.layout_drift_events += 1
        self._recompute_volatility(domain)
    
    def record_selector_replaced(self, domain: str, previous_lifespan_hours: float) -> None:
        """Record that a selector was replaced for a domain.
        
        Args:
            domain: The domain whose selector was replaced
            previous_lifespan_hours: How long the previous selector lasted
        """
        metrics = self._get_or_create(domain)
        metrics.mutation_count += 1
        metrics.last_mutation = time.time()
        metrics.mutation_timeline.append(time.time())
        
        # Update average selector lifespan
        alpha = 0.3
        if metrics.selector_lifespan_avg_hours > 0:
            metrics.selector_lifespan_avg_hours = (
                (1 - alpha) * metrics.selector_lifespan_avg_hours +
                alpha * previous_lifespan_hours
            )
        else:
            metrics.selector_lifespan_avg_hours = previous_lifespan_hours
        
        self._recompute_volatility(domain)
    
    def record_anti_bot_escalation(self, domain: str, new_anti_bot_score: float) -> None:
        """Record a change in anti-bot intensity.
        
        Args:
            domain: The domain experiencing escalation
            new_anti_bot_score: Current anti-bot detection score [0, 1]
        """
        metrics = self._get_or_create(domain)
        
        # Determine new level
        old_level = metrics.current_anti_bot_level
        new_level = "none"
        for level, threshold in sorted(self._anti_bot_levels.items(), key=lambda x: x[1]):
            if new_anti_bot_score >= threshold:
                new_level = level
        
        metrics.current_anti_bot_level = new_level
        
        # Detect escalation
        if new_level != old_level:
            metrics.anti_bot_escalations += 1
            metrics.last_anti_bot_change = time.time()
            metrics.anti_bot_escalation_timeline.append({
                "timestamp": time.time(),
                "old_level": old_level,
                "new_level": new_level,
                "score": new_anti_bot_score,
            })
            logger.info(
                "Anti-bot escalation detected for %s: %s → %s (score=%.2f)",
                domain, old_level, new_level, new_anti_bot_score,
            )
            
            from app.config import settings
            webhook_url = getattr(settings, "ALERT_WEBHOOK_URL", None)
            if webhook_url:
                payload = {
                    "event": "anti_bot_escalation",
                    "domain": domain,
                    "old_level": old_level,
                    "new_level": new_level,
                    "score": new_anti_bot_score,
                    "timestamp": time.time(),
                }
                try:
                    import asyncio
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        loop.create_task(_trigger_webhook(webhook_url, payload))
                except RuntimeError:
                    # No running event loop, send in background thread
                    import threading
                    def fire_sync():
                        import httpx
                        try:
                            httpx.post(webhook_url, json=payload, timeout=5.0)
                        except Exception as ex:
                            logger.debug("Failed to deliver webhook synchronously: %s", ex)
                    threading.Thread(target=fire_sync, daemon=True).start()
        
        self._recompute_volatility(domain)
    
    def analyze_from_memory(self) -> None:
        """Analyze all domains in selector memory for evolution patterns."""
        memory = get_selector_memory()
        
        for domain, entry in list(memory._memory.items()):
            metrics = self._get_or_create(domain)
            
            # Detect from entry metadata
            lineage = entry.get("lineage", [])
            if lineage:
                metrics.mutation_count = len(lineage)
                metrics.last_mutation = lineage[-1].get("replaced_at", 0)
            
            # Check failure counts as mutation signal
            failures = entry.get("failure_count", 0)
            if failures > 3 and metrics.mutation_count == 0:
                # High failure rate without recorded mutations suggests unobserved drift
                self._record_drift_event(domain)
    
    def _record_drift_event(self, domain: str) -> None:
        """Record a layout drift event (gradual degradation)."""
        metrics = self._get_or_create(domain)
        metrics.layout_drift_events += 1
    
    def _recompute_volatility(self, domain: str) -> None:
        """Recompute the volatility index for a domain.
        
        Volatility index combines:
          - Mutation frequency (mutations per day)
          - Anti-bot escalation activity
          - Layout drift rate
        """
        metrics = self._domains.get(domain)
        if not metrics:
            return
        
        now = time.time()
        days_tracked = max(1.0, (now - metrics.first_tracked) / 86400)
        
        # Mutation frequency (normalized to 1 mutation/day = 0.5 volatility)
        mutation_rate = metrics.mutation_count / days_tracked
        mutation_factor = min(1.0, mutation_rate * 0.5)
        
        # Anti-bot escalation factor
        escalation_rate = metrics.anti_bot_escalations / max(1, days_tracked)
        escalation_factor = min(0.5, escalation_rate * 0.25)
        
        # Drift factor
        drift_rate = metrics.layout_drift_events / days_tracked
        drift_factor = min(0.3, drift_rate * 0.15)
        
        # Recency boost: recent mutations increase volatility
        recency_boost = 0.0
        if metrics.last_mutation > 0:
            hours_since_mutation = (now - metrics.last_mutation) / 3600
            if hours_since_mutation < 24:  # Within last day
                recency_boost = 0.2
            elif hours_since_mutation < 72:  # Within last 3 days
                recency_boost = 0.1
        
        volatility = min(1.0, mutation_factor + escalation_factor + drift_factor + recency_boost)
        metrics.volatility_index = round(volatility, 3)
        metrics.mutation_frequency = round(mutation_rate, 3)
        metrics.layout_drift_rate = round(drift_rate, 3)
    
    def get_domain_evolution(self, domain: str) -> Optional[DomainEvolutionMetrics]:
        """Get evolution metrics for a domain."""
        return self._domains.get(domain)
    
    def get_volatile_domains(self, threshold: float = 0.5) -> list[DomainEvolutionMetrics]:
        """Get domains whose volatility exceeds a threshold.
        
        Args:
            threshold: Volatility threshold (default 0.5)
            
        Returns:
            List of volatile domains sorted by volatility (highest first)
        """
        volatile = [
            m for m in self._domains.values()
            if m.volatility_index >= threshold
        ]
        return sorted(volatile, key=lambda x: x.volatility_index, reverse=True)
    
    def get_evolution_report(self) -> dict:
        """Get comprehensive evolution analysis report."""
        if not self._domains:
            return {
                "total_domains": 0,
                "avg_volatility": 0.0,
                "volatile_domains": 0,
                "total_mutations": 0,
                "total_anti_bot_escalations": 0,
            }
        
        volatile = self.get_volatile_domains()
        total_mutations = sum(m.mutation_count for m in self._domains.values())
        total_escalations = sum(m.anti_bot_escalations for m in self._domains.values())
        avg_volatility = sum(m.volatility_index for m in self._domains.values()) / len(self._domains)
        
        return {
            "total_domains": len(self._domains),
            "avg_volatility": round(avg_volatility, 3),
            "volatile_domains": len(volatile),
            "total_mutations": total_mutations,
            "total_anti_bot_escalations": total_escalations,
            "volatile_list": [
                {
                    "domain": m.domain,
                    "volatility": m.volatility_index,
                    "mutations": m.mutation_count,
                    "escalations": m.anti_bot_escalations,
                    "anti_bot_level": m.current_anti_bot_level,
                    "avg_selector_lifespan_hours": round(m.selector_lifespan_avg_hours, 1),
                }
                for m in volatile[:20]
            ],
            "domain_map": {
                m.domain: {
                    "volatility": m.volatility_index,
                    "mutations": m.mutation_count,
                    "anti_bot_level": m.current_anti_bot_level,
                    "stability_days": round(
                        (time.time() - m.first_tracked) / 86400, 1
                    ) if m.first_tracked > 0 else 0.0,
                }
                for m in list(self._domains.values())[:100]
            },
        }


# Global singleton
_evolution_model: DomainEvolutionModel | None = None


def get_domain_evolution_model() -> DomainEvolutionModel:
    """Get the global domain evolution model."""
    global _evolution_model
    if _evolution_model is None:
        _evolution_model = DomainEvolutionModel()
    return _evolution_model
