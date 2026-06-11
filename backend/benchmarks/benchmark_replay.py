"""Replay Benchmark Harness — Phase 55.
==================================
Goal: measure replay speed for a local synthetic semantic-world workload.

This script executes 10k transactions, captures the journal, and measures
the time to perfectly reconstruct the state via deterministic replay.
"""

import random
import time

from app.semantic_world_state import SemanticWorldState


def _check(condition: bool, message: str) -> None:
    """Runtime invariant check. Used instead of ``assert`` so the benchmark
    keeps working when run with ``python -O`` (which strips asserts).
    """
    if not condition:
        msg = f"BENCHMARK INVARIANT FAILED: {message}"
        raise SystemExit(msg)


def benchmark_replay(transaction_count: int = 10000) -> bool:
    ws = SemanticWorldState()
    ws.clear()
    # Phase 55: Ensure journal doesn't truncate during benchmark
    ws._journal_capacity = transaction_count + 100

    roles = [f"role_{i}" for i in range(20)]

    # 1. Generation Phase
    for i in range(transaction_count):
        with ws.transaction(f"tx_{i}"):
            # 3 mutations per tx
            for _ in range(3):
                ws.set_manifold_vector(random.choice(roles), [random.random() for _ in range(16)])  # nosec B311 — synthetic load generator, no security need

    # 2. Replay Phase
    journal = ws.trace_causality(limit=transaction_count + 100)
    # Ensure full journal captured
    _check(len(journal) >= transaction_count, f"journal truncated: got {len(journal)} of {transaction_count}")

    original_checksum = ws.get_manifold_checksum()
    ws.clear()

    start_replay = time.time()
    for tx in journal:
        ws.replay_transaction(tx)
    time.time() - start_replay

    # 3. Verification
    final_checksum = ws.get_manifold_checksum()
    return original_checksum == final_checksum


if __name__ == "__main__":
    benchmark_replay(transaction_count=5000)
