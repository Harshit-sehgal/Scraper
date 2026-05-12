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

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE TRANSITION DETECTOR
# ═══════════════════════════════════════════════════════════════════════════════

# Known transition signatures: type_a → type_b that commonly represent role boundaries
_BOOTSTRAP_TRANSITIONS = {
    ('org', 'number'): 0.7,     # Honda → 2020
    ('org', 'price'): 0.8,      # Google → 25L
    ('organization', 'number'): 0.7,
    ('organization', 'price'): 0.8,
    ('code', 'price'): 0.7,     # INR → 25L
    ('number', 'text'): 0.6,    # 45000 → miles
    ('number', 'code'): 0.3,    # 3 → BHK (low - these merge)
    ('number', 'price'): 0.5,   # ambiguous
}


@dataclass
class TransitionScore:
    """Score for a potential role transition between adjacent tokens."""
    probability: float = 0.5   # 0-1 how likely this is a role transition
    type_pair: str = ""
    evidence: str = ""


class RoleTransitionDetector:
    """Detects when a token begins a new semantic role.

    Adjacent tokens can represent:
    - continuation of the same entity (merge)
    - a transition between semantic roles (boundary)
    - a modifier-value relationship

    This detector learns which type-pair patterns represent role boundaries.
    """

    def __init__(self):
        # Learned transition probabilities: (type_a, type_b) → probability
        self.transition_probs: Dict[Tuple[str, str], float] = dict(_BOOTSTRAP_TRANSITIONS)
        self.observation_count: int = 0

    def score_transition(self, type_a: str, type_b: str) -> TransitionScore:
        """Score how likely a transition between these types represents a role boundary."""
        pair = (type_a, type_b)
        prob = self.transition_probs.get(pair, 0.4)  # Default: low transition probability
        return TransitionScore(probability=prob, type_pair=f"{type_a}→{type_b}")

    def observe_transition(self, type_a: str, type_b: str, is_role_boundary: bool):
        """Observe whether a transition was a role boundary or entity continuation."""
        pair = (type_a, type_b)
        current = self.transition_probs.get(pair, 0.4)
        delta = 0.05 if is_role_boundary else -0.05
        self.transition_probs[pair] = max(0.0, min(1.0, current + delta))
        self.observation_count += 1

    def get_high_transition_types(self) -> List[Tuple[str, str]]:
        """Get type pairs with high transition probability."""
        return [(a, b) for (a, b), p in self.transition_probs.items() if p > 0.6]


# ═══════════════════════════════════════════════════════════════════════════════
# COHESION MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class CohesionModel:
    """Learns which type-pair patterns should merge or split from experience.

    Tracks success rates per (type_a, type_b, merged) pattern.
    Over time, learned rates override bootstrap defaults.
    """

    def __init__(self):
        # Pattern → count of successful outcomes
        self.merge_success: Dict[Tuple[str, str], float] = {}
        self.merge_attempts: Dict[Tuple[str, str], float] = {}
        self.split_success: Dict[Tuple[str, str], float] = {}
        self.split_attempts: Dict[Tuple[str, str], float] = {}

    def record(self, type_a: str, type_b: str, did_merge: bool, success: bool):
        """Record whether a merge or split decision was successful."""
        pair = (type_a, type_b)
        if did_merge:
            self.merge_attempts[pair] = self.merge_attempts.get(pair, 0.0) + 1.0
            if success:
                self.merge_success[pair] = self.merge_success.get(pair, 0.0) + 1.0
        else:
            self.split_attempts[pair] = self.split_attempts.get(pair, 0.0) + 1.0
            if success:
                self.split_success[pair] = self.split_success.get(pair, 0.0) + 1.0

    def merge_success_rate(self, type_a: str, type_b: str) -> float:
        """Get the learned success rate for merging this type pair."""
        pair = (type_a, type_b)
        attempts = self.merge_attempts.get(pair, 0.0)
        if attempts < 2:
            return 0.5  # Not enough data
        return self.merge_success.get(pair, 0.0) / attempts

    def split_success_rate(self, type_a: str, type_b: str) -> float:
        """Get the learned success rate for splitting this type pair."""
        pair = (type_a, type_b)
        attempts = self.split_attempts.get(pair, 0.0)
        if attempts < 2:
            return 0.5
        return self.split_success.get(pair, 0.0) / attempts

    def get_cohesion_bias(self, type_a: str, type_b: str) -> float:
        """Get the learned cohesion bias (-1 to +1, positive = prefer merge)."""
        merge_rate = self.merge_success_rate(type_a, type_b)
        split_rate = self.split_success_rate(type_a, type_b)
        # Bias toward merge if merging has higher success rate
        return merge_rate - split_rate


# ═══════════════════════════════════════════════════════════════════════════════
# MOTIF LEARNER
# ═══════════════════════════════════════════════════════════════════════════════


class MotifLearner:
    """Learns recurring multi-token structural patterns (motifs).

    A motif is a sequence of token types that occurs repeatedly across records.
    Stable motifs represent reliable semantic structures.

    Examples of motifs:
    - [org, code, price]  → entity + identifier + value
    - [org, org, price]   → multi-word entity + value
    - [number, code]      → quantity + unit (often merges)

    By tracking which motifs recur across records, the system can
    learn which structural patterns are meaningful and stable.
    """

    def __init__(self):
        self.motif_counts: Counter = Counter()
        self.total_records: int = 0

    def observe_types(self, types: List[str]):
        """Record a type sequence from a record."""
        self.total_records += 1
        # Record all n-grams of length 2-4 as motifs
        for size in range(2, min(len(types) + 1, 5)):
            for start in range(len(types) - size + 1):
                motif = tuple(types[start:start + size])
                self.motif_counts[motif] += 1

    def stability(self, motif: Tuple[str, ...]) -> float:
        """Get the stability score for a type motif (0-1).

        High stability = this motif has been observed many times.
        """
        if self.total_records == 0:
            return 0.0
        count = self.motif_counts.get(motif, 0)
        return min(count / max(self.total_records, 1), 1.0)

    def boundary_stability(self, left_types: Tuple[str, ...], right_types: Tuple[str, ...]) -> float:
        """Get the stability of a boundary at this position.

        Higher stability → the boundary is more likely to be a real semantic break.
        Lower stability → the tokens are more likely part of the same entity.
        """
        left_stability = self.stability(left_types) if len(left_types) >= 2 else 0.0
        right_stability = self.stability(right_types) if len(right_types) >= 2 else 0.0
        # If both sides form stable motifs, this is likely a real boundary
        return (left_stability + right_stability) / 2.0 if left_stability > 0 or right_stability > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC BOUNDARY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

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
        self.cohesion_model = CohesionModel()
        self.transition_detector = RoleTransitionDetector()
        self.motif_learner = MotifLearner()

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

        # 4. Role transition check: known boundary patterns
        ts = self.transition_detector.score_transition(type_a, type_b)
        if ts.probability > 0.6:
            score.separation = ts.probability
            score.transition = ts.probability
            score.cohesion = 1.0 - ts.probability
            score.uncertainty = 0.3
            return score

        # 5. Number + code: "3 BHK" → merge
        if type_a == 'number' and type_b == 'code':
            score.cohesion = 0.8
            score.separation = 0.2
            score.uncertainty = 0.2
            return score

        # 6. Learned transition patterns (from old system)
        learned = self.learned_transitions.get(pair, 0.0)
        if learned > 0.6:
            score.separation = learned
            score.transition = learned
            score.cohesion = 1.0 - learned
            score.uncertainty = 0.4
            return score

        # 6. Learned cohesion bias from past outcomes
        bias = self.cohesion_model.get_cohesion_bias(type_a, type_b)
        if abs(bias) > 0.2:
            # Strong learned bias overrides default
            if bias > 0:
                score.cohesion = 0.5 + bias * 0.4
                score.separation = 1.0 - score.cohesion
            else:
                score.separation = 0.5 + abs(bias) * 0.4
                score.cohesion = 1.0 - score.separation
            score.transition = 0.3 + abs(bias) * 0.3
            score.uncertainty = 0.4
            return score

        # 7. Default: moderate separation preference
        score.cohesion = 0.4
        score.separation = 0.5
        score.transition = 0.3
        score.uncertainty = 0.5
        return score

    
    def save_state(self) -> dict:
        """Export learned memory for persistence."""
        return {
            "transitions": {f"{k[0]}|{k[1]}": v for k, v in self.transition_detector.transition_probs.items()},
            "motifs": {",".join(k): v for k, v in self.motif_learner.motif_counts.items()},
            "total_records": self.motif_learner.total_records,
            "cohesion_merge": {f"{k[0]}|{k[1]}": v for k, v in self.cohesion_model.merge_success.items()},
            "cohesion_split": {f"{k[0]}|{k[1]}": v for k, v in self.cohesion_model.split_success.items()}
        }

    def load_state(self, state: dict):
        """Import learned memory from persistence."""
        if "transitions" in state:
            self.transition_detector.transition_probs = {
                tuple(k.split("|")): v for k, v in state["transitions"].items()
            }
        if "motifs" in state:
            self.motif_learner.motif_counts.update({
                tuple(k.split(",")): v for k, v in state["motifs"].items()
            })
        if "total_records" in state:
            self.motif_learner.total_records = state["total_records"]
        if "cohesion_merge" in state:
            self.cohesion_model.merge_success = {
                tuple(k.split("|")): v for k, v in state["cohesion_merge"].items()
            }
        if "cohesion_split" in state:
            self.cohesion_model.split_success = {
                tuple(k.split("|")): v for k, v in state["cohesion_split"].items()
            }

    def save_to_file(self, filepath: str):
        import json
        import os
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(self.save_state(), f, indent=2)

    def load_from_file(self, filepath: str):
        import json
        import os
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                self.load_state(json.load(f))

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
        # Also record in the cohesion model
        self.cohesion_model.record(decision.type_a, decision.type_b, decision.merged, decision.success)
        # Also record in the transition detector
        is_role_boundary = not decision.merged and decision.success
        self.transition_detector.observe_transition(decision.type_a, decision.type_b, is_role_boundary)


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


def record_boundary_feedback(type_a: str, type_b: str, merged: bool, coherence: float):
    """Record whether a merge/split decision was successful.

    Called after allocation completes. High coherence → success.
    """
    engine = get_boundary_engine()
    success = coherence > 0.6
    decision = MergeDecision(type_a, type_b, "", "", merged, coherence, success)
    engine.record_decision(decision)


def record_motif_observation(types: List[str]):
    """Record a type sequence as a motif observation."""
    engine = get_boundary_engine()
    engine.motif_learner.observe_types(types)
