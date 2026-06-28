#!/usr/bin/env python3
"""Shared fsync-safe file writing helpers for operational scripts.

Every ``Path.write_text()`` or ``open(..., "w")`` call in the scripts/
directory previously skipped ``os.fsync()`` before close, which means a
power failure or container kill between write and kernel flush could
leave a 0-byte or truncated file. For operational scripts that write
production secrets, backup data, drill evidence, and audit artifacts,
durability matters.

Usage::

    from scripts._fsync_helper import write_text_sync, write_gzip_sync  # noqa: F401

    write_text_sync(path, content)
    write_gzip_sync(path, data)

These helpers flush + fsync before close so that on return the data is
guaranteed to be on stable storage (as far as the OS can guarantee it).
"""

from __future__ import annotations

import contextlib
import gzip
import os
from pathlib import Path


def write_text_sync(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    perm: int = 0o644,
    mkdir_parents: bool = True,
) -> None:
    """Write *content* to *path* with ``os.fsync()`` before close.

    Opens the file with ``O_WRONLY | O_CREAT | O_TRUNC`` at the
    requested *perm* (default ``0o644`` — world-readable but not
    world-writable; use ``0o600`` for secret files), writes the
    content, flushes the Python buffer, calls ``os.fsync()`` on the
    underlying fd, and closes.

    If *mkdir_parents* is True (default), the parent directory is
    created with ``mkdir -p`` semantics before opening.
    """
    path = Path(path)
    if mkdir_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, perm)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        # On error, close the fd if it's still open (os.fdopen takes
        # ownership, but if the write + flush failed before fdopen
        # closed it, the fd is leaked without this).
        with contextlib.suppress(OSError):
            os.close(fd)
        raise


def write_gzip_sync(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    perm: int = 0o644,
    mkdir_parents: bool = True,
) -> None:
    """Write *content* to a gzipped *path* with ``os.fsync()`` before close.

    Uses ``gzip.open`` in text mode (``"wt"``). After the write,
    flushes and fsyncs the underlying file descriptor.
    """
    path = Path(path)
    if mkdir_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, perm)
    try:
        with os.fdopen(fd, "wb") as raw_f:
            with gzip.GzipFile(fileobj=raw_f, mode="wb") as gz:
                gz.write(content.encode(encoding))
            raw_f.flush()
            os.fsync(raw_f.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise
