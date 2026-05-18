import time
from typing import Dict

class HeartbeatManager:
    """Monitors the health and alignment of distributed OS nodes.
    
    LAW 11: Distributed truth requires continuous verification.
    """
    def __init__(self):
        self.node_registry: Dict[str, dict] = {}

    def record_heartbeat(self, node_id: str, clock: dict, checksum: str, energy: float):
        """Record health metrics from a node."""
        self.node_registry[node_id] = {
            "last_seen": time.time(),
            "clock": clock,
            "checksum": checksum,
            "energy": energy,
            "status": "online"
        }

    def get_global_health(self) -> dict:
        """Analyze the alignment of all known nodes."""
        now = time.time()
        active_nodes = []
        
        # 1. Prune stale nodes (seen > 60s ago)
        for nid in list(self.node_registry.keys()):
            node = self.node_registry[nid]
            if now - node["last_seen"] > 60:
                node["status"] = "offline"
            if now - node["last_seen"] < 10:
                active_nodes.append(node)
                
        if not active_nodes:
            return {"status": "isolated", "active_nodes": 0}
            
        # 2. Check Alignment (Checksum Consistency)
        checksums = [n["checksum"] for n in active_nodes]
        unique_checksums = len(set(checksums))
        alignment = 1.0 if unique_checksums == 1 else (1.0 / unique_checksums)
        
        # 3. Aggregate Energy
        avg_energy = sum(n["energy"] for n in active_nodes) / len(active_nodes) if active_nodes else 0.0
        
        return {
            "status": "synchronized" if alignment == 1.0 else "divergent",
            "active_nodes": len(active_nodes),
            "alignment_score": round(alignment, 3),
            "average_energy": round(avg_energy, 3),
            "nodes": self.node_registry
        }

_manager = HeartbeatManager()

def get_heartbeat_manager() -> HeartbeatManager:
    return _manager
