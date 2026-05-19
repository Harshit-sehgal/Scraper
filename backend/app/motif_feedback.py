"""
Motif Feedback System — Close the learning loop.

Feeds learned structural patterns (motifs) back into selector discovery
to improve extraction quality over time through autonomous adaptation.

Responsible for:
- Extracting hints from solidified motifs
- Enhancing selector discovery prompts with learned patterns
- Adapting field type hints based on field-specific patterns
"""

from __future__ import annotations

import logging
from typing import Tuple, Dict, List, Optional
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
            Dict mapping field names to hints about their expected patterns/relationships
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
        
        # Fields that frequently appear in solidified motifs are well-structured
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
        valid_motifs = [
            tuple(f for f in motif if f in field_names)
            for motif in solidified_motifs
        ]
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


def get_motif_feedback_engine() -> MotifFeedbackEngine:
    """Get the motif feedback engine instance."""
    return MotifFeedbackEngine()
