"""Adaptive scraper hooks — side-effect observations that do not affect the extraction result.

Extracted from ``scraper.py`` during the Phase C refactoring.

These functions record observations into various adaptive / predictive
subsystems after a scrape completes. They are designed to be called as
fire-and-forget hooks; failures are logged but never propagated.
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from app.config import settings
from app.crawl_frontier import get_crawl_frontier

logger = logging.getLogger(__name__)


def _run_motif_feedback(results: list[dict], schema_fields: list, world_state: Any | None) -> int:
    """Extract field co-occurrence motifs from results and feed back into world_state.

    Returns the number of new motifs added (0 if none or if world_state is unavailable).
    """
    new_motifs: list = []
    if results and world_state:
        from app.motif_feedback import MotifFeedbackEngine  # research-shell, lazy

        feedback_engine = MotifFeedbackEngine()
        new_motifs = feedback_engine.extract_motifs_from_results(
            results,
            schema_fields,
            min_cooccurrence=settings.MOTIF_MIN_COOCCURRENCE,
        )
        if new_motifs:
            if hasattr(world_state, "add_solidified_motifs"):
                added = world_state.add_solidified_motifs(new_motifs)
            else:
                added = 0
                if hasattr(world_state, "_history") and hasattr(world_state._history, "add_solidified_motifs"):
                    added = world_state._history.add_solidified_motifs(new_motifs)
            logger.info(
                "[Scraper] Closed motif feedback loop: %d new motifs (of %d candidates) from %d results",
                added,
                len(new_motifs),
                len(results),
            )
            return added
    elif results and not world_state:
        logger.debug("[Scraper] No world_state available, skipping motif feedback")
    return 0


async def _run_crawl_frontier_link_discovery(
    url: str,
    html: str,
    domain: str,
    source_depth: int = 0,
) -> int:
    """Extract links from the page and add them to the crawl frontier.

    Returns the number of links successfully added to the frontier.
    """
    try:
        from urllib.parse import urljoin, urlparse

        soup = BeautifulSoup(html, "html.parser")
        discovered_links = []
        for a_tag in soup.find_all("a", href=True):
            href_val = a_tag.get("href")
            href = href_val[0] if isinstance(href_val, list) else str(href_val) if href_val else ""
            if not href:
                continue
            if href.startswith("http") and domain in urlparse(href).netloc:
                discovered_links.append(href)
            elif href.startswith(("/", "?")):
                full_url = urljoin(url, href)
                if domain in urlparse(full_url).netloc:
                    discovered_links.append(full_url)

        if discovered_links:
            frontier = get_crawl_frontier()
            added = await frontier.add_discovered_links(discovered_links, url, source_depth=source_depth)
            if added > 0:
                logger.debug("[Scraper] Added %d/%d discovered links to frontier from %s", added, len(discovered_links), url)
            return added
    except Exception as e:
        logger.debug("[Scraper] Link discovery skipped for %s: %s", url, e)
    return 0


def _run_selector_decay_prediction(domain: str, selector_hit_rate: float) -> None:
    """Record selector hit-rate observation and log decay predictions.

    Fire-and-forget: failures are logged but never propagated.
    """
    try:
        from app.selector_decay_predictor import (
            get_selector_decay_predictor,  # research-shell, lazy
        )

        decay_predictor = get_selector_decay_predictor()
        decay_predictor.record_observation(domain, selector_hit_rate)

        prediction = decay_predictor.predict_decay(domain)
        if prediction.risk_level in ("decaying", "critical"):
            logger.info(
                "[PredictiveAdaptation] %s decay risk=%.2f level=%s days_until_failure=%.1f",
                domain,
                prediction.decay_risk,
                prediction.risk_level,
                prediction.days_until_failure,
            )
    except Exception as e:
        logger.debug("[PredictiveAdaptation] Decay prediction failed: %s", e)


def _run_domain_evolution_modeling(domain: str, extraction_method: str, anti_bot_score: float) -> None:
    """Record mutations and anti-bot changes in the domain evolution model.

    Fire-and-forget: failures are logged but never propagated.
    """
    try:
        from app.domain_evolution_model import (
            get_domain_evolution_model,  # research-shell, lazy
        )

        evolution_model = get_domain_evolution_model()
        if extraction_method == "regex":
            evolution_model.record_mutation(domain)
        if anti_bot_score > 0.5:
            evolution_model.record_anti_bot_escalation(domain, anti_bot_score)
    except Exception as e:
        logger.debug("[PredictiveAdaptation] Evolution modeling failed: %s", e)


def _run_self_tuning_extraction(
    domain: str,
    fetch_ms: float,
    classification: Any | None,
    confidence_map: dict | None,
    anti_bot_score: float,
) -> None:
    """Feed telemetry into the self-tuning extraction controller.

    Fire-and-forget: failures are logged but never propagated.
    """
    try:
        from app.self_tuning_extraction import (
            get_self_tuning_controller,  # research-shell, lazy
        )

        tuning_controller = get_self_tuning_controller()
        tuning_controller.record_telemetry(
            domain,
            {
                "fetch_ms": fetch_ms,
                "error": classification.category.value if classification else None,
                "failure_category": classification.category.value if classification else None,
                "anti_bot_score": anti_bot_score,
                "confidence_map": confidence_map or {},
            },
        )
    except Exception as e:
        logger.debug("[PredictiveAdaptation] Self-tuning failed: %s", e)


def run_all_adaptive_hooks(
    url: str,  # noqa: ARG001, RUF100
    html: str,  # noqa: ARG001, RUF100
    domain: str,
    results: list[dict],
    schema_fields: list,
    world_state: Any | None,
    extraction_method: str,
    fetch_ms: float,
    selector_hit_rate: float,
    confidence_map: dict | None,
    classification: Any | None,
    anti_bot_score: float,
) -> int:
    """Run all adaptive observation hooks after a scrape completes.

    This is a convenience function that calls each adaptive hook in turn.
    Failures are caught per-hook and logged; the calling scrape is never
    affected.

    Args:
        Returns: Number of new motifs added (0 if none or world_state unavailable).

    """
    new_motifs = _run_motif_feedback(results, schema_fields, world_state)
    _run_selector_decay_prediction(domain, selector_hit_rate)
    _run_domain_evolution_modeling(domain, extraction_method, anti_bot_score)
    _run_self_tuning_extraction(domain, fetch_ms, classification, confidence_map, anti_bot_score)
    return new_motifs
