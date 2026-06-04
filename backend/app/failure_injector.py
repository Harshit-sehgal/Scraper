import logging
import random


class FailureInjector:
    """Utility for stress testing state safety via failure injection.

    LAW 10: Distributed-state safety requires resilience against mid-transaction
    failures.
    """

    def __init__(self, probability: float = 0.0) -> None:
        self.probability = probability
        self.active = probability > 0

    def inject(self, label: str = "anonymous") -> None:
        """Randomly raise an exception if failure injection is active."""
        if self.active and random.random() < self.probability:  # nosec B311
            logging.getLogger(__name__).warning("FAILURE INJECTED: %s", label)
            msg = f"Simulated failure in {label}"
            raise RuntimeError(msg)


_injector = FailureInjector()


def get_injector() -> FailureInjector:
    return _injector


def set_injection_probability(p: float) -> None:
    _injector.probability = p
    _injector.active = p > 0
