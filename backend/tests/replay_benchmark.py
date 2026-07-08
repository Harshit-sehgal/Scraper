"""
Replay Benchmark Harness — Phase 55
==================================
LAW: Replay speed must remain sub-linear relative to event volume to support
million-event evolution cycles.

This script executes 10k transactions, captures the journal, and measures
the time to perfectly reconstruct the state via deterministic replay.
"""

import time
import random
from app.semantic_world_state import SemanticWorldState

def benchmark_replay(transaction_count: int = 10000):
    ws = SemanticWorldState()
    ws.clear()
    # Phase 55: Ensure journal doesn't truncate during benchmark
    ws._journal_capacity = transaction_count + 100
    
    roles = [f"role_{i}" for i in range(20)]
    
    print(f"\n--- Starting Replay Benchmark ({transaction_count} transactions) ---")
    
    # 1. Generation Phase
    start_gen = time.time()
    for i in range(transaction_count):
        with ws.transaction(f"tx_{i}"):
            # 3 mutations per tx
            for _ in range(3):
                ws.set_manifold_vector(random.choice(roles), [random.random() for _ in range(16)])
                
    duration_gen = time.time() - start_gen
    print(f"  Generation phase: {duration_gen:.2f}s ({transaction_count / duration_gen:.1f} tx/s)")
    
    # 2. Replay Phase
    journal = ws.trace_causality(limit=transaction_count + 100)
    # Ensure full journal captured
    assert len(journal) >= transaction_count
    
    original_checksum = ws.get_manifold_checksum()
    ws.clear()
    
    start_replay = time.time()
    for tx in journal:
        ws.replay_transaction(tx)
    duration_replay = time.time() - start_replay
    
    print(f"  Replay phase: {duration_replay:.2f}s ({transaction_count / duration_replay:.1f} tx/s)")
    
    # 3. Verification
    final_checksum = ws.get_manifold_checksum()
    if original_checksum != final_checksum:
        print(f"  [ERROR] Checksum mismatch! {original_checksum} != {final_checksum}")
        return False
        
    print("  Verification: SUCCESS (Bit-for-bit parity confirmed)")
    print(f"  Replay Efficiency: {duration_replay / duration_gen:.2f}x generation speed")
    return True

if __name__ == "__main__":
    benchmark_replay(transaction_count=5000)
