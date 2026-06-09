"""Semantic Intermediate Representation (IR).
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

from app.models import FieldType


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
    # Real data record (flight, hotel, product, etc.)
    ENTITY = "entity"
    FILTER = "filter"  # Filter / pagination control
    NAVIGATION = "navigation"  # Navigation element
    METADATA = "metadata"  # Page metadata
    CONTROL = "control"  # UI control (button, form)
    SUMMARY = "summary"  # Aggregate / summary row
    ADVERTISEMENT = "advertisement"
    UI_COMPONENT = "ui_component"
    UNKNOWN = "unknown"


class RegionType(Enum):
    """Universal region types - NOT domain-specific."""

    ENTITY_NAME = "entity_name"  # Primary entity name / identifier
    PRICE_REGION = "price_region"  # Price-related tokens
    DATE_REGION = "date_region"  # Date / time-related tokens
    LOCATION_REGION = "location_region"  # Location identifiers (codes, names)
    QUANTIFIER = "quantifier"  # Numeric modifiers (count, quantity)
    DESCRIPTOR = "descriptor"  # Descriptive / adjective text
    IDENTIFIER_REGION = "identifier_region"  # Codes, SKUs, IDs
    RATING_REGION = "rating_region"  # Rating / score tokens
    CONTACT_REGION = "contact_region"  # Phone / email / contact
    DURATION_REGION = "duration_region"  # Time duration
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class Span:
    """Character span in source text."""

    start: int
    end: int

    def overlaps_with(self, other: Span) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: Span) -> bool:
        return self.start <= other.start and other.end <= self.end

    def distance_to(self, other: Span) -> int:
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

    # Semantic Embedding: 16-dimensional manifold point.
    # Replaces individual type_facet fields for unified geometric meaning.
    embedding: list[float] = field(default_factory=lambda: [0.5] * 16)

    # Classification: primary type + ambiguity distribution
    primary_type: SemanticType = SemanticType.TEXT
    type_distribution: dict[SemanticType, float] = field(default_factory=dict)

    # Provenance
    extraction_method: str = ""  # "pattern", "split", "whitespace", "dom"
    extraction_pass: int = 0
    source_field: str = ""  # which record field this came from

    # Evidence and traceability
    evidence: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    # Neighbors (populated by relationship_inference)
    left_neighbor: SemanticToken | None = None
    right_neighbor: SemanticToken | None = None
    neighborhood: list[SemanticToken] = field(default_factory=list)

    # DOM context
    dom_path: str = ""
    dom_depth: int = 0
    tag_name: str = ""
    css_classes: list[str] = field(default_factory=list)


@dataclass
class RelationshipEdge:
    """A scored relationship between two tokens."""

    source_idx: int
    target_idx: int
    # "adjacent", "paired_codes", "date_range", "price_modifier", "same_group"
    relationship_type: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)


@dataclass
class SemanticGroup:
    """A group of tokens that form a coherent semantic unit."""

    tokens: list[SemanticToken]
    cohesion_score: float = 0.0
    primary_type: SemanticType | None = None
    relationships: list[RelationshipEdge] = field(default_factory=list)
    structural_signature: tuple[str, ...] = field(default_factory=tuple)
    dom_region: str = ""


@dataclass
class SemanticRecord:
    """Complete semantic representation of one extracted record."""

    tokens: list[SemanticToken]
    groups: list[SemanticRegion] = field(default_factory=list)
    relationships: list[RelationshipEdge] = field(default_factory=list)
    structural_signature: tuple[str, ...] = field(default_factory=tuple)

    # Confidence at multiple levels
    token_confidence: float = 0.0
    group_cohesion: float = 0.0
    structural_confidence: float = 0.0
    overall_confidence: float = 0.0

    # Noise classification
    is_noise: bool = False
    noise_confidence: float = 0.0
    noise_evidence: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    # Original data context
    source_text: str = ""
    source_field: str = ""

    # Dataset-level tracking
    row_index: int = -1

    # Mapped output (populated by semantic_mapper)
    mapped_fields: dict[str, str] = field(default_factory=dict)
    mapped_confidences: dict[str, float] = field(default_factory=dict)
    is_unstable: bool = False  # Thermodynamic reasoning flag (Phase 18)

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
    tokens: list[SemanticToken]
    start_position: int
    end_position: int

    # Confidence
    confidence: float = 0.0

    # Relationships to other regions
    relationships: list[RelationshipEdge] = field(default_factory=list)

    # Ownership
    owned_by: int | None = None  # region_id of owner
    owns: list[int] = field(default_factory=list)  # region_ids of owned
    ownership_confidence: float = 0.0

    # Structural
    structural_signature: tuple[str, ...] = field(default_factory=tuple)

    # Evidence
    evidence: list[str] = field(default_factory=list)


@dataclass
class AffinityEdge:
    """Soft cohesion between tokens (e.g. proximity-based contextual affinity)."""

    source_id: int
    target_id: int
    strength: float = 0.5
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)


@dataclass
class OwnershipEdge:
    """A scored ownership relationship between two entities.

    Example: price (owned_entity) belongs_to flight (owner_region)
    """

    owner_region_id: int
    owned_region_id: int
    ownership_type: str  # "belongs_to", "describes", "modifies", "quantifies", "identifies"
    confidence: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class ExclusionEdge:
    """A scored exclusion relationship between two nodes / regions.

    Exclusion edges propagate conflict pressure through the topology.
    Unified with RelationshipEdge via confidence / strength duality.
    """

    source_id: int
    target_id: int
    strength: float = 1.0
    confidence: float = 1.0
    evidence: list[str] = field(default_factory=list)

    def __init__(
        self,
        source_id: int,
        target_id: int,
        strength: float = 1.0,
        confidence: float | None = None,
        evidence: list[str] | None = None,
    ) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.strength = strength
        self.confidence = confidence if confidence is not None else strength
        self.evidence = evidence or []


@dataclass
class SemanticGraph:
    """Complete semantic graph for a dataset row or page.

    The graph ITSELF is the reasoning substrate.
    Meaning emerges from graph structure, not individual heuristics.
    """

    regions: list[SemanticRegion]
    tokens: list[SemanticToken] = field(default_factory=list)
    relationships: list[RelationshipEdge] = field(default_factory=list)
    ownership_edges: list[OwnershipEdge] = field(default_factory=list)
    exclusion_edges: list[ExclusionEdge] = field(default_factory=list)
    affinity_edges: list[AffinityEdge] = field(default_factory=list)

    # Global properties & Equilibrium metrics
    coherence_score: float = 0.0
    semantic_energy: float = 5.0
    uncertainty_field: dict[int, float] = field(default_factory=dict)  # node_id -> uncertainty

    # Sub-graphs
    sub_graphs: list[SemanticGraph] = field(default_factory=list)

    def get_region(self, region_id: int) -> SemanticRegion | None:
        for r in self.regions:
            if r.region_id == region_id:
                return r
        return None

    def get_owned_regions(self, region_id: int) -> list[SemanticRegion]:
        owner = self.get_region(region_id)
        if not owner:
            return []
        return [r for r in self.regions if r.region_id in owner.owns]

    def get_owner(self, region_id: int) -> SemanticRegion | None:
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

    role_name: str  # "price", "date", "name", "location", "code"
    field_type: SemanticType  # Expected type for this role
    required: bool = False
    # How exclusive this role is (1.0 = strictly one candidate)
    exclusivity: float = 1.0
    filled_by: str | None = None  # candidate key
    fill_confidence: float = 0.0


@dataclass
class AllocationGraph:
    """Global allocation graph for semantic role assignment.

    Candidates compete for roles. The optimal assignment maximizes
    global coherence while satisfying exclusivity constraints.
    """

    candidates: dict[str, SemanticToken] = field(default_factory=dict)  # key → token
    roles: dict[str, SemanticRole] = field(default_factory=dict)  # role_name → role
    compatibility: dict[tuple[str, str], float] = field(default_factory=dict)  # (candidate, role) → score
    exclusivity_edges: list[tuple[str, str]] = field(default_factory=list)  # mutually exclusive candidates
    field_conflicts: list[dict] = field(default_factory=list)
    coherence_score: float = 0.0
    is_unstable: bool = False  # Thermodynamic reasoning flag (Phase 18)
    assignment_history: list[dict] = field(default_factory=list)


@dataclass
class DatasetIR:
    """Complete IR for a dataset (multiple records from one page)."""

    records: list[SemanticRecord]
    structure_type: str = ""  # "table", "cards", "list", "mixed"
    structural_memory: dict[tuple[str, ...], int] = field(default_factory=dict)  # pattern -> count
    global_coherence: float = 0.0

    def add_record(self, record: SemanticRecord) -> None:
        self.records.append(record)
        sig = record.structural_signature
        self.structural_memory[sig] = self.structural_memory.get(sig, 0) + 1


def create_token(
    raw: str,
    span_start: int,
    span_end: int,
    position: int,
    primary_type: SemanticType = SemanticType.TEXT,
    confidence: float = 0.85,
    extraction_method: str = "pattern",
    source_field: str = "",  # noqa: ARG001, RUF100
) -> SemanticToken:
    """Factory for creating SemanticToken with sensible defaults.

    Also populates the 16-dimensional embedding from the primary_type.
    """
    source = primary_type.value[:10].lower() if hasattr(primary_type, "value") else ""
    tok = SemanticToken(
        raw=raw,
        normalized=raw.strip(),
        span=Span(span_start, span_end),
        position=position,
        primary_type=primary_type,
        type_distribution={primary_type: confidence},
        extraction_method=extraction_method,
        source_field=source,
        evidence=[f"created:{extraction_method}"],
    )
    populate_type_vector(tok, primary_type)
    return tok


def populate_type_vector(token: SemanticToken, primary_type: SemanticType, graph: SemanticGraph | None = None) -> None:  # noqa: ARG001, RUF100
    """Populate the 16-dimensional embedding from graph context."""
    if graph:
        from app.semantic_inference_engine import RelationshipEmbeddingSpace

        emb_space = RelationshipEmbeddingSpace()
        for i, t in enumerate(graph.tokens):
            if t is token or t.raw == token.raw:
                token.embedding = emb_space.compute_embedding(i, graph)
                return

    # No graph available: use uniform defaults (entropy anchored)
    token.embedding = [0.5] * 16


def compute_type_signature(tokens: list[SemanticToken]) -> tuple[str, ...]:
    """Compute the type signature of a token sequence."""
    return tuple(t.primary_type.value for t in tokens)


def semantic_to_field_type(st: SemanticType) -> FieldType:
    """Convert a SemanticType to its nearest FieldType equivalent."""
    _map = {
        SemanticType.PRICE: FieldType.CURRENCY,
        SemanticType.DATE: FieldType.DATE,
        SemanticType.PHONE: FieldType.PHONE,
        SemanticType.EMAIL: FieldType.EMAIL,
        SemanticType.URL: FieldType.URL,
        SemanticType.LOCATION: FieldType.LOCATION,
        SemanticType.CODE: FieldType.CODE,
        SemanticType.RATING: FieldType.RATING,
        SemanticType.NUMBER: FieldType.NUMBER,
        SemanticType.TEXT: FieldType.STRING,
        SemanticType.DURATION: FieldType.STRING,
        SemanticType.ORGANIZATION: FieldType.STRING,
        SemanticType.NAME: FieldType.STRING,
        SemanticType.IDENTIFIER: FieldType.CODE,
    }
    return _map.get(st, FieldType.STRING)


def field_type_to_semantic(ft: FieldType) -> SemanticType:
    """Convert a FieldType to its nearest SemanticType equivalent."""
    _map = {
        FieldType.STRING: SemanticType.TEXT,
        FieldType.INTEGER: SemanticType.NUMBER,
        FieldType.FLOAT: SemanticType.NUMBER,
        FieldType.BOOLEAN: SemanticType.TEXT,
        FieldType.EMAIL: SemanticType.EMAIL,
        FieldType.URL: SemanticType.URL,
        FieldType.PHONE: SemanticType.PHONE,
        FieldType.LOCATION: SemanticType.LOCATION,
        FieldType.DATE: SemanticType.DATE,
        FieldType.LIST_STRING: SemanticType.TEXT,
        FieldType.CURRENCY: SemanticType.PRICE,
        FieldType.PERCENTAGE: SemanticType.NUMBER,
        FieldType.CODE: SemanticType.CODE,
        FieldType.RATING: SemanticType.RATING,
        FieldType.NUMBER: SemanticType.NUMBER,
    }
    return _map.get(ft, SemanticType.TEXT)
