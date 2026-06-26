"""Shared atomic-write helper for JSON persistence.

Centralises the ``tempfile.mkstemp`` → ``os.fdopen`` → ``json.dump`` →
``os.replace`` pattern (with cleanup on failure) that was duplicated
across 5+ modules.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def atomic_json_write(
    data: Any,
    dest: Path | str,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    default: Any = None,
) -> None:
    """Write *data* as JSON to *dest* atomically.

    Uses ``tempfile.mkstemp`` in the same directory followed by
    ``os.replace`` so readers never see a partially-written file.
    On failure the temp file is cleaned up and the exception
    re-raised.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    fd: int | None = None
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = None  # ownership transferred to fdopen context manager
            json.dump(data, f, indent=indent, sort_keys=sort_keys, default=default)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest)
        tmp_path = None  # ownership transferred via rename
    except Exception:
        with contextlib.suppress(OSError):
            if fd is not None:
                os.close(fd)
        if tmp_path is not None:
            with contextlib.suppress(FileNotFoundError):
                Path(tmp_path).unlink()
        raise
