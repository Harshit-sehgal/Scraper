"""
Iterative Semantic Refinement Engine
======================================
Multi-pass refinement pipeline that allows later stages to
modify earlier assumptions.

Pipeline phases:
1. Initial extraction
2. Region decomposition
3. Semantic allocation
4. Ownership inference
5. Constraint checking
6. Contradiction repair
7. Global coherence optimization
8. Final semantic reconciliation

Core principle: Later stages CAN modify earlier assumptions.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Callable
from copy import deepcopy

from app.semantic_ir import (
    SemanticRecord, DatasetIR,
)
from app.semantic_regions import detect_semantic_regions, build_region_hierarchy
from app.semantic_allocation_engine import allocate_semantic_roles
from app.semantic_constraints import check_all_constraints, compute_constraint_penalty
from app.semantic_contradiction_engine import detect_contradictions
from app.semantic_repair import repair_graph
from app.global_graph_coherence import enhance_dataset_with_global_coherence
from app.semantic_graph import build_semantic_graph
from app.semantic_density import compute_density_profile


@dataclass
class RefinementPhase:
    """A single phase in the refinement pipeline."""
    name: str
    fn: Callable
    description: str
    applied: bool = False
    changes_made: int = 0


@dataclass
class RefinementReport:
    """Report of all refinement phases and their impact."""
    phases: List[RefinementPhase] = field(default_factory=list)
    initial_coherence: float = 0.0
    final_coherence: float = 0.0
    total_changes: int = 0
    improvement: float = 0.0


def refine_record(
    record: SemanticRecord,
    schema_fields: List[str],
    verbose: bool = False,
) -> Tuple[SemanticRecord, RefinementReport]:
    """Run the full multi-pass refinement pipeline on a single record."""
    report = RefinementReport()
    current = deepcopy(record)
    report.initial_coherence = current.overall_confidence

    # Phase 1: Region decomposition
    regions = detect_semantic_regions(current.tokens)
    regions = build_region_hierarchy(regions)
    current.groups = regions
    report.phases.append(RefinementPhase(
        name="regions", fn=lambda: None, description=f"decomposed into {len(regions)} regions",
        applied=True, changes_made=len(regions),
    ))
    if verbose: print(f"  Phase 1: {len(regions)} regions")

    # Phase 2: Semantic allocation
    current, alloc_graph = allocate_semantic_roles(current, schema_fields)
    changes = len([r for r in alloc_graph.roles.values() if r.filled_by])
    report.phases.append(RefinementPhase(
        name="allocation", fn=lambda: None, description=f"{changes} roles assigned",
        applied=True, changes_made=changes,
    ))
    if verbose: print(f"  Phase 2: {changes} roles assigned")

    # Phase 3: Constraint checking
    violations = check_all_constraints(current, alloc_graph)
    if violations:
        penalty = compute_constraint_penalty(violations)
        current.overall_confidence *= (1.0 - penalty * 0.3)
        report.phases.append(RefinementPhase(
            name="constraints", fn=lambda: None,
            description=f"{len(violations)} violations, penalty={penalty:.2f}",
            applied=True, changes_made=len(violations),
        ))
        if verbose: print(f"  Phase 3: {len(violations)} constraint violations")

    # Phase 4: Graph building + contradiction detection
    graph = build_semantic_graph(current)
    contradictions = detect_contradictions(graph)
    if contradictions:
        graph, repair_actions = repair_graph(graph)
        current.overall_confidence = graph.coherence_score
        report.phases.append(RefinementPhase(
            name="repair", fn=lambda: None,
            description=f"{len(repair_actions)} repairs, {len(contradictions)} contradictions",
            applied=True, changes_made=len(repair_actions),
        ))
        if verbose: print(f"  Phase 4: {len(repair_actions)} repairs")

    # Phase 5: Density classification
    density = compute_density_profile(current.tokens)
    if not density.is_data:
        report.phases.append(RefinementPhase(
            name="density", fn=lambda: None,
            description=f"low density={density.semantic_density:.2f}",
            applied=True, changes_made=0,
        ))

    report.final_coherence = current.overall_confidence
    report.improvement = report.final_coherence - report.initial_coherence
    report.total_changes = sum(p.changes_made for p in report.phases)

    return current, report


def refine_dataset(
    dataset: DatasetIR,
    schema_fields: List[str],
    verbose: bool = False,
) -> Tuple[DatasetIR, List[RefinementReport]]:
    """Run full refinement pipeline on all records in a dataset."""
    reports: List[RefinementReport] = []
    refined_records: List[SemanticRecord] = []

    for i, record in enumerate(dataset.records):
        if verbose:
            print(f"\nRecord {i}:")
        refined, report = refine_record(record, schema_fields, verbose)
        refined_records.append(refined)
        reports.append(report)

    dataset.records = refined_records

    # Global coherence pass
    dataset = enhance_dataset_with_global_coherence(dataset)

    if verbose:
        avg_initial = sum(r.initial_coherence for r in reports) / len(reports)
        avg_final = sum(r.final_coherence for r in reports) / len(reports)
        print(f"\nGlobal: coherence={dataset.global_coherence:.2f}")
        print(f"Avg initial: {avg_initial:.2f} → avg final: {avg_final:.2f}")

    return dataset, reports
