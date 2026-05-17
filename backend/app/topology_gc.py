"""Topology Garbage Collection — prevents semantic memory explosion.

Stale basins, dead motifs, and unused exclusions are pruned
regularly to prevent unbounded memory growth in the field.

ALL operations go through SemanticWorldState GC gateway APIs.
No subsystem bypass — strengthens the ownership boundary.
"""

import logging

logger = logging.getLogger(__name__)


def collect_garbage(ws):
    """Run full garbage collection cycle on the semantic field.
    
    Delegates all operations to SemanticWorldState GC gateway APIs.
    Returns dict with counts of collected items.
    """
    collected = ws.gc_collect()
    total = sum(collected.values())
    if total > 0:
        logger.debug("GC collected %d items: %s", total, collected)
    return collected
