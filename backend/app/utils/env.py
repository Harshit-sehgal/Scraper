import logging
import os

logger = logging.getLogger(__name__)


def env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except Exception:
            logger.exception("Failed to parse env var %s", name)
            value = default

    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value
