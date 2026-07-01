"""FAQ extraction — detects FAQPage schema and common Q&A patterns.

Scans HTML for structured FAQ content via two strategies:

1. **Schema.org detection**: Parses ``FAQPage`` / ``Question`` /
   ``Answer`` microdata, JSON-LD, or RDFa and extracts all
   question-answer pairs with confidence.

2. **Structural heuristics**: Falls back to common UI patterns when
   no FAQ schema is found — accordion containers (``<details>`` /
   ``<summary>``), ``dt``/``dd`` lists, and ``[data-faq]`` /
   ``[data-question]`` annotated elements.

No remote calls, no LLM, no Playwright — pure HTML parsing via
BeautifulSoup, matching the convention established by
``variant_extractor.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Tag

_ACCORDION_RE = re.compile(r"accordion|faq|qa|questions?", re.IGNORECASE)
_QUESTION_RE = re.compile(
    r"(?:what|how|why|when|where|who|can|do|does|is|are|was|were)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QAPair:
    """A single question-answer pair."""

    question: str
    answer: str
    source: str = "schema"  # "schema" | "details" | "dl" | "data_attr" | "heading"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "source": self.source,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class FAQExtractionResult:
    """Aggregate FAQ extraction result."""

    pairs: list[QAPair] = field(default_factory=list)
    source: str = "none"  # "schema" | "heuristic" | "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairs": [p.to_dict() for p in self.pairs],
            "source": self.source,
            "count": len(self.pairs),
        }


# ── Schema.org extraction ───────────────────────────────────────────


def _extract_schema_json_ld(soup: BeautifulSoup) -> list[QAPair]:
    """Extract Q&A pairs from ``<script type=\"application/ld+json\">`` blocks."""
    pairs: list[QAPair] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string) if script.string else {}
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type", "")
            if item_type == "FAQPage":
                main_entity = item.get("mainEntity", [])
                if isinstance(main_entity, dict):
                    main_entity = [main_entity]
                for entry in main_entity:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("@type") == "Question":
                        q_name = entry.get("name", "")
                        answer = entry.get("suggestedAnswer") or entry.get("acceptedAnswer") or {}
                        a_text = answer.get("text", "") if isinstance(answer, dict) else ""
                        if q_name and a_text:
                            pairs.append(
                                QAPair(
                                    question=q_name,
                                    answer=a_text,
                                    source="schema",
                                    confidence=0.95,
                                )
                            )
            elif item_type == "Question":
                q_name = item.get("name", "")
                answer = item.get("suggestedAnswer") or item.get("acceptedAnswer") or {}
                a_text = answer.get("text", "") if isinstance(answer, dict) else ""
                if q_name and a_text:
                    pairs.append(
                        QAPair(
                            question=q_name,
                            answer=a_text,
                            source="schema",
                            confidence=0.9,
                        )
                    )
    return pairs


def _extract_schema_microdata(soup: BeautifulSoup) -> list[QAPair]:
    """Extract Q&A pairs from schema.org microdata attributes."""
    pairs: list[QAPair] = []
    faq_containers = soup.find_all(attrs={"itemtype": re.compile(r"https?://schema\.org/FAQPage", re.IGNORECASE)})
    for container in faq_containers:
        questions = container.find_all(attrs={"itemtype": re.compile(r"https?://schema\.org/Question", re.IGNORECASE)})
        for question in questions:
            q_name = question.find(attrs={"itemprop": "name"})
            q_text = q_name.get_text(strip=True) if q_name else ""
            answer = question.find(attrs={"itemprop": re.compile(r"(suggestedAnswer|acceptedAnswer)", re.IGNORECASE)})
            a_text_wrapper = answer.find(attrs={"itemprop": "text"}) if answer else None
            a_text = a_text_wrapper.get_text(strip=True) if a_text_wrapper else ""
            if q_text and a_text:
                pairs.append(QAPair(question=q_text, answer=a_text, source="schema", confidence=0.95))
    return pairs


# ── Heuristic extraction ────────────────────────────────────────────


def _extract_details_summary(soup: BeautifulSoup) -> list[QAPair]:
    """Extract Q&A from ``<details>`` / ``<summary>`` elements inside FAQ containers."""
    pairs: list[QAPair] = []
    for details in soup.find_all("details"):
        summary = details.find("summary")
        summary_text = summary.get_text(strip=True) if summary else ""
        # Only accept if the parent container looks like FAQ or the summary looks like a question
        parent = details.find_parent()
        parent_classes = " ".join(parent.get("class", [])) if parent else ""
        if not summary_text:
            continue
        if not _ACCORDION_RE.search(parent_classes) and not _QUESTION_RE.match(summary_text):
            continue
        # Answer is the text content of <details> excluding the <summary>
        parts: list[str] = []
        for child in details.children:
            if isinstance(child, Tag) and child.name == "summary":
                continue
            if isinstance(child, Tag):
                parts.append(child.get_text(" ", strip=True))
            elif hasattr(child, "strip"):
                stripped = str(child).strip()
                if stripped:
                    parts.append(stripped)
        answer_text = " ".join(parts)
        if summary_text and answer_text:
            pairs.append(
                QAPair(
                    question=summary_text,
                    answer=answer_text,
                    source="details",
                    confidence=0.7,
                )
            )
    return pairs


def _extract_dt_dd(soup: BeautifulSoup) -> list[QAPair]:
    """Extract Q&A from ``<dt>`` / ``<dd>`` pairs inside FAQ containers."""
    pairs: list[QAPair] = []
    # Find <dl> inside FAQ-looking containers
    for dl in soup.find_all("dl"):
        # Check if parent container looks like FAQ
        parent = dl.find_parent()
        parent_classes = " ".join(parent.get("class", [])) if parent else ""
        parent_id = parent.get("id", "") if parent else ""
        if not _ACCORDION_RE.search(f"{parent_classes} {parent_id}"):
            continue
        terms = dl.find_all("dt")
        for dt in terms:
            q_text = dt.get_text(strip=True)
            if not q_text:
                continue
            dd = dt.find_next_sibling("dd")
            a_text = dd.get_text(strip=True) if dd else ""
            if a_text:
                pairs.append(
                    QAPair(
                        question=q_text,
                        answer=a_text,
                        source="dl",
                        confidence=0.65,
                    )
                )
    return pairs


def _extract_data_attr(soup: BeautifulSoup) -> list[QAPair]:
    """Extract Q&A from ``[data-faq]`` / ``[data-question]`` annotated elements."""
    pairs: list[QAPair] = []
    for container in soup.find_all(lambda tag: tag.name and tag.has_attr("data-faq")):
        questions = container.find_all(lambda tag: tag.name and tag.has_attr("data-question"))
        for q_elem in questions:
            q_text = q_elem.get("data-question") or q_elem.get_text(strip=True)
            if not q_text:
                q_text = q_elem.get_text(strip=True)
            if not q_text:
                continue
            # Answer may be on the same element (data-answer attribute), or
            # the next sibling with data-answer, or the next sibling element.
            a_text = q_elem.get("data-answer") or ""
            if not a_text:
                ans = q_elem.find_next_sibling(lambda tag: tag.name and tag.has_attr("data-answer"))
                if not ans:
                    ans = q_elem.find_next_sibling()
                a_text = ans.get("data-answer") if ans and ans.get("data-answer") else (ans.get_text(strip=True) if ans else "")
            if a_text:
                pairs.append(
                    QAPair(
                        question=q_text,
                        answer=a_text,
                        source="data_attr",
                        confidence=0.75,
                    )
                )
    return pairs


def _extract_heading_paragraph(soup: BeautifulSoup) -> list[QAPair]:
    """Extract Q&A from heading+paragraph patterns inside FAQ containers."""
    pairs: list[QAPair] = []
    for container in soup.find_all(class_=_ACCORDION_RE):
        headings = container.find_all(["h2", "h3", "h4", "h5", "h6"])
        for heading in headings:
            q_text = heading.get_text(strip=True)
            if not q_text or not _QUESTION_RE.match(q_text):
                continue
            sibling = heading.find_next_sibling()
            # Accept the next paragraph or div with text content
            if sibling and sibling.name in ("p", "div", "span"):
                a_text = sibling.get_text(strip=True)
                if a_text and len(a_text) > 10:
                    pairs.append(
                        QAPair(
                            question=q_text,
                            answer=a_text,
                            source="heading",
                            confidence=0.5,
                        )
                    )
    return pairs


# ── Public API ──────────────────────────────────────────────────────


def extract_faq(
    html: str,
    *,
    enable_heuristics: bool = True,
) -> FAQExtractionResult:
    """Extract FAQ question-answer pairs from HTML.

    Prefers schema.org structured data first; falls back to heuristic
    patterns when ``enable_heuristics`` is True (default).

    Args:
        html: Raw HTML of the page (may be a partial document).
        enable_heuristics: When True, also scans for structural FAQ
            patterns (``<details>``, ``<dl>``, data attributes,
            heading+paragraph pairs inside FAQ containers).

    Returns:
        :class:`FAQExtractionResult` with extracted pairs and the
        detection source.
    """
    soup = BeautifulSoup(html, "html.parser")
    all_pairs: list[QAPair] = []

    # Stage 1: Schema.org (JSON-LD + microdata)
    schema_pairs = _extract_schema_json_ld(soup) + _extract_schema_microdata(soup)
    if schema_pairs:
        all_pairs.extend(schema_pairs)
        return FAQExtractionResult(pairs=schema_pairs, source="schema")

    # Stage 2: Heuristic patterns (only if schemas didn't fire)
    if enable_heuristics:
        for extractor in (
            _extract_details_summary,
            _extract_dt_dd,
            _extract_data_attr,
            _extract_heading_paragraph,
        ):
            try:
                pairs = extractor(soup)
                all_pairs.extend(pairs)
            except (AttributeError, TypeError, ValueError):
                continue

    source = "heuristic" if all_pairs else "none"
    return FAQExtractionResult(pairs=all_pairs, source=source)
