import random
from typing import Dict, Set, Any

class GossipSubstrate:
    """Simulates a P2P gossip protocol for distributed state propagation.
    
    In a real system, this would use sockets/HTTP. Here, it manages
    virtual peer connections and state exchange.
    """
    def __init__(self):
        self.peers: Dict[str, Any] = {} # node_id -> state_provider
        self.known_nodes: Set[str] = set()

    def register_node(self, node_id: str, provider: Any):
        """Register a virtual peer in the substrate."""
        self.peers[node_id] = provider
        self.known_nodes.add(node_id)

    def gossip(self, local_node_id: str):
        """Perform one gossip cycle: pick a random peer and exchange state."""
        other_nodes = [n for n in self.known_nodes if n != local_node_id]
        if not other_nodes:
            return
            
        peer_id = random.choice(other_nodes)
        peer = self.peers.get(peer_id)
        local = self.peers.get(local_node_id)
        
        if peer and local:
            # Push-Pull Gossip (Phase 32)
            # 1. Peer sends state to local
            remote_state = peer.to_dict()
            local.merge_state(remote_state)
            
            # 2. Local sends state to peer
            local_state = local.to_dict()
            peer.merge_state(local_state)

_substrate = GossipSubstrate()

def get_gossip_substrate() -> GossipSubstrate:
    return _substrate
