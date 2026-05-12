"""
Semantic Intermediate Representation (IR)
============================================
Single source of truth for ALL semantic data in the extraction pipeline.

ALL stages operate on IR objects, NOT raw strings.
This prevents direct regex-to-schema coupling and enables
probabilistic reasoning at every level.

Core principle: Everything is a relationship, nothing is an island.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class SemanticType(Enum):
    TEXT = "text"
    PRICE = "price"
    DATE = "date"
    DURATION = "duration"
    CODE = "code"
    RATING = "rating"
    NUMBER = "number"
    PHONE = "phone"
    EMAIL = "email"
    URL = "url"
    LOCATION = "location"
    ORGANIZATION = "organization"
    NAME = "name"
    IDENTIFIER = "identifier"


class RecordType(Enum):
    ENTITY = "entity"           # Real data record (flight, hotel, product, etc.)
    FILTER = "filter"           # Filter/pagination control
    NAVIGATION = "navigation"   # Navigation element
    METADATA = "metadata"       # Page metadata
    CONTROL = "control"          # UI control (button, form)
    SUMMARY = "summary"         # Aggregate/summary row
    ADVERTISEMENT = "advertisement"
    UI_COMPONENT = "ui_component"
    UNKNOWN = "unknown"


class RegionType(Enum):
    """Universal region types - NOT domain-specific."""
    ENTITY_NAME = "entity_name"         # Primary entity name/identifier
    PRICE_REGION = "price_region"       # Price-related tokens
    DATE_REGION = "date_region"         # Date/time-related tokens
    LOCATION_REGION = "location_region" # Location identifiers (codes, names)
    QUANTIFIER = "quantifier"           # Numeric modifiers (count, quantity, stops)
    DESCRIPTOR = "descriptor"           # Descriptive/adjective text
    IDENTIFIER_REGION = "identifier_region"  # Codes, SKUs, IDs
    RATING_REGION = "rating_region"     # Rating/score tokens
    CONTACT_REGION = "contact_region"   # Phone/email/contact
    DURATION_REGION = "duration_region" # Time duration
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class Span:
    """Character span in source text."""
    start: int
    end: int

    def overlaps_with(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: "Span") -> bool:
        return self.start <= other.start and other.end <= self.end

    def distance_to(self, other: "Span") -> int:
        if self.overlaps_with(other):
            return 0
        if self.end <= other.start:
            return other.start - self.end
        return self.start - other.end

    def __hash__(self):
        return hash((self.start, self.end))


@dataclass
class SemanticToken:
    """The fundamental unit of semantic information.

    All extraction, classification, and mapping operates on these.
    Regex only PROPOSES tokens; meaning is inferred from context.
    """
    raw: str
    normalized: str
    span: Span
    position: int  # ordinal position in source

    # Multi-dimensional type vector (replaces single primary_type for rich semantics)
    # Each dimension represents a different semantic facet:
    # ALL start at 0.5 (maximum entropy, no symbolic priors).
    # Differentiation emerges from graph behavior.
    type_value: float = 0.5
    type_entity: float = 0.5
    type_location: float = 0.5
    type_temporal: float = 0.5
    type_identifier: float = 0.5
    type_quantity: float = 0.5
    type_quality: float = 0.5
    type_contact: float = 0.5
    type_text: float = 0.5

    # Classification: primary type + ambiguity distribution
    primary_type: SemanticType = SemanticType.TEXT
    type_distribution: Dict[SemanticType, float] = field(default_factory=dict)

    # Provenance
    extraction_method: str = ""  # "pattern", "split", "whitespace", "dom"
    extraction_pass: int = 0
    source_field: str = ""  # which record field this came from

    # Evidence and traceability
    evidence: List[str] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)

    # Neighbors (populated by relationship_inference)
    left_neighbor: Optional["SemanticToken"] = None
    right_neighbor: Optional["SemanticToken"] = None
    neighborhood: List["SemanticToken"] = field(default_factory=list)

    # DOM context
    dom_path: str = ""
    dom_depth: int = 0
    tag_name: str = ""
    css_classes: List[str] = field(default_factory=list)


@dataclass
class RelationshipEdge:
    """A scored relationship between two tokens."""
    source_idx: int
    target_idx: int
    relationship_type: str  # "adjacent", "paired_codes", "date_range", "price_modifier", "same_group"
    confidence: float
    evidence: List[str] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)


@dataclass
class SemanticGroup:
    """A group of tokens that form a coherent semantic unit."""
    tokens: List[SemanticToken]
    cohesion_score: float = 0.0
    primary_type: Optional[SemanticType] = None
    relationships: List[RelationshipEdge] = field(default_factory=list)
    structural_signature: Tuple[str, ...] = field(default_factory=tuple)
    dom_region: str = ""


@dataclass
class SemanticRecord:
    """Complete semantic representation of one extracted record."""
    tokens: List[SemanticToken]
    groups: list[SemanticRegion] = field(default_factory=list)
    relationships: List[RelationshipEdge] = field(default_factory=list)
    structural_signature: Tuple[str, ...] = field(default_factory=tuple)

    # Confidence at multiple levels
    token_confidence: float = 0.0
    group_cohesion: float = 0.0
    structural_confidence: float = 0.0
    overall_confidence: float = 0.0

    # Noise classification
    is_noise: bool = False
    noise_confidence: float = 0.0
    noise_evidence: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)

    # Original data context
    source_text: str = ""
    source_field: str = ""

    # Dataset-level tracking
    row_index: int = -1

    # Mapped output (populated by semantic_mapper)
    mapped_fields: Dict[str, str] = field(default_factory=dict)
    mapped_confidences: Dict[str, float] = field(default_factory=dict)

    # Record type classification
    record_type: RecordType = RecordType.UNKNOWN
    record_type_confidence: float = 0.0


@dataclass
class SemanticRegion:
    """A semantically coherent region within a record.

    Groups related tokens into a meaningful unit.
    Meaning exists primarily at region level, not token level.
    """
    region_id: int
    region_type: RegionType
    tokens: List[SemanticToken]
    start_position: int
    end_position: int

    # Confidence
    confidence: float = 0.0

    # Relationships to other regions
    relationships: List["RelationshipEdge"] = field(default_factory=list)

    # Ownership
    owned_by: Optional[int] = None  # region_id of owner
    owns: List[int] = field(default_factory=list)  # region_ids of owned
    ownership_confidence: float = 0.0

    # Structural
    structural_signature: Tuple[str, ...] = field(default_factory=tuple)

    # Evidence
    evidence: List[str] = field(default_factory=list)


@dataclass
class OwnershipEdge:
    """A scored ownership relationship between two entities.

    Example: price (owned_entity) belongs_to flight (owner_region)
    """
    owner_region_id: int
    owned_region_id: int
    ownership_type: str  # "belongs_to", "describes", "modifies", "quantifies", "identifies"
    confidence: float
    evidence: List[str] = field(default_factory=list)


@dataclass
class SemanticGraph:
    """Complete semantic graph for a dataset row or page.

    The graph ITSELF is the reasoning substrate.
    Meaning emerges from graph structure, not individual heuristics.
    """
    regions: List[SemanticRegion]
    tokens: List[SemanticToken] = field(default_factory=list)
    relationships: List[RelationshipEdge] = field(default_factory=list)
    ownership_edges: List[OwnershipEdge] = field(default_factory=list)

    # Global properties
    coherence_score: float = 0.0
    contradictions: List[Any] = field(default_factory=list)
    contradiction_score: float = 0.0
    has_contradictions: bool = False

    # Sub-graphs
    sub_graphs: List["SemanticGraph"] = field(default_factory=list)

    def get_region(self, region_id: int) -> Optional[SemanticRegion]:
        for r in self.regions:
            if r.region_id == region_id:
                return r
        return None

    def get_owned_regions(self, region_id: int) -> List[SemanticRegion]:
        owner = self.get_region(region_id)
        if not owner:
            return []
        return [r for r in self.regions if r.region_id in owner.owns]

    def get_owner(self, region_id: int) -> Optional[SemanticRegion]:
        region = self.get_region(region_id)
        if not region or region.owned_by is None:
            return None
        return self.get_region(region.owned_by)


@dataclass
class SemanticRole:
    """A semantic role that a candidate can fill.

    Roles compete globally - each candidate can fill at most one role,
    and each role can be filled by at most one candidate.
    """
    role_name: str           # "origin", "destination", "price", "date", "name", "stops"
    field_type: SemanticType # Expected type for this role
    required: bool = False
    exclusivity: float = 1.0  # How exclusive this role is (1.0 = strictly one candidate)
    filled_by: Optional[str] = None  # candidate key
    fill_confidence: float = 0.0


@dataclass
class AllocationGraph:
    """Global allocation graph for semantic role assignment.

    Candidates compete for roles. The optimal assignment maximizes
    global coherence while satisfying exclusivity constraints.
    """
    candidates: Dict[str, SemanticToken] = field(default_factory=dict)  # key → token
    roles: Dict[str, SemanticRole] = field(default_factory=dict)  # role_name → role
    compatibility: Dict[Tuple[str, str], float] = field(default_factory=dict)  # (candidate, role) → score
    exclusivity_edges: List[Tuple[str, str]] = field(default_factory=list)  # mutually exclusive candidates
    coherence_score: float = 0.0
    assignment_history: List[Dict] = field(default_factory=list)
    role_order: List[str] = field(default_factory=list)  # schema field order for positional signals


@dataclass
class DatasetIR:
    """Complete IR for a dataset (multiple records from one page)."""
    records: List[SemanticRecord]
    structure_type: str = ""  # "table", "cards", "list", "mixed"
    structural_memory: Dict[Tuple[str, ...], int] = field(default_factory=dict)  # pattern -> count
    global_coherence: float = 0.0

    def add_record(self, record: SemanticRecord):
        self.records.append(record)
        sig = record.structural_signature
        self.structural_memory[sig] = self.structural_memory.get(sig, 0) + 1


def create_token(raw: str, span_start: int, span_end: int, position: int,
                 primary_type: SemanticType = SemanticType.TEXT,
                 extraction_method: str = "pattern") -> SemanticToken:
    """Factory for creating SemanticToken with sensible defaults.

    Also populates the multi-dimensional type_vector from the primary_type.
    """
    tok = SemanticToken(
        raw=raw,
        normalized=raw.strip(),
        span=Span(span_start, span_end),
        position=position,
        primary_type=primary_type,
        type_distribution={primary_type: 0.85},
        extraction_method=extraction_method,
        evidence=[f"created:{extraction_method}"],
    )
    populate_type_vector(tok, primary_type)
    return tok


def populate_type_vector(token: SemanticToken, primary_type: SemanticType,
                          graph: Optional[SemanticGraph] = None):
    """Populate the multi-dimensional type_vector from graph context.

    When a graph is available, type_vector is derived from:
    - Relationship types the token participates in
    - Neighborhood token types
    - Ownership structure

    When no graph is available, uses uniform defaults (no symbolic priors).

    This replaces the hardcoded mapping dict with emergent graph-derived semantics.
    """
    if graph:
        # Derive type_vector from graph neighborhood
        from app.semantic_inference_engine import RelationalEmbeddingSpace
        emb_space = RelationalEmbeddingSpace(dimension=16)
        # Find the token in the graph
        for i, t in enumerate(graph.tokens):
            if t is token or t.raw == token.raw:
                emb = emb_space.compute_embedding(i, graph)
                # Map embedding positions to type_vector fields
                token.type_entity = emb[0]
                token.type_value = emb[1]
                token.type_location = emb[2]
                token.type_temporal = emb[3]
                token.type_identifier = emb[4]
                token.type_quantity = emb[5]
                token.type_quality = emb[6]
                token.type_contact = emb[7]
                token.type_text = emb[8]
                return
    
    # No graph available: use uniform defaults (emergent, no symbolic priors)
    # All dimensions start at same value - differentiation comes from graph behavior
    uniform = 0.5
    token.type_entity = uniform
    token.type_value = uniform
    token.type_location = uniform
    token.type_temporal = uniform
    token.type_identifier = uniform
    token.type_quantity = uniform
    token.type_quality = uniform
    token.type_contact = uniform
    token.type_text = uniform


def compute_type_signature(tokens: List[SemanticToken]) -> Tuple[str, ...]:
    """Compute the type signature of a token sequence."""
    return tuple(t.primary_type.value for t in tokens)
