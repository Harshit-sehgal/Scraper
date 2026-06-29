"""Semantic page-type classifier.

Heuristic, rule-based classifier that labels a page by what kind of
content it carries — product, listing, article, job posting, event,
review, forum, social media, search results, or unknown.

The classifier is intentionally lightweight: it inspects structural
cues in the supplied HTML (Schema.org types, button text, CSS class
hints, tag presence) and the record count returned by extraction.
No remote calls, no LLM, no Playwright.

Use it to:
  * Surface page-type labels in the job details API (Wave 5 #19).
  * Bias strategy selection: product pages want HEADLESS requests,
    social media feeds want PLAYWRIGHT_FULL.
  * Power the page-specific cascade tuning in subsequent waves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PageType(StrEnum):
    """Semantic page-type labels."""

    PRODUCT = "product"
    LISTING = "listing"
    ARTICLE = "article"
    JOB_POSTING = "job_posting"
    EVENT = "event"
    REVIEW = "review"
    FORUM = "forum"
    SOCIAL_MEDIA = "social_media"
    SEARCH_RESULTS = "search_results"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PageTypeClassification:
    """Result of classifying a single page.

    ``confidence`` is in [0.0, 1.0] and represents how strongly the
    heuristic evidence supports the chosen label. ``alternatives``
    lists runner-up page types whose summed weight exceeds a 0.2
    threshold so callers can surface "could also be X" hints.
    """

    page_type: PageType
    confidence: float
    signals: dict[str, float] = field(default_factory=dict)
    alternatives: list[PageType] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_type": self.page_type.value,
            "confidence": round(self.confidence, 4),
            "signals": {k: round(v, 4) for k, v in self.signals.items()},
            "alternatives": [p.value for p in self.alternatives],
        }


# Patterns probed from the raw HTML. Each tuple is (compiled regex,
# signal weight). Order is irrelevant — all matches accumulate.
_SIGNAL_PATTERNS: tuple[tuple[re.Pattern[str], tuple[str, PageType, float]], ...] = (
    (
        re.compile(r"itemtype=\"https?://schema\.org/Product\"|@type\"\s*:\s*\"Product\"|@type\":\"Product\""),
        ("schema_org", PageType.PRODUCT, 0.8),
    ),
    (
        re.compile(r"itemtype=\"https?://schema\.org/JobPosting\"|@type\":\"JobPosting\""),
        ("schema_org", PageType.JOB_POSTING, 0.8),
    ),
    (re.compile(r"itemtype=\"https?://schema\.org/Event\"|@type\":\"Event\""), ("schema_org", PageType.EVENT, 0.7)),
    (
        re.compile(r"itemtype=\"https?://schema\.org/Article\|NewsArticle\|BlogPosting\"|@type\":\"Article\""),
        ("schema_org", PageType.ARTICLE, 0.6),
    ),
    (re.compile(r"itemtype=\"https?://schema\.org/Review\"|@type\":\"Review\""), ("schema_org", PageType.REVIEW, 0.6)),
    (re.compile(r"add\s+to\s+cart|add\s+to\s+basket|buy\s+now", re.IGNORECASE), ("button_text", PageType.PRODUCT, 0.6)),
    (
        re.compile(r"apply\s+now|apply\s+for\s+this\s+job|submit\s+application", re.IGNORECASE),
        ("button_text", PageType.JOB_POSTING, 0.6),
    ),
    (
        re.compile(r"tweet|twitter-post|social-tweet|fb-post|linkedin-post", re.IGNORECASE),
        ("class_hint", PageType.SOCIAL_MEDIA, 0.5),
    ),
    (re.compile(r"comment-thread|discussion-thread|forum-thread|reply-list", re.IGNORECASE), ("class_hint", PageType.FORUM, 0.5)),
    (
        re.compile(r"class=\"[^\"]*(?:result|results)-count|resultCount|search-results", re.IGNORECASE),
        ("class_hint", PageType.SEARCH_RESULTS, 0.4),
    ),
    (re.compile(r"<article\b|class=\"[^\"]*article[^\"]*\"", re.IGNORECASE), ("tag", PageType.ARTICLE, 0.3)),
    (re.compile(r"\$\d|\£\d|\€\d|\¥\d|\₹\d", re.IGNORECASE), ("price_visible", PageType.PRODUCT, 0.3)),
)

_ALT_THRESHOLD = 0.2


def _score_signals(html: str) -> dict[PageType, tuple[float, dict[str, float]]]:
    """Aggregate per-PageType weights and which signals fired."""
    scores: dict[PageType, float] = dict.fromkeys(PageType, 0.0)
    fired: dict[PageType, dict[str, float]] = {pt: {} for pt in PageType}
    if not html:
        return {pt: (0.0, {}) for pt in PageType}

    for pattern, (signal_name, page_type, weight) in _SIGNAL_PATTERNS:
        if pattern.search(html) and signal_name not in fired[page_type]:
            # Idempotent per-signal: only adds weight the first time the
            # signal fires for that page_type so duplicate matches don't
            # stack runaway weights.
            scores[page_type] += weight
            fired[page_type][signal_name] = weight
    return {pt: (scores[pt], fired[pt]) for pt in PageType}


def _apply_count_bonus(record_count: int) -> dict[PageType, float]:
    """Add small bonuses based on the extracted record count.

    ``listing`` is the only type whose primary signal is many records on
    one page; the rest are roughly single-record. ``unknown`` never
    receives an automatic boost.
    """
    if record_count <= 0:
        return {}
    if record_count == 1:
        return {PageType.PRODUCT: 0.2, PageType.JOB_POSTING: 0.2}
    if record_count >= 5:
        return {PageType.LISTING: 0.3, PageType.SEARCH_RESULTS: 0.2}
    return {PageType.LISTING: 0.1}


def classify_page_type(
    html: str,
    *,
    url: str = "",
    record_count: int = 0,
    has_schema_org: bool = False,
) -> PageTypeClassification:
    """Classify a page's content type using structural HTML cues.

    Args:
        html: Raw HTML body of the page. May be empty (returns UNKNOWN).
        url: Optional URL — currently unused but reserved so future
            domain patterns can fold in (e.g., ``/jobs/`` paths).
        record_count: Number of records the extractor returned. Used as
            a soft bonus when many or exactly one record surfaces.
        has_schema_org: Whether any schema.org structured data was
            detected upstream. When false, the schema_org signal weight
            is suppressed slightly so non-semantic pages don't get
            over-classified as ``product``.

    Returns:
        :class:`PageTypeClassification` with the chosen label,
        confidence (in [0, 1]), a dict of the contributing signals,
        and the runner-up labels whose weights exceeded the threshold.
    """
    del url  # Reserved for future path-based heuristics.

    signals_by_type = _score_signals(html)
    scores: dict[PageType, float] = {pt: weight for pt, (weight, _) in signals_by_type.items()}
    flattened: dict[str, float] = {}
    for pt, (_, signals) in signals_by_type.items():
        for signal_name, signal_weight in signals.items():
            flattened[f"{signal_name}→{pt.value}"] = signal_weight
            if has_schema_org is False and signal_name == "schema_org":
                # Schema.org signals only count when the upstream detector saw them.
                scores[pt] -= signal_weight
                flattened[f"{signal_name}→{pt.value}"] = 0.0

    for pt, bonus in _apply_count_bonus(record_count).items():
        scores[pt] += bonus
        flattened[f"record_count→{pt.value}"] = bonus

    contributions = flattened

    best = max(scores.items(), key=lambda kv: kv[1])
    best_type, best_score = best[0], best[1]

    # Compute alternatives (anything above ALT_THRESHOLD and not the winner).
    others = sorted(
        ((pt, score) for pt, score in scores.items() if pt != best_type and score > _ALT_THRESHOLD),
        key=lambda kv: kv[1],
        reverse=True,
    )
    alternatives = [pt for pt, _ in others]

    if best_score <= 0.05:
        return PageTypeClassification(
            page_type=PageType.UNKNOWN,
            confidence=0.0,
            signals=contributions,
            alternatives=alternatives,
        )

    # Normalize confidence: cap at 0.95 to leave room for uncertainty.
    confidence = min(0.95, best_score)
    return PageTypeClassification(
        page_type=best_type,
        confidence=round(confidence, 4),
        signals=contributions,
        alternatives=alternatives,
    )
