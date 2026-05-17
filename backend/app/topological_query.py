from typing import List, Optional
from app.semantic_world_state import get_world_state
from app.semantic_ir import SemanticType

class TopologicalQuery:
    """Evaluates geometric and relational queries against the semantic field."""
    
    def __init__(self, ws=None):
        self.ws = ws or get_world_state()

    def find_roles_near(self, role_name: str, radius: float = 0.5) -> List[dict]:
        """Find roles within geometric radius in the manifold."""
        target_vec = self.ws._manifold.get_manifold_vector(role_name)
        if not target_vec:
            return []
            
        return self._find_near_vec(target_vec, radius, exclude_role=role_name)

    def find_roles_near_type(self, stype: SemanticType, radius: float = 0.4) -> List[dict]:
        """Find roles geometrically near a canonical type vector (Phase 34)."""
        from app.semantic_inference_engine import RoleEmbeddingEngine
        reng = RoleEmbeddingEngine()
        target_vec = reng._get_type_vector(stype)
        return self._find_near_vec(target_vec, radius)

    def _find_near_vec(self, target_vec: list, radius: float, exclude_role: Optional[str] = None) -> List[dict]:
        results = []
        for role in self.ws._manifold.get_manifold_roles():
            if role == exclude_role:
                continue
            vec = self.ws._manifold.get_manifold_vector(role)
            # Distance: sum of squared differences
            dist = sum((a - b) ** 2 for a, b in zip(target_vec, vec)) ** 0.5
            if dist <= radius:
                results.append({
                    "role": role,
                    "distance": round(dist, 4),
                    "instability": self.ws.metrics.get_schema_instability(role)
                })
        return sorted(results, key=lambda x: x["distance"])

    def find_stable_anchors(self) -> List[tuple]:
        """Return all protected relational anchors."""
        return list(self.ws._topology.anchors)

    def execute_tql(self, query: str) -> dict:
        """Simple TQL Parser and Executor.
        
        Supported syntax:
        - NEAR <role> [radius]
        - STABLE [threshold]
        - EXCLUSIONS FOR <role>
        """
        parts = query.split()
        if not parts:
            return {"error": "Empty query"}
            
        cmd = parts[0].upper()
        
        if cmd == "NEAR":
            role = parts[1]
            radius = float(parts[2]) if len(parts) > 2 else 0.5
            return {"type": "roles", "data": self.find_roles_near(role, radius)}
            
        if cmd == "STABLE":
            threshold = float(parts[1]) if len(parts) > 1 else 0.2
            stable_roles = [r for r in self.ws._manifold.get_manifold_roles() 
                           if self.ws.metrics.get_schema_instability(r) <= threshold]
            return {"type": "roles", "data": stable_roles}
            
        if cmd == "EXCLUSIONS":
            # Syntax: EXCLUSIONS FOR <role>
            if len(parts) >= 3 and parts[1].upper() == "FOR":
                role = parts[2]
                excl = {str(k): v for k, v in self.ws.learned_exclusions.items() if role in k}
                return {"type": "exclusions", "role": role, "data": excl}
                
        return {"error": f"Unknown TQL command: {cmd}"}

def get_tql_engine(ws=None) -> TopologicalQuery:
    return TopologicalQuery(ws=ws)
