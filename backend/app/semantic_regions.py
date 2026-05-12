"""
Semantic Region Decomposition Engine
======================================
Decomposes token sequences into semantically coherent regions.

Core principle: meaning exists primarily at REGION level, not token level.
A region is a group of tokens that form a meaningful semantic unit.

Example:
  "Lufthansa" + "LON" + "22-05-2026" + "1 Stop" + "PAR"
  → [entity_name] [location] [date] [quantifier] [location]
"""

from typing import List, Dict

from app.semantic_ir import (
    SemanticToken, SemanticType, RegionType, SemanticRegion,
    SemanticRecord,
)


# Token type → region type mapping (universal, NOT domain-specific)
TYPE_TO_REGION: Dict[SemanticType, RegionType] = {
    SemanticType.PRICE: RegionType.PRICE_REGION,
    SemanticType.DATE: RegionType.DATE_REGION,
    SemanticType.DURATION: RegionType.DURATION_REGION,
    SemanticType.RATING: RegionType.RATING_REGION,
    SemanticType.PHONE: RegionType.CONTACT_REGION,
    SemanticType.EMAIL: RegionType.CONTACT_REGION,
    SemanticType.CODE: RegionType.IDENTIFIER_REGION,
    SemanticType.LOCATION: RegionType.LOCATION_REGION,
    SemanticType.ORGANIZATION: RegionType.ENTITY_NAME,
    SemanticType.NAME: RegionType.ENTITY_NAME,
    SemanticType.NUMBER: RegionType.QUANTIFIER,
}


def detect_semantic_regions(tokens: List[SemanticToken]) -> List[SemanticRegion]:
    """Decompose a token sequence into semantic regions.

    Uses:
    1. Token type transitions (type change = region boundary)
    2. Proximity (gap > threshold = region boundary)
    3. Same-type grouping (consecutive same type = same region)
    """
    if not tokens:
        return []

    regions: List[SemanticRegion] = []
    region_id = 0

    current_tokens: List[SemanticToken] = [tokens[0]]
    current_type = tokens[0].primary_type

    for i in range(1, len(tokens)):
        token = tokens[i]
        gap = token.span.distance_to(tokens[i - 1].span)

        # Check for region boundary
        is_boundary = _is_region_boundary(current_type, token.primary_type, gap, current_tokens[-1], token)

        if is_boundary:
            # Close current region
            region = _build_region(region_id, current_tokens, current_type)
            regions.append(region)
            region_id += 1
            current_tokens = [token]
            current_type = token.primary_type
        else:
            current_tokens.append(token)

    # Close final region
    if current_tokens:
        region = _build_region(region_id, current_tokens, current_type)
        regions.append(region)

    return regions


def _is_region_boundary(
    prev_type: SemanticType,
    curr_type: SemanticType,
    gap: int,
    prev_token: SemanticToken,
    curr_token: SemanticToken,
) -> bool:
    """Determine if there's a region boundary between two tokens.

    Boundaries occur at:
    1. Type transitions (code → date, price → text)
    2. Large gaps (>= 3 chars with no meaningful connection)
    3. Semantic incompatibility (organization → number with no modifier)
    """
    # Type transition = boundary
    if prev_type != curr_type:
        return True

    # Same type but large gap = boundary
    if gap >= 5:
        return True

    return False


def _build_region(
    region_id: int,
    tokens: List[SemanticToken],
    primary_type: SemanticType,
) -> SemanticRegion:
    """Build a SemanticRegion from a group of tokens."""
    region_type = TYPE_TO_REGION.get(primary_type, RegionType.UNKNOWN)

    # For text tokens, try to classify as entity name
    if primary_type == SemanticType.TEXT:
        combined = " ".join(t.raw for t in tokens)
        # Uppercase-starting text is likely an entity name
        if combined and combined[0].isupper():
            region_type = RegionType.ENTITY_NAME

    start_pos = tokens[0].position
    end_pos = tokens[-1].position
    signature = tuple(t.primary_type.value for t in tokens)

    # Confidence based on type-region match
    confidence = 0.9 if region_type != RegionType.UNKNOWN else 0.4

    return SemanticRegion(
        region_id=region_id,
        region_type=region_type,
        tokens=tokens,
        start_position=start_pos,
        end_position=end_pos,
        confidence=confidence,
        structural_signature=signature,
        evidence=[f"region:{region_type.value}:{len(tokens)}_tokens"],
    )


def compute_region_cohesion(region: SemanticRegion) -> float:
    """Compute how internally cohesive a region is.

    Factors:
    - Type consistency (all same type = high cohesion)
    - Token proximity (small gaps = high cohesion)
    - Length appropriateness (region has right size)
    """
    if not region.tokens:
        return 0.0

    # Type consistency
    types = set(t.primary_type for t in region.tokens)
    type_consistency = 1.0 if len(types) == 1 else 0.5

    # Proximity
    gaps = []
    for i in range(1, len(region.tokens)):
        gap = region.tokens[i].span.distance_to(region.tokens[i - 1].span)
        gaps.append(gap)
    avg_gap = sum(gaps) / len(gaps) if gaps else 0
    proximity = 1.0 - min(avg_gap / 10, 1.0)

    # Size appropriateness (1-5 tokens is ideal)
    size_score = 1.0 - abs(len(region.tokens) - 3) / 10

    cohesion = (type_consistency * 0.4) + (proximity * 0.3) + (size_score * 0.3)
    return min(cohesion, 1.0)


def build_region_hierarchy(regions: List[SemanticRegion]) -> List[SemanticRegion]:
    """Build region hierarchy by inferring parent-child relationships.

    Rules (universal, not domain-specific):
    - Entity names own nearby price/date/quantifier regions
    - Identifiers own nearby price regions
    - Descriptors modify the nearest entity/identifier region
    """
    if not regions:
        return regions

    # Find primary entity region (likely the first name/identifier region)
    primary_regions = [
        r for r in regions
        if r.region_type in (RegionType.ENTITY_NAME, RegionType.IDENTIFIER_REGION)
    ]
    if not primary_regions:
        return regions

    primary = primary_regions[0]
    primary_id = primary.region_id

    for region in regions:
        if region.region_id == primary_id:
            continue
        # Other regions are owned by the primary entity
        gap = region.start_position - primary.end_position if region.start_position > primary.end_position else primary.start_position - region.end_position

        if gap <= 10:
            region.owned_by = primary_id
            primary.owns.append(region.region_id)
            region.ownership_confidence = 0.7
            region.evidence.append(f"owned_by_primary:{primary_id}")

    return regions


def decompose_record(record: SemanticRecord) -> List[SemanticRegion]:
    """Full region decomposition for a record."""
    regions = detect_semantic_regions(record.tokens)
    regions = build_region_hierarchy(regions)
    record.groups = regions  # attach regions to record
    return regions
