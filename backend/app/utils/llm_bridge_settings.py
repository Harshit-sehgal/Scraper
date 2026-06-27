"""Defaults for LLM bridge call behaviour.

Centralised here so the silent-empty fallback vs ``LLMCascadeExhausted``
exception policy can be tuned with a single env var (``DATAFORGE_LLM_RAISE_ON_FAILURE``)
without forcing every caller to pass ``raise_on_failure=`` explicitly.

We deliberately default to ````False`` (silent empty) for backwards-compatibility —
callers that carry data-integrity-sensitive payloads must opt in.  Operators who
want fail-loud behaviour in production can set the flag once and every downstream
caller benefits.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Final

logger = logging.getLogger(__name__)

ENV_VAR: Final[str] = "DATAFORGE_LLM_RAISE_ON_FAILURE"


@lru_cache(maxsize=1)
def llm_raise_on_failure_default() -> bool:
    """Whether LLM bridge public functions raise :class:`LLMCascadeExhausted`.

    Returns:
        True iff the env var is truthy (``1``, ``true``, ``yes``, ``on``).
        Defaults to ``False`` so legacy callers that expect ``{}``/``""``
        keep working without modification.

    Cache key includes the env value so a unit-test that mutates the
    environment can ``cache_clear()`` to pick up the change.
    """
    raw = os.environ.get(ENV_VAR, "").strip().lower()
    if not raw:
        return False
    truthy = raw in ("1", "true", "yes", "on")
    if truthy:
        logger.info("LLM bridge raise_on_failure default is ENABLED — cascade exhaustion will raise LLMCascadeExhausted")
    return truthy


def reset_cache() -> None:
    """Clear the cached default. Test helper."""
    llm_raise_on_failure_default.cache_clear()
