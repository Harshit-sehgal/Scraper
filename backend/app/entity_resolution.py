"""
Entity Resolution Engine
=========================
Resolves entity identity: merges aliases, tracks canonical forms,
and maintains persistent entity identity across records.

Core principle: Multiple text mentions can represent the SAME semantic entity.
"Lufthansa", "LH", "Lufthansa Airlines" → same canonical entity.

Identity emerges from:
- Relationship topology (same neighbors = same entity) — PRIMARY
- Graph ownership structure (same owned regions = same entity)
- Semantic role similarity (fills same roles = same entity)
- Text similarity (normalized fuzzy matching) — FALLBACK only

This replaces purely string-centric identity with graph-aware identity.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
import re

from app.semantic_ir import (
    SemanticType, SemanticRecord, SemanticGraph, DatasetIR,
)


@dataclass
class CanonicalEntity:
    """A resolved canonical entity with all its aliases."""
    entity_id: str
    canonical_name: str
    entity_type: SemanticType
    aliases: Set[str] = field(default_factory=set)
    region_ids: List[int] = field(default_factory=list)
    occurrence_count: int = 0
    confidence: float = 0.0
    first_seen: int = 0
    last_seen: int = 0
    # Graph-aware identity signature (relationship topology)
    identity_signature: str = ""


@dataclass
class EntityRegistry:
    """Global registry of all known entities across a dataset.

    Identity is resolved using:
    1. Graph topology (primary) - same relationship neighbors = same entity
    2. Text similarity (fallback) - same normalized name = same entity
    """
    entities: Dict[str, CanonicalEntity] = field(default_factory=dict)
    alias_to_entity: Dict[str, str] = field(default_factory=dict)

    def register(self, name: str, entity_type: SemanticType, position: int = 0,
                 graph: Optional[SemanticGraph] = None) -> str:
        """Register a name occurrence, returning canonical entity_id.

        Uses graph topology as PRIMARY identity signal,
        text similarity as FALLBACK.
        """
        normalized = _normalize_entity_name(name)
        if not normalized:
            return ""

        # Compute graph-aware identity signature if graph provided
        sig = self._compute_identity_signature(name, graph) if graph else ""

        # PRIMARY: Match by graph topology signature
        if sig:
            for eid, entity in self.entities.items():
                if entity.identity_signature and entity.identity_signature == sig:
                    self.alias_to_entity[normalized] = eid
                    entity.aliases.add(normalized)
                    entity.occurrence_count += 1
                    entity.last_seen = max(entity.last_seen, position)
                    return eid

        # SECONDARY: Check known aliases (text similarity)
        if normalized in self.alias_to_entity:
            eid = self.alias_to_entity[normalized]
            self.entities[eid].occurrence_count += 1
            self.entities[eid].last_seen = max(self.entities[eid].last_seen, position)
            return eid

        # TERTIARY: Fuzzy text match fallback
        for eid, entity in self.entities.items():
            if _fuzzy_match(normalized, _normalize_entity_name(entity.canonical_name)):
                self.alias_to_entity[normalized] = eid
                entity.aliases.add(normalized)
                entity.occurrence_count += 1
                entity.last_seen = max(entity.last_seen, position)
                return eid

        # Create new entity
        eid = f"entity_{len(self.entities)}"
        self.entities[eid] = CanonicalEntity(
            entity_id=eid,
            canonical_name=normalized,
            primary_type=SemanticType.ORGANIZATION,
            aliases={normalized},
            occurrence_count=1,
            confidence=0.7,
            first_seen=position,
            last_seen=position,
            identity_signature=sig,
        )
        self.alias_to_entity[normalized] = eid
        return eid

    def _compute_identity_signature(self, name: str, graph: SemanticGraph) -> str:
        """Compute graph-aware identity signature.

        The signature encodes the token's relationship topology:
        - What types of neighbors it connects to
        - What ownership relationships it has
        - What semantic roles it fills

        Two tokens with the SAME signature are likely the SAME entity,
        even if their text is completely different.
        """
        parts = []
        # Find this token in the graph by raw text match
        for i, token in enumerate(graph.tokens):
            if token.raw == name or _normalize_entity_name(token.raw) == _normalize_entity_name(name):
                # Encode neighbor types
                neighbor_types = sorted([
                    graph.tokens[e.target_idx].primary_type.value
                    for e in graph.relationships if e.source_idx == i
                ] + [
                    graph.tokens[e.source_idx].primary_type.value
                    for e in graph.relationships if e.target_idx == i
                ])
                parts.extend(neighbor_types)
                # Encode ownership
                for region in graph.regions:
                    for t in region.tokens:
                        if t is token or t.raw == token.raw:
                            parts.append(f"region:{region.region_type.value}")
                            if region.owned_by is not None:
                                parts.append(f"owned_by:{region.owned_by}")
                            if region.owns:
                                parts.append(f"owns:{len(region.owns)}")
                break
        return ":".join(parts) if parts else ""


    def merge(self, entity_id_a: str, entity_id_b: str):
        """Merge two entities into one (a absorbs b)."""
        if entity_id_a not in self.entities or entity_id_b not in self.entities:
            return
        a, b = self.entities[entity_id_a], self.entities[entity_id_b]
        a.aliases.update(b.aliases)
        a.region_ids.extend(b.region_ids)
        a.occurrence_count += b.occurrence_count
        a.last_seen = max(a.last_seen, b.last_seen)
        a.confidence = max(a.confidence, b.confidence)
        for alias in b.aliases:
            self.alias_to_entity[alias] = entity_id_a
        del self.entities[entity_id_b]

    def get_entity(self, name: str) -> Optional[CanonicalEntity]:
        normalized = _normalize_entity_name(name)
        eid = self.alias_to_entity.get(normalized)
        return self.entities.get(eid) if eid else None

    def resolve_record_entities(self, record: SemanticRecord) -> SemanticRecord:
        """Resolve all entity-type tokens in a record to canonical IDs."""
        for token in record.tokens:
            if token.primary_type in (SemanticType.ORGANIZATION, SemanticType.NAME,
                                      SemanticType.LOCATION, SemanticType.CODE):
                eid = self.register(token.raw, token.primary_type, token.position)
                if eid:
                    token.source_field = eid  # tag with entity ID
                    token.evidence.append(f"entity_resolved:{eid}")
        return record


def _normalize_entity_name(name: str) -> str:
    """Normalize entity name for comparison."""
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9\s]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _fuzzy_match(a: str, b: str) -> bool:
    """Check if two normalized names likely represent the same entity."""
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    # Token overlap
    tokens_a, tokens_b = set(a.split()), set(b.split())
    if len(tokens_a & tokens_b) >= min(len(tokens_a), len(tokens_b)):
        return True
    return False


def resolve_dataset_entities(dataset: DatasetIR) -> DatasetIR:
    """Resolve entities across all records in a dataset."""
    registry = EntityRegistry()
    for record in dataset.records:
        registry.resolve_record_entities(record)

    # Compute confidence from occurrence frequency
    for entity in registry.entities.values():
        freq_bonus = min(entity.occurrence_count / 10, 0.2)
        entity.confidence = min(entity.confidence + freq_bonus, 1.0)

    return dataset
