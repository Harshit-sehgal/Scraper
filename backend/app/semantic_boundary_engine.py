
"""
Semantic Boundary Engine
=========================
Determines whether adjacent tokens should merge or stay separate.

Replaces hardcoded suffix lists and merge patterns with scored
boundary decisions based on structural signals and learned history.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.semantic_world_state import get_world_state


@dataclass
class BoundaryScore:
    """Scores for a potential boundary between two tokens."""
    cohesion: float = 0.5  # 0-1, likelihood tokens belong together
    separation: float = 0.5  # 0-1, likelihood tokens are separate
    transition: float = 0.0  # probability of role transition
    uncertainty: float = 0.0

    def should_merge(self) -> bool:
        return self.cohesion > self.separation


@dataclass
class MergeDecision:
    """A recorded decision to merge or split two tokens."""
    type_a: str
    type_b: str
    value_a: str
    value_b: str
    merged: bool
    coherence_after: float
    success: bool = False


@dataclass
class TransitionScore:
    """Score for a type transition."""
    probability: float
    type_pair: str


# ═══════════════════════════════════════════════════════════════════════════════
# BOOTSTRAP KNOWLEDGE (Smallest possible set)
# ═══════════════════════════════════════════════════════════════════════════════

_BOOTSTRAP_SUFFIXES = {
    'group', 'inc', 'ltd', 'limited', 'corp', 'corporation',
    'industries', 'designs', 'designers', 'studio', 'associates',
    'international', 'solutions', 'technologies', 'services'
}

_STOP_WORDS = {'the', 'a', 'an', 'and', 'of', 'for'}

# High-confidence transition pairs (e.g. price followed by date)
_HIGH_TRANSITION_PAIRS = {
    ('price', 'date'),
    ('price', 'location'),
    ('date', 'price'),
    ('rating', 'price'),
    ('rating', 'date'),
}

# ═══════════════════════════════════════════════════════════════════════════════
# ROLE TRANSITION DETECTOR
# ═══════════════════════════════════════════════════════════════════════════════

_BOOTSTRAP_TRANSITIONS = {
    ('organization', 'price'): 0.85,
    ('organization', 'location'): 0.80,
    ('location', 'price'): 0.85,
    ('price', 'date'): 0.90,
    ('date', 'price'): 0.90,
    ('number', 'organization'): 0.70,
    ('organization', 'number'): 0.70,
}


class RoleTransitionDetector:
    """Learns which type transitions likely mark a semantic role boundary."""

    def __init__(self):
        # Ensure bootstrap transitions are present in the world state
        ws = get_world_state()
        if not ws.transition_probs:
            ws.transition_probs.update(_BOOTSTRAP_TRANSITIONS)

    @property
    def transition_probs(self) -> Dict[Tuple[str, str], float]:
        return get_world_state().transition_probs

    @property
    def observation_count(self) -> int:
        return get_world_state().metrics.transition_observations

    @observation_count.setter
    def observation_count(self, value: int):
        get_world_state().metrics.transition_observations = value

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
        pass

    @property
    def merge_success(self) -> Dict[Tuple[str, str], float]:
        return get_world_state().cohesion_merge_success

    @property
    def merge_attempts(self) -> Dict[Tuple[str, str], float]:
        return get_world_state().cohesion_merge_attempts

    @property
    def split_success(self) -> Dict[Tuple[str, str], float]:
        return get_world_state().cohesion_split_success

    @property
    def split_attempts(self) -> Dict[Tuple[str, str], float]:
        return get_world_state().cohesion_split_attempts

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
        if attempts < 1:
            return 0.5  # Not enough data
        return self.merge_success.get(pair, 0.0) / attempts

    def split_success_rate(self, type_a: str, type_b: str) -> float:
        """Get the learned success rate for splitting this type pair."""
        pair = (type_a, type_b)
        attempts = self.split_attempts.get(pair, 0.0)
        if attempts < 1:
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
    """

    def __init__(self):
        pass

    @property
    def total_records(self) -> int:
        return get_world_state().metrics.total_records_processed

    @total_records.setter
    def total_records(self, value: int):
        get_world_state().metrics.total_records_processed = value

    def observe_types(self, types: List[str]):
        """Record and REINFORCE a type sequence from a record."""
        ws = get_world_state()
        self.total_records += 1

        # Record all n-grams of length 2-4 as motifs
        for size in range(2, min(len(types) + 1, 5)):
            for start in range(len(types) - size + 1):
                motif = tuple(types[start:start + size])
                ws.reinforce_motif(motif)

    def stability(self, motif: Tuple[str, ...]) -> float:
        """Get the stability score for a type motif (0-1)."""
        return get_world_state().get_motif_stability(motif)


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC BOUNDARY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticBoundaryEngine:
    """Scores adjacent token pairs for cohesion vs separation."""

    def __init__(self):
        self.cohesion_model = CohesionModel()
        self.transition_detector = RoleTransitionDetector()
        self.motif_learner = MotifLearner()

    @property
    def decision_history(self) -> list:
        return get_world_state().decision_history

    def score_pair(self, type_a: str, type_b: str, value_a: str, value_b: str,
                   position_a: int, position_b: int) -> BoundaryScore:
        """Score an adjacent token pair for cohesion vs separation."""
        score = BoundaryScore()

        # 1. High-confidence transition check
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

        # 3. Learned cohesion bias from past outcomes (HIGHER PRIORITY)
        bias = self.cohesion_model.get_cohesion_bias(type_a, type_b)
        if abs(bias) > 0.2:
            if bias > 0:
                score.cohesion = 0.5 + bias * 0.4
                score.separation = 1.0 - score.cohesion
            else:
                score.separation = 0.5 + abs(bias) * 0.4
                score.cohesion = 1.0 - score.separation
            score.transition = 0.3 + abs(bias) * 0.3
            score.uncertainty = 0.4
            return score

        # 4. Same-type check
        if type_a == type_b:
            if type_a in ('org', 'organization'):
                if value_b.lower() in _BOOTSTRAP_SUFFIXES:
                    score.cohesion = 0.85
                    score.separation = 0.15
                else:
                    score.cohesion = 0.3
                    score.separation = 0.7
                return score
            score.cohesion = 0.2
            score.separation = 0.7
            return score

        # 5. Role transition detector check
        ts = self.transition_detector.score_transition(type_a, type_b)
        if ts.probability > 0.6:
            score.separation = ts.probability
            score.transition = ts.probability
            score.cohesion = 1.0 - ts.probability
            return score

        # 6. Number + code: "3 BHK" → merge
        if type_a == 'number' and type_b == 'code':
            score.cohesion = 0.8
            score.separation = 0.2
            return score

        # 7. Default
        score.cohesion = 0.4
        score.separation = 0.5
        score.transition = 0.3
        score.uncertainty = 0.5
        return score

    def save_state(self) -> dict:
        """Export learned memory for persistence."""
        return get_world_state().to_dict()

    def load_state(self, state: dict):
        """Import learned memory from persistence."""
        get_world_state().from_dict(state)

    def decide_merge(self, type_a: str, type_b: str, value_a: str, value_b: str,
                     position_a: int, position_b: int) -> bool:
        score = self.score_pair(type_a, type_b, value_a, value_b, position_a, position_b)
        return score.should_merge()

    def record_decision(self, decision: MergeDecision):
        self.decision_history.append(decision)
        self.cohesion_model.record(decision.type_a, decision.type_b, decision.merged, decision.success)
        is_role_boundary = not decision.merged and decision.success
        self.transition_detector.observe_transition(decision.type_a, decision.type_b, is_role_boundary)


def group_adjacent_entities(records: list) -> list:
    """Merge consecutive segmented values that form multi-token entities."""
    if not records:
        return records

    for record in records:
        seen: set[str] = set()
        keys_to_delete = []
        from app.semantic_mapper import is_child_fragment
        for k in list(record.keys()):
            v = record.get(k)
            if v and isinstance(v, str):
                if is_child_fragment(v, seen):
                    keys_to_delete.append(k)
                seen.add(v)
        for k in keys_to_delete:
            if k in record:
                del record[k]

        def _sort_key(k):
            parts = k.rsplit('_', 1)
            return int(parts[-1]) if parts[-1].isdigit() else 0

        seg_keys = sorted([k for k in record if '_seg_' in k], key=_sort_key)
        if len(seg_keys) < 2:
            continue

        merged = set()
        i = 0
        while i < len(seg_keys) - 1:
            k1, k2 = seg_keys[i], seg_keys[i + 1]
            t1 = k1.split('_')[-2] if len(k1.split('_')) >= 3 else ''
            t2 = k2.split('_')[-2] if len(k2.split('_')) >= 3 else ''
            v1, v2 = record.get(k1, ''), record.get(k2, '')
            if v1 and v2:
                if score_boundary(t1, t2, v1, v2, i, i + 1):
                    record[k1] = f"{v1} {v2}"
                    record[k2] = None
                    merged.add(k2)
                    i += 2
                    continue
            i += 1

        for k in merged:
            if k in record:
                del record[k]
    return records


_boundary_engine: Optional[SemanticBoundaryEngine] = None

def get_boundary_engine() -> SemanticBoundaryEngine:
    global _boundary_engine
    if _boundary_engine is None:
        _boundary_engine = SemanticBoundaryEngine()
    return _boundary_engine

def score_boundary(type_a: str, type_b: str, value_a: str, value_b: str,
                   pos_a: int = 0, pos_b: int = 0) -> bool:
    engine = get_boundary_engine()
    return engine.decide_merge(type_a, type_b, value_a, value_b, pos_a, pos_b)

def record_motif_observation(types: List[str]):
    engine = get_boundary_engine()
    engine.motif_learner.observe_types(types)
