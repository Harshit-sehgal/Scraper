"""
Semantic Boundary Engine
=========================
Determines whether adjacent tokens should merge or stay separate.

Replaces hardcoded suffix lists and merge patterns with scored
boundary decisions based on structural signals.

Core principle: Adjacency ≠ semantic cohesion.
Nearby tokens can be one entity, multiple entities, or a role transition.
The engine must learn which is which.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
import re

from app.semantic_ir import SemanticType
from app.semantic_allocation_engine import _get_role_engine


# Known entity suffixes for bootstrap (will be replaced by learning)
_BOOTSTRAP_SUFFIXES = {'group', 'inc', 'corp', 'llc', 'ltd', 'company', 'airlines',
                       'airways', 'hotel', 'hotels', 'resort', 'restaurant', 'place',
                       'festival', 'cafe', 'school'}

# Stop words at the start of entity names
_STOP_WORDS = {'the', 'a', 'an'}

# Transition-heavy type pairs (likely role boundaries, not merges)
_HIGH_TRANSITION_PAIRS = {
    ('organization', 'number'),   # Honda 2020
    ('organization', 'price'),    # Google 25L
    ('code', 'price'),            # INR 25L
    ('number', 'text'),           # 2020 Limited
}


@dataclass
class BoundaryScore:
    """Score for a single adjacent token pair."""
    cohesion: float = 0.0      # How likely they form one entity (0-1)
    separation: float = 0.0    # How likely they are separate (0-1)
    transition: float = 0.0    # How likely this is a role transition (0-1)
    uncertainty: float = 1.0   # How uncertain the decision is (0-1)

    def should_merge(self, threshold: float = 0.6) -> bool:
        """Decide if tokens should merge based on scores."""
        if self.uncertainty > 0.5:
            return False  # Don't merge when uncertain
        return self.cohesion > threshold and self.cohesion > self.separation


@dataclass
class MergeDecision:
    """Record of a merge/split decision for learning."""
    type_a: str
    type_b: str
    value_a: str
    value_b: str
    merged: bool
    coherence_after: float = 0.0
    success: bool = False


class SemanticBoundaryEngine:
    """Scores adjacent token pairs for cohesion vs separation.

    Uses structural signals:
    - Type transition patterns
    - Co-occurrence history
    - Positional proximity
    - Learned boundaries from past decisions
    """

    def __init__(self):
        self.decision_history: List[MergeDecision] = []
        self.learned_transitions: Dict[Tuple[str, str], float] = {}

    def score_pair(self, type_a: str, type_b: str, value_a: str, value_b: str,
                   position_a: int, position_b: int) -> BoundaryScore:
        """Score an adjacent token pair for cohesion vs separation."""
        score = BoundaryScore()

        # 1. Type transition check
        pair = (type_a, type_b)
        if pair in _HIGH_TRANSITION_PAIRS:
            score.transition = 0.8
            score.separation = 0.7
            score.cohesion = 0.2
            score.uncertainty = 0.3
            return score

        # 2. Stop-word prefix: "The" + org → merge (check before same-type)
        if value_a.lower() in _STOP_WORDS and type_b in ('org', 'organization'):
            score.cohesion = 0.85
            score.separation = 0.1
            score.uncertainty = 0.15
            return score

        # 3. Same-type check
        if type_a == type_b:
            # org+org: check if second is an entity suffix
            if type_a in ('org', 'organization'):
                if value_b.lower() in _BOOTSTRAP_SUFFIXES:
                    score.cohesion = 0.85
                    score.separation = 0.15
                    score.uncertainty = 0.2
                else:
                    score.cohesion = 0.3
                    score.separation = 0.7
                    score.uncertainty = 0.3
                return score

            # number+number or code+code: likely separate
            score.cohesion = 0.2
            score.separation = 0.7
            score.transition = 0.6
            score.uncertainty = 0.3
            return score

        # 3. Stop-word prefix: "The" + org → merge
        if value_a.lower() in _STOP_WORDS and type_b in ('org', 'organization'):
            score.cohesion = 0.85
            score.separation = 0.1
            score.uncertainty = 0.15
            return score

        # 4. Number + code: "3 BHK" → merge
        if type_a == 'number' and type_b == 'code':
            score.cohesion = 0.8
            score.separation = 0.2
            score.uncertainty = 0.2
            return score

        # 5. Learned transition patterns
        learned = self.learned_transitions.get(pair, 0.0)
        if learned > 0.6:
            score.separation = learned
            score.transition = learned
            score.cohesion = 1.0 - learned
            score.uncertainty = 0.4
            return score

        # 6. Default: moderate separation preference
        score.cohesion = 0.4
        score.separation = 0.5
        score.transition = 0.3
        score.uncertainty = 0.5
        return score

    def decide_merge(self, type_a: str, type_b: str, value_a: str, value_b: str,
                     position_a: int, position_b: int) -> bool:
        """Decide whether two adjacent tokens should merge."""
        score = self.score_pair(type_a, type_b, value_a, value_b, position_a, position_b)
        return score.should_merge()

    def record_decision(self, decision: MergeDecision):
        """Record a merge decision for learning."""
        self.decision_history.append(decision)
        pair = (decision.type_a, decision.type_b)

        if decision.merged and decision.success:
            # Reinforce this merge pattern
            self.learned_transitions[pair] = self.learned_transitions.get(pair, 0.5) + 0.1
        elif decision.merged and not decision.success:
            # Weaken this merge pattern
            self.learned_transitions[pair] = self.learned_transitions.get(pair, 0.5) - 0.1
        elif not decision.merged and decision.success:
            # Reinforce this separation pattern
            self.learned_transitions[pair] = self.learned_transitions.get(pair, 0.5) + 0.1

        self.learned_transitions[pair] = max(0.0, min(1.0, self.learned_transitions[pair]))


# Global singleton boundary engine
_boundary_engine: Optional[SemanticBoundaryEngine] = None


def get_boundary_engine() -> SemanticBoundaryEngine:
    """Get the global boundary engine singleton."""
    global _boundary_engine
    if _boundary_engine is None:
        _boundary_engine = SemanticBoundaryEngine()
    return _boundary_engine


def score_boundary(type_a: str, type_b: str, value_a: str, value_b: str,
                   pos_a: int = 0, pos_b: int = 0) -> bool:
    """Convenience function to score and decide a boundary."""
    engine = get_boundary_engine()
    return engine.decide_merge(type_a, type_b, value_a, value_b, pos_a, pos_b)
