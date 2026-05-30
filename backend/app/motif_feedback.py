"""
Motif Feedback System — Close the learning loop.

Feeds learned structural patterns (motifs) back into selector discovery
to improve extraction quality over time through adaptive hints.

Responsible for:
- Extracting hints from solidified motifs
- Enhancing selector discovery prompts with learned patterns
- Adapting field type hints based on field-specific patterns
"""

from __future__ import annotations

import logging
from typing import Any, Tuple, Dict, List, Optional
from collections import Counter

from app.models import SchemaField

logger = logging.getLogger(__name__)


class MotifFeedbackEngine:
    """Convert learned motifs into selector discovery hints."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def extract_field_hints_from_motifs(
        solidified_motifs: List[Tuple[str, ...]],
        schema_fields: List[SchemaField],
    ) -> Dict[str, str]:
        """Extract field hints from solidified motifs.

        A solidified motif is a tuple of field names that frequently co-occur.
        Example: ("price", "title", "availability") suggests these fields are often together.

        Args:
            solidified_motifs: List of field name tuples that have been learned as stable patterns
            schema_fields: The target schema fields

        Returns:
            Dict mapping field names to hints about their expected patterns / relationships
        """
        if not solidified_motifs:
            return {}

        field_names = {f.name for f in schema_fields}
        hints = {}

        # Count how often each field appears in solidified motifs
        field_cooccurrence: Counter = Counter()
        for motif in solidified_motifs:
            for field_name in motif:
                if field_name in field_names:
                    field_cooccurrence[field_name] += 1

        # Fields that frequently appear in solidified motifs are
        # well-structured
        for field_name, count in field_cooccurrence.most_common(10):
            if count >= 2:  # At least 2 solidified patterns
                hints[field_name] = (
                    f"HINT: This field is part of a stable structural pattern "
                    f"(appeared in {count} solidified motifs). It likely has consistent selectors across the site."
                )

        return hints

    @staticmethod
    def build_motif_context(
        solidified_motifs: List[Tuple[str, ...]],
        schema_fields: List[SchemaField],
    ) -> Optional[str]:
        """Build a context string about learned patterns for the selector discovery prompt.

        Args:
            solidified_motifs: Learned field groupings
            schema_fields: Target schema

        Returns:
            Context string to prepend to selector discovery prompt, or None if no motifs
        """
        if not solidified_motifs:
            return None

        field_names = {f.name for f in schema_fields}

        # Filter motifs to only include fields in our schema
        valid_motifs = [tuple(f for f in motif if f in field_names) for motif in solidified_motifs]
        valid_motifs = [m for m in valid_motifs if len(m) > 0]

        if not valid_motifs:
            return None

        motif_str_parts = []
        for motif in valid_motifs[:5]:  # Limit to top 5 for brevity
            fields_str = ", ".join([f'"{f}"' for f in motif])
            motif_str_parts.append(f"  - {fields_str}")

        context = f"""LEARNED STRUCTURAL PATTERNS (from previous successful extractions):
The following field groups have been found together in stable patterns:
{chr(10).join(motif_str_parts)}

Use these patterns as hints: if you find one field from a group, look nearby for the others.
This can help with relative selector selection (e.g., if you find the price, the title might be a sibling or parent).
"""
        return context

    @staticmethod
    def extract_motifs_from_results(
        results: List[Dict[str, Any]],
        schema_fields: List[SchemaField],
        min_cooccurrence: int = 2,
    ) -> List[Tuple[str, ...]]:
        """Extract field co-occurrence motifs from extraction results.

        Scans results for fields that frequently appear together and returns
        them as solidified motifs that can be fed back into selector discovery.

        This closes the adaptive feedback loop:
          extract → find co-occurring fields → solidify motifs → feed back → better extractions

        Args:
            results: List of extracted record dicts
            schema_fields: The target schema fields
            min_cooccurrence: Minimum times a field pair must appear together

        Returns:
            List of field name tuples representing solidified motifs
        """
        if not results:
            return []

        from collections import Counter

        # Track which fields appear together per record
        field_pairs: Counter = Counter()
        for record in results:
            # Find non-empty fields in this record
            present_fields = []
            for field in schema_fields:
                val = record.get(field.name)
                if val is not None and val != "" and val != []:
                    present_fields.append(field.name)

            # Record all field pairs as co-occurrences
            if len(present_fields) >= 2:
                for i in range(len(present_fields)):
                    for j in range(i + 1, len(present_fields)):
                        pair = tuple(sorted([present_fields[i], present_fields[j]]))
                        field_pairs[pair] += 1

        # Group field pairs into motifs: fields that co-occur frequently
        # Fields that share many connections form a motif
        field_connections: Dict[str, set] = {}
        for (f1, f2), count in field_pairs.items():
            if count >= min_cooccurrence:
                field_connections.setdefault(f1, set()).add(f2)
                field_connections.setdefault(f2, set()).add(f1)

        # Build motifs from connected components (greedy clustering)
        assigned = set()
        motifs: List[Tuple[str, ...]] = []

        for fname, neighbors in sorted(field_connections.items(), key=lambda x: -len(x[1])):
            if fname in assigned:
                continue
            # Start a new motif with this field and its strongly connected
            # neighbors
            motif_fields = {fname}
            for neighbor in neighbors:
                if neighbor not in assigned:
                    # Check if this neighbor is also connected to other motif
                    # members
                    neighbor_neighbors = field_connections.get(neighbor, set())
                    shared = motif_fields & neighbor_neighbors
                    if len(shared) >= 1 or len(motif_fields) == 1:
                        motif_fields.add(neighbor)

            if len(motif_fields) >= 2:
                motif = tuple(sorted(motif_fields))
                motifs.append(motif)
                assigned.update(motif_fields)

        if motifs:
            logger.info(
                "Extracted %d motifs from %d results: %s",
                len(motifs),
                len(results),
                ["(" + ", ".join(m) + ")" for m in motifs],
            )

        return motifs


def get_motif_feedback_engine() -> MotifFeedbackEngine:
    """Get the motif feedback engine instance."""
    return MotifFeedbackEngine()
