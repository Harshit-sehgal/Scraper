import logging
import os
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
    """Set the singleton injector's probability.

    Production guard: refuse to enable injection when ``DATAFORGE_ENV``
    is ``production``. Failure injection is a research / test-only
    utility; turning it on in production would cause random 5xx errors
    to surface to real callers. We log a warning and leave the
    probability at 0 so the injector stays inert.
    """
    env = (os.environ.get("DATAFORGE_ENV") or "").strip().lower()
    if p > 0 and env == "production":
        logging.getLogger(__name__).warning(
            "Refusing to enable failure injection in production "
            "(requested probability=%s). Failure injection is a test-only "
            "utility; leaving probability at 0.",
            p,
        )
        return
    _injector.probability = p
    _injector.active = p > 0
