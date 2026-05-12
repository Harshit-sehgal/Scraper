"""
Temporal Reasoning Engine
===========================
Infers temporal relationships, chronology, and event ordering.

Core principle: Dates are not just values - they participate in sequences,
timelines, and temporal relationships.

The engine understands:
- Chronological ordering (date A before date B)
- Event sequencing (departure → arrival)
- Duration inference (start + duration = end)
- Temporal grouping (multiple dates in same record)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from app.semantic_ir import (
    RelationshipEdge,
    SemanticGraph,
    SemanticToken,
    SemanticType,
)


@dataclass
class TemporalEvent:
    """A temporal event with inferred timing."""
    token_idx: int
    raw: str
    parsed_date: Optional[datetime] = None
    event_type: str = ""  # "departure", "arrival", "checkin", "checkout", "start", "end"
    confidence: float = 0.0
    position: int = 0


@dataclass
class Timeline:
    """A sequence of temporal events in order."""
    events: List[TemporalEvent] = field(default_factory=list)
    is_ordered: bool = False
    span_duration: Optional[timedelta] = None
    coherence: float = 0.0


DATE_FORMATS = [
    r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",       # 22-05-2026
    r"(\d{4})[/-](\d{2})[/-](\d{1,2})",             # 2026-05-22
    r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{2,4})",  # 22 May 2026
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2}),?\s+(\d{2,4})",  # May 22, 2026
]

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_date(text: str) -> Optional[datetime]:
    """Parse a date string to datetime."""
    for fmt in DATE_FORMATS:
        m = re.match(fmt, text, re.IGNORECASE)
        if not m:
            continue
        groups = m.groups()
        if len(groups) == 3:
            if fmt == DATE_FORMATS[0]:  # dd-mm-yyyy
                d, mo, y = int(groups[0]), int(groups[1]), int(groups[2])
            elif fmt == DATE_FORMATS[1]:  # yyyy-mm-dd
                y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
            elif fmt == DATE_FORMATS[2]:  # dd Mon yyyy
                d, mon, y = int(groups[0]), groups[1].lower(), int(groups[2])
                mo = MONTH_MAP.get(mon, 1)
            elif fmt == DATE_FORMATS[3]:  # Mon dd, yyyy
                mon, d, y = groups[0].lower(), int(groups[1]), int(groups[2])
                mo = MONTH_MAP.get(mon, 1)
            y = y + 2000 if y < 100 else y
            try:
                return datetime(y, mo, d)
            except ValueError:
                continue
    return None


def build_timeline(tokens: List[SemanticToken]) -> Timeline:
    """Build a timeline from date tokens in a record."""
    events: List[TemporalEvent] = []

    for i, token in enumerate(tokens):
        if token.primary_type != SemanticType.DATE:
            continue
        parsed = parse_date(token.raw)
        event_type = _infer_temporal_role(token, tokens, i)
        events.append(TemporalEvent(
            token_idx=i,
            raw=token.raw,
            parsed_date=parsed,
            event_type=event_type,
            confidence=0.8 if parsed else 0.3,
            position=token.position,
        ))

    if not events:
        return Timeline()

    # Sort by parsed date if available, otherwise by position
    dated = [e for e in events if e.parsed_date]
    if dated:
        dated.sort(key=lambda e: e.parsed_date)
        is_ordered = all(
            dated[i].parsed_date <= dated[i + 1].parsed_date
            for i in range(len(dated) - 1)
        )
        span = dated[-1].parsed_date - dated[0].parsed_date if len(dated) >= 2 else None
    else:
        events.sort(key=lambda e: e.position)
        is_ordered = True
        span = None

    coherence = _compute_timeline_coherence(events)

    return Timeline(
        events=events,
        is_ordered=is_ordered,
        span_duration=span,
        coherence=coherence,
    )


def _infer_temporal_role(token: SemanticToken, tokens: List[SemanticToken], idx: int) -> str:
    """Infer the temporal role of a date token based on context.

    Uses positional and neighbor signals, NOT domain knowledge.
    """
    # First date in sequence → likely departure/start
    date_indices = [i for i, t in enumerate(tokens) if t.primary_type == SemanticType.DATE]
    if not date_indices:
        return "temporal"
    if idx == date_indices[0]:
        return "start"
    if idx == date_indices[-1] and len(date_indices) > 1:
        return "end"
    return "intermediate"


def _compute_timeline_coherence(events: List[TemporalEvent]) -> float:
    """Compute how coherent a timeline is.

    High coherence: dates are ordered, parsed, consistent.
    Low coherence: dates conflict, unparseable, or incomplete.
    """
    if not events:
        return 0.0

    # Parse ratio
    parsed = [e for e in events if e.parsed_date]
    parse_ratio = len(parsed) / len(events)

    # Chronological order
    ordered_count = sum(
        1 for i in range(len(parsed) - 1)
        if parsed[i].parsed_date <= parsed[i + 1].parsed_date
    ) if len(parsed) >= 2 else 1
    order_ratio = ordered_count / max(len(parsed) - 1, 1)

    coherence = (parse_ratio * 0.5) + (order_ratio * 0.5)
    return min(coherence, 1.0)


def infer_temporal_relationships(timeline: Timeline) -> List[RelationshipEdge]:
    """Infer temporal relationships from a timeline.

    Relationships:
    - before (A comes before B chronologically)
    - after (A comes after B)
    - duration (A and B define a time span)
    """
    edges: List[RelationshipEdge] = []

    parsed = [e for e in timeline.events if e.parsed_date]
    for i in range(len(parsed)):
        for j in range(i + 1, len(parsed)):
            a, b = parsed[i], parsed[j]
            gap = (b.parsed_date - a.parsed_date).days

            edges.append(RelationshipEdge(
                source_idx=a.token_idx,
                target_idx=b.token_idx,
                relationship_type="before" if gap > 0 else (
                    "after" if gap < 0 else "same_time"
                ),
                confidence=0.8 if abs(gap) > 0 else 0.5,
                evidence=[f"temporal:gap={gap}d", f"from:{a.raw}", f"to:{b.raw}"],
            ))

    return edges


def enhance_graph_with_temporal(graph: SemanticGraph) -> SemanticGraph:
    """Enhance a semantic graph with temporal reasoning."""
    timeline = build_timeline(graph.tokens)
    temporal_edges = infer_temporal_relationships(timeline)
    graph.relationships.extend(temporal_edges)
    return graph
