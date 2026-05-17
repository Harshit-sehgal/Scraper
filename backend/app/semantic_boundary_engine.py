
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
        ws.update_seed_transition(_BOOTSTRAP_TRANSITIONS)

    @property
    def _transition_state(self):
        """Access the owned TransitionState."""
        return get_world_state()._transition

    @property
    def transition_probs(self) -> Dict[Tuple[str, str], float]:
        return self._transition_state.transition_probs

    @property
    def observation_count(self) -> int:
        return self._transition_state.transition_observations

    @observation_count.setter
    def observation_count(self, value: int):
        self._transition_state.set_transition_observations(value)

    def score_transition(self, type_a: str, type_b: str) -> TransitionScore:
        """Score how likely a transition between these types represents a role boundary."""
        prob = self._transition_state.get_prob(type_a, type_b)
        return TransitionScore(probability=prob, type_pair=f"{type_a}→{type_b}")

    def observe_transition(self, type_a: str, type_b: str, is_role_boundary: bool):
        """Observe whether a transition was a role boundary or entity continuation."""
        self._transition_state.observe(type_a, type_b, is_role_boundary)

    def get_high_transition_types(self) -> List[Tuple[str, str]]:
        """Get type pairs with high transition probability."""
        return self._transition_state.get_high_transition_types()


# ═══════════════════════════════════════════════════════════════════════════════
# COHESION MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class CohesionModel:
    """Learns which type-pair patterns should merge or split from experience.

    Tracks success rates per (type_a, type_b, merged) pattern.
    Over time, learned rates override bootstrap defaults.
    """

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
        ws = get_world_state()
        if did_merge:
            ws.record_cohesion_merge_attempt(pair)
            if success:
                ws.record_cohesion_merge_success(pair)
        else:
            ws.record_cohesion_split_attempt(pair)
            if success:
                ws.record_cohesion_split_success(pair)

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

    @property
    def total_records(self) -> int:
        return get_world_state().metrics.total_records_processed

    @total_records.setter
    def total_records(self, value: int):
        get_world_state().metrics.total_records_processed = value

    def observe_types(self, types: List[str]):
        # Identity Protection: filter out known-noisy motifs
        if any(t == "text" for t in types) and len(types) > 4: return
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

        # 1. TOPOLOGICAL MOTIF CHECK (Primary Strategy)
        # If this sequence (A, B) is part of a stable recurring motif, prefer cohesion
        motif = (type_a, type_b)
        stability = self.motif_learner.stability(motif)
        if stability > 0.6:
            score.cohesion = 0.5 + stability * 0.4
            score.separation = 1.0 - score.cohesion
            score.uncertainty = 0.2
            return score

        # 2. Role Transition check (Topological Discontinuity)
        ts = self.transition_detector.score_transition(type_a, type_b)
        if ts.probability > 0.6:
            score.separation = ts.probability
            score.transition = ts.probability
            score.cohesion = 1.0 - ts.probability
            return score

        # 3. High-confidence transition check (Bootstrap)
        pair = (type_a, type_b)
        if pair in _HIGH_TRANSITION_PAIRS:
            score.transition = 0.8
            score.separation = 0.7
            score.cohesion = 0.2
            return score

        # 4. Learned cohesion bias from past outcomes
        bias = self.cohesion_model.get_cohesion_bias(type_a, type_b)
        if abs(bias) > 0.2:
            if bias > 0:
                score.cohesion = 0.5 + bias * 0.4
                score.separation = 1.0 - score.cohesion
            else:
                score.separation = 0.5 + abs(bias) * 0.4
                score.cohesion = 1.0 - score.separation
            return score

        # 5. Symbolic/Hardcoded fallbacks (Lowest priority)
        # "The" + org → merge
        if value_a.lower() in _STOP_WORDS and type_b in ('org', 'organization'):
            score.cohesion = 0.85
            score.separation = 0.1
            return score

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

        # Number + code: "3 BHK" → merge
        if type_a == 'number' and type_b == 'code':
            score.cohesion = 0.8
            score.separation = 0.2
            return score

        # 6. Default
        score.cohesion = 0.4
        score.separation = 0.5
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
        decision_dict = decision.__dict__ if hasattr(decision, '__dict__') else {}
        get_world_state().record_decision(decision_dict)
        self.cohesion_model.record(decision.type_a, decision.type_b, decision.merged, decision.success)
        is_role_boundary = not decision.merged and decision.success
        self.transition_detector.observe_transition(decision.type_a, decision.type_b, is_role_boundary)

    def update_recent_decisions(self, coherence: float, threshold: float):
        """Update the most recent decisions with coherence/success metadata.
        
        Uses controlled access through HistoryState to avoid in-place
        alias mutation of internal list elements.
        """
        ws = get_world_state()
        recent = ws.get_recent_decisions(20)
        ws.update_recent_decision_metadata(recent, coherence, threshold)


def group_adjacent_entities(records: list) -> list:
    """Merge consecutive segmented values that form multi-token entities."""
    if not records:
        return records

    for record in records:
        # Step 1: Clean up child fragments that are already part of larger values
        seen: set[str] = set()
        keys_to_delete = []
        from app.semantic_mapper import is_child_fragment
        
        # Sort keys to ensure we process in a predictable order
        all_keys = list(record.keys())
        for k in all_keys:
            v = record.get(k)
            if v and isinstance(v, str):
                if is_child_fragment(v, seen):
                    keys_to_delete.append(k)
                else:
                    seen.add(v)
        
        for k in keys_to_delete:
            if k in record:
                del record[k]

        # Step 2: Merge adjacent segments (_seg_ keys)
        def _get_topo_info(k):
            # New Format: {key}_seg_{type}_{i}_{start}_{end}
            # Old Format: {key}_seg_{type}_{i}
            parts = k.rsplit('_', 2)
            if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
                return int(parts[-2]), int(parts[-1]), int(k.rsplit('_', 3)[-3] if '_' in k else 0)
            
            # Fallback to linear index if spans missing
            idx_part = k.rsplit('_', 1)[-1]
            idx = int(idx_part) if idx_part.isdigit() else 0
            return 0, 0, idx

        # Sort by start span if available, otherwise by linear index
        seg_keys = sorted([k for k in record if '_seg_' in k], 
                         key=lambda k: (info := _get_topo_info(k), info[0] if info[0] > 0 else info[2]))
        if len(seg_keys) < 2:
            continue

        merged_keys = set()
        current_idx = 0
        while current_idx < len(seg_keys) - 1:
            k_head = seg_keys[current_idx]
            h_start, h_end, h_idx = _get_topo_info(k_head)
            
            # Try to merge subsequent tokens into the head
            lookahead = 1
            while current_idx + lookahead < len(seg_keys):
                k_next = seg_keys[current_idx + lookahead]
                n_start, n_end, n_idx = _get_topo_info(k_next)
                
                # Adjacency check:
                # If spans exist: max 3 chars gap
                # If no spans: must be consecutive indices (e.g. 0 and 1)
                if h_start > 0 or n_start > 0:
                    if n_start - h_end > 3: break
                else:
                    if n_idx - h_idx > 1: break

                # Extract types from key names
                parts_h = k_head.split('_')
                parts_n = k_next.split('_')
                
                # Format detection: new format has at least 5 parts
                if len(parts_h) >= 5 and parts_h[-1].isdigit() and parts_h[-2].isdigit():
                    t_head = parts_h[-4]
                    t_next = parts_n[-4] if len(parts_n) >= 5 else ''
                else:
                    # Old format: {key}_seg_{type}_{i}
                    t_head = parts_h[-2] if len(parts_h) >= 3 else ''
                    t_next = parts_n[-2] if len(parts_n) >= 3 else ''
                
                v_head = record.get(k_head, '')
                v_next = record.get(k_next, '')
                
                if v_head and v_next:
                    # Boundary engine scores based on types and values
                    if score_boundary(t_head, t_next, v_head, v_next, h_start, n_start):
                        # Merge into head
                        record[k_head] = f"{v_head} {v_next}".strip()
                        record[k_next] = None
                        merged_keys.add(k_next)
                        # Update head's end span for next adjacency check
                        h_end = n_end
                        lookahead += 1
                        continue
                
                # If no merge, stop lookahead for this head
                break
            
            # Move to the next un-merged token
            current_idx += lookahead

        # Final cleanup
        for k in merged_keys:
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
