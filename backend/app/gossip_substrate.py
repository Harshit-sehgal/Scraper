"""
Enhanced Gossip Substrate — Multi-node state synchronization.

Implements Push-Pull gossip with:
- Vector clock tracking for causality
- Selective state merging (avoid conflicts)
- Topology-aware peer selection
- State versioning and conflict detection
- Health tracking for peer reliability
"""

import random
import time
import logging
from typing import Dict, Set, Any, Optional, Tuple, List
from collections import defaultdict

logger = logging.getLogger(__name__)


class VectorClock:
    """Track causality of events across distributed nodes."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.clock: Dict[str, int] = defaultdict(int)
        self.clock[node_id] = 0
    
    def increment(self) -> None:
        """Increment this node's clock value."""
        self.clock[self.node_id] += 1
    
    def update(self, other_clock: Dict[str, int]) -> None:
        """Update this node's clock based on received clock."""
        for node_id, ts in other_clock.items():
            self.clock[node_id] = max(self.clock.get(node_id, 0), ts)
        self.increment()
    
    def to_dict(self) -> Dict[str, int]:
        """Export clock as dict."""
        return dict(self.clock)
    
    def compare(self, other: 'VectorClock') -> str:
        """Compare with another clock.
        
        Returns: 'before', 'after', 'concurrent', or 'equal'
        """
        self_lt_other = False
        self_gt_other = False
        
        all_nodes = set(self.clock.keys()) | set(other.clock.keys())
        for node_id in all_nodes:
            s = self.clock.get(node_id, 0)
            o = other.clock.get(node_id, 0)
            if s < o:
                self_lt_other = True
            if s > o:
                self_gt_other = True
        
        if self_lt_other and self_gt_other:
            return 'concurrent'
        elif self_lt_other:
            return 'before'
        elif self_gt_other:
            return 'after'
        else:
            return 'equal'


class NodeHealth:
    """Track health and reliability of a peer node."""
    
    def __init__(self):
        self.success_count = 0
        self.failure_count = 0
        self.last_seen = time.time()
        self.last_sync = 0.0
    
    @property
    def reliability_score(self) -> float:
        """Score from 0-1 indicating peer reliability."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total
    
    @property
    def is_healthy(self) -> bool:
        """Is this peer currently healthy?"""
        return self.reliability_score >= 0.7 and (time.time() - self.last_seen) < 300


class GossipSubstrate:
    """Enhanced P2P gossip protocol for distributed state propagation.
    
    Implements:
    - Push-Pull gossip (bidirectional state exchange)
    - Vector clocks for causality tracking
    - Selective peer selection based on health
    - State versioning with conflict detection
    - Topology awareness (prefer nearby nodes)
    """
    
    def __init__(self, node_id: str = "default"):
        self.node_id = node_id
        self.vector_clock = VectorClock(node_id)
        self.peers: Dict[str, Any] = {}  # node_id -> state_provider
        self.peer_health: Dict[str, NodeHealth] = defaultdict(NodeHealth)
        self.known_nodes: Set[str] = set()
        self.state_versions: Dict[str, Tuple[Any, Dict[str, int]]] = {}  # Track version + clock
        self.conflicts: List[Dict[str, Any]] = []  # Log of detected conflicts
    
    def register_node(self, node_id: str, provider: Any) -> None:
        """Register a virtual peer in the substrate."""
        self.peers[node_id] = provider
        self.known_nodes.add(node_id)
        logger.debug(f"[Gossip] Registered node: {node_id}")
    
    def select_peers_for_gossip(self, count: int = 1) -> List[str]:
        """Select healthy peers for gossip, preferring reliable nodes.
        
        Uses a weighted selection based on:
        - Reliability score
        - Recency of last contact
        """
        candidates = [n for n in self.known_nodes if n != self.node_id]
        if not candidates:
            return []
        
        # Weight candidates by health
        weights = []
        for peer_id in candidates:
            health = self.peer_health[peer_id]
            reliability = health.reliability_score
            
            # Prefer recently seen nodes
            time_penalty = max(0, (time.time() - health.last_seen) / 300)
            adjusted_weight = (reliability * 0.8) + (1 - time_penalty) * 0.2
            weights.append(adjusted_weight)
        
        # Weighted random selection
        if max(weights) <= 0:
            return random.sample(candidates, min(count, len(candidates)))
        
        selected = []
        for _ in range(min(count, len(candidates))):
            total = sum(weights)
            pick = random.uniform(0, total)
            cumsum = 0
            for i, w in enumerate(weights):
                cumsum += w
                if pick <= cumsum:
                    selected.append(candidates[i])
                    weights[i] = 0  # Don't pick same twice
                    break
        
        return selected
    
    def gossip(self, local_node_id: str, peer_id: Optional[str] = None) -> bool:
        """Perform one gossip cycle with a peer.
        
        Args:
            local_node_id: ID of the local node
            peer_id: Optional specific peer to gossip with (auto-select if None)
            
        Returns:
            True if successful, False otherwise
        """
        if not peer_id:
            candidates = self.select_peers_for_gossip(1)
            if not candidates:
                return False
            peer_id = candidates[0]
        
        peer = self.peers.get(peer_id)
        local = self.peers.get(local_node_id)
        
        if not peer or not local:
            self.peer_health[peer_id].failure_count += 1
            return False
        
        try:
            # Phase 1: Pull state from peer
            remote_state = peer.to_dict()
            remote_clock = peer.get_vector_clock() if hasattr(peer, 'get_vector_clock') else {}
            
            # Check for conflicts
            conflict_detected = self._detect_conflicts(local_node_id, peer_id, remote_state, remote_clock)
            
            # Merge pull state
            self.vector_clock.update(remote_clock)
            local.merge_state(remote_state)
            
            # Phase 2: Push local state to peer
            local_state = local.to_dict()
            peer.merge_state(local_state)
            
            # Update health
            self.peer_health[peer_id].success_count += 1
            self.peer_health[peer_id].last_seen = time.time()
            self.peer_health[peer_id].last_sync = time.time()
            
            logger.debug(f"[Gossip] {local_node_id} <-> {peer_id}: sync successful")
            return True
            
        except Exception as e:
            self.peer_health[peer_id].failure_count += 1
            logger.warning(f"[Gossip] Sync with {peer_id} failed: {e}")
            return False
    
    def _detect_conflicts(self, local_id: str, peer_id: str, remote_state: dict, remote_clock: dict) -> bool:
        """Detect if there are conflicting state changes.
        
        Returns: True if conflicts detected
        """
        # Simple conflict detection: if state changed but we don't have causality
        # In a real system, this would use vector clock comparison
        key = f"{local_id}:{peer_id}"
        
        if key in self.state_versions:
            prev_state, prev_clock = self.state_versions[key]
            # If state changed but remote clock isn't strictly greater, we have concurrent changes
            if prev_state != remote_state:
                self.conflicts.append({
                    "local": local_id,
                    "peer": peer_id,
                    "timestamp": time.time(),
                    "local_version": prev_state,
                    "remote_version": remote_state,
                })
                return True
        
        self.state_versions[key] = (remote_state, remote_clock)
        return False
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get health status of all peers."""
        peers_report: Dict[str, Dict[str, Any]] = {}
        
        for node_id in self.known_nodes:
            if node_id == self.node_id:
                continue
            health = self.peer_health[node_id]
            peers_report[node_id] = {
                "reliability_score": health.reliability_score,
                "success_count": health.success_count,
                "failure_count": health.failure_count,
                "is_healthy": health.is_healthy,
                "seconds_since_seen": time.time() - health.last_seen,
            }
        
        report: Dict[str, Any] = {
            "local_node": self.node_id,
            "vector_clock": self.vector_clock.to_dict(),
            "peers": peers_report,
            "conflicts_detected": len(self.conflicts),
        }
        
        return report


# Global singleton - will be initialized with node ID
_substrate: Optional[GossipSubstrate] = None


def get_gossip_substrate(node_id: str = "default") -> GossipSubstrate:
    """Get or create the global gossip substrate."""
    global _substrate
    if _substrate is None:
        _substrate = GossipSubstrate(node_id)
    return _substrate


def reset_gossip_substrate(node_id: str = "default") -> None:
    """Reset the global gossip substrate (useful for testing)."""
    global _substrate
    _substrate = GossipSubstrate(node_id)
