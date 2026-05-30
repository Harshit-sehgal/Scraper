import random
import logging


class FailureInjector:
    """Utility for stress testing state safety via failure injection.

    LAW 10: Distributed-state safety requires resilience against mid-transaction
    failures.
    """

    def __init__(self, probability: float = 0.0):
        self.probability = probability
        self.active = probability > 0

    def inject(self, label: str = "anonymous"):
        """Randomly raise an exception if failure injection is active."""
        if self.active and random.random() < self.probability:
            logging.getLogger(__name__).warning(f"FAILURE INJECTED: {label}")
            raise RuntimeError(f"Simulated failure in {label}")


_injector = FailureInjector()


def get_injector() -> FailureInjector:
    return _injector


def set_injection_probability(p: float):
    _injector.probability = p
    _injector.active = p > 0
