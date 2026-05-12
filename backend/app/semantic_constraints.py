"""
Universal Semantic Constraints Engine
========================================
Defines universal constraints that any valid semantic interpretation must satisfy.

These are NOT domain-specific rules.
They are universal semantic invariants that hold across ALL domains.

Examples:
- A price value cannot be a date value simultaneously (in most contexts)
- A single code cannot be both origin and destination
- Temporal ordering must be consistent
- Ownership must be acyclic
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field

from app.semantic_ir import (
    SemanticType, SemanticRecord, SemanticGraph,
    AllocationGraph,
)
from app.semantic_allocation_engine import ROLE_EXCLUSIVITY


@dataclass
class ConstraintViolation:
    """A detected constraint violation."""
    constraint: str
    description: str
    severity: float  # 0.0-1.0
    evidence: List[str] = field(default_factory=list)


# Universal constraints (NOT domain-specific)
# Each is a function (graph) → List[ConstraintViolation]
CONSTRAINT_REGISTRY: List[Dict] = []


def check_exclusivity_constraints(graph: AllocationGraph) -> List[ConstraintViolation]:
    """Check that no candidate fills two mutually exclusive roles."""
    violations: List[ConstraintViolation] = []

    filled = {r.role_name: r.filled_by for r in graph.roles.values() if r.filled_by}
    for role_a, role_b in ROLE_EXCLUSIVITY:
        if role_a in filled and role_b in filled:
            if filled[role_a] == filled[role_b]:
                violations.append(ConstraintViolation(
                    constraint="role_exclusivity",
                    description=f"'{filled[role_a]}' fills both '{role_a}' and '{role_b}'",
                    severity=0.8,
                    evidence=[f"exclusivity_violation:{role_a}:{role_b}"],
                ))

    return violations


def check_type_consistency(record: SemanticRecord) -> List[ConstraintViolation]:
    """Check that mapped value types match their field expectations."""
    violations: List[ConstraintViolation] = []

    type_expectations = {
        "price": SemanticType.PRICE,
        "date": SemanticType.DATE,
        "rating": SemanticType.RATING,
        "duration": SemanticType.DURATION,
        "phone": SemanticType.PHONE,
        "email": SemanticType.EMAIL,
    }

    for field_name, field_value in record.mapped_fields.items():
        expected_type = type_expectations.get(field_name)
        if expected_type is None:
            continue

        # Find the token that was mapped
        token = next((t for t in record.tokens if t.raw == field_value), None)
        if token and token.primary_type != expected_type:
            violations.append(ConstraintViolation(
                constraint="type_consistency",
                description=f"'{field_value}' (type={token.primary_type.value}) "
                            f"assigned to '{field_name}' (expected={expected_type.value})",
                severity=0.5,
                evidence=[f"type_mismatch:{token.primary_type.value}:{expected_type.value}"],
            ))

    return violations


def check_temporal_ordering(record: SemanticRecord) -> List[ConstraintViolation]:
    """Check temporal ordering consistency.

    If a record has multiple dates, earlier dates should be assigned
    to "start" roles and later dates to "end" roles.
    """
    violations: List[ConstraintViolation] = []
    from app.temporal_reasoning import parse_date

    date_fields = {k: v for k, v in record.mapped_fields.items()
                   if k in ("date", "start_date", "end_date", "departure", "arrival")}

    parsed_dates = [(role, parse_date(val)) for role, val in date_fields.items()]
    parsed_dates = [(r, d) for r, d in parsed_dates if d is not None]

    if len(parsed_dates) >= 2:
        # Check that "start" dates come before "end" dates
        start_dates = [d for r, d in parsed_dates if "start" in r or "depart" in r or r == "date"]
        end_dates = [d for r, d in parsed_dates if "end" in r or "arriv" in r]

        for sd in start_dates:
            for ed in end_dates:
                if sd > ed:
                    violations.append(ConstraintViolation(
                        constraint="temporal_ordering",
                        description=f"Start date {sd} after end date {ed}",
                        severity=0.6,
                        evidence=[f"temporal_reversed:{sd}:{ed}"],
                    ))

    return violations


def check_semantic_graph_constraints(graph: SemanticGraph) -> List[ConstraintViolation]:
    """Check constraints on the semantic graph structure."""
    violations: List[ConstraintViolation] = []

    # Acyclic ownership constraint
    for edge in graph.ownership_edges:
        if edge.owner_region_id == edge.owned_region_id:
            violations.append(ConstraintViolation(
                constraint="acyclic_ownership",
                description=f"Circular ownership: region {edge.owner_region_id} owns itself",
                severity=1.0,
                evidence=["self_ownership"],
            ))

    return violations


def check_all_constraints(
    record: SemanticRecord,
    graph: Optional[AllocationGraph] = None,
    semantic_graph: Optional[SemanticGraph] = None,
) -> List[ConstraintViolation]:
    """Check all universal constraints and return violations."""
    violations: List[ConstraintViolation] = []

    if graph:
        violations.extend(check_exclusivity_constraints(graph))

    violations.extend(check_type_consistency(record))
    violations.extend(check_temporal_ordering(record))

    if semantic_graph:
        violations.extend(check_semantic_graph_constraints(semantic_graph))

    return violations


def compute_constraint_penalty(violations: List[ConstraintViolation]) -> float:
    """Compute total confidence penalty from constraint violations."""
    if not violations:
        return 0.0

    total = sum(v.severity for v in violations)
    return min(total / len(violations), 1.0)
