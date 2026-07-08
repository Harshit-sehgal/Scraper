import time

class CognitiveBudget:
    """Manages resource bounds for cognitive cycles.
    
    Prevents runaway loops and ensures system responsiveness by tracking
    cycle counts and execution time.
    """
    def __init__(self, max_cycles: int = 100, max_time_ms: float = 500.0):
        self.max_cycles = max_cycles
        self.max_time_ms = max_time_ms
        self.start_time = time.time()
        self.cycle_count = 0
        self._interrupted = False

    def increment_cycle(self) -> bool:
        """Increment cycle count and check if budget is exceeded.
        
        Returns:
            True if budget remains, False if exceeded.
        """
        self.cycle_count += 1
        
        if self.cycle_count > self.max_cycles:
            self._interrupted = True
            return False
            
        elapsed_ms = (time.time() - self.start_time) * 1000.0
        if elapsed_ms > self.max_time_ms:
            self._interrupted = True
            return False
            
        return True

    @property
    def is_exhausted(self) -> bool:
        return self._interrupted

    @property
    def usage_report(self) -> dict:
        return {
            "cycles": self.cycle_count,
            "elapsed_ms": round((time.time() - self.start_time) * 1000.0, 2),
            "exhausted": self._interrupted
        }

def get_default_budget() -> CognitiveBudget:
    return CognitiveBudget()
