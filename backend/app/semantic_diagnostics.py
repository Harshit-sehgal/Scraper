"""
Semantic Diagnostics Engine
===========================
Handles meta-cognition and decision explanations for semantic allocation.
Generates human-readable reasoning for why certain values were mapped to specific roles.
"""

from typing import Any, Dict, List


def generate_allocation_diagnostics(
    output: Dict[str, Any],
    schema_fields: List[str],
    reng,
    contradictions: List[str],
    detect_type_fn
) -> List[str]:
    """Generate reasoning for how roles were assigned.
    
    Exposes uncertainty, ambiguity, and structural conflicts.
    """
    reasoning = []
    reng_cache = reng.compatibility_cache
    
    for role_name in schema_fields:
        val = output.get(role_name)
        if val:
            val_type, conf = detect_type_fn(val, role_name)
            compat = reng_cache.get((role_name, val_type.value), 0.5)
            
            # Ambiguity detection
            if 0.45 <= compat <= 0.55:
                reasoning.append(f"Assignment {role_name}='{val}' is highly ambiguous (learned compat: {compat:.2f}).")
            
            if compat > 0.7:
                reasoning.append(f"Mapped '{val}' ({val_type.value}) to {role_name} due to high learned compatibility ({compat:.2f}).")
            elif conf > 0.8:
                reasoning.append(f"Mapped '{val}' to {role_name} based on strong value structure ({val_type.value}).")
            else:
                reasoning.append(f"Mapped '{val}' to {role_name} via structural best-fit (compatibility: {compat:.2f}).")
                
            # Type-role tension detection
            if compat < 0.3:
                reasoning.append(f"High tension: '{val}' ({val_type.value}) is unusual for role {role_name}.")
    
    if contradictions:
        reasoning.append(f"Penalized confidence due to contradictory claims: {', '.join(contradictions)}.")
    
    # Global state diagnostics
    certainty = reng.get_certainty()
    if certainty < 0.3:
        reasoning.append("Global certainty is low: system is still in early exploration phase.")
    elif certainty > 0.8:
        reasoning.append("Global certainty is high: assignments are backed by stable learned patterns.")
        
    speed = reng.get_learning_speed()
    if speed > 0.6:
        reasoning.append("System is learning rapidly from this dataset context.")
        
    return reasoning

