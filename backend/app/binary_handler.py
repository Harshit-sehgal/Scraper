"""Binary download handler — detect, download, and serve binary content.

Roadmap Feat 5: ``scrape_url(extract_binary=True)`` saves PDF, ZIP,
image files to disk and returns a download URL in the result metadata.

Architecture
------------
The binary handler sits alongside the HTML extraction pipeline. When
``scrape_url`` is called with ``extract_binary=True``, the scraper
checks the URL extension to detect binary content. If the URL looks like
binary (PDF, ZIP, image, …) the handler downloads the full payload as
raw bytes, writes it to ``{DATA_DIR}/binaries/``, and returns a
``ScrapeAttemptResult`` whose single record carries ``_binary_file_url``
and ``_binary_file_path`` keys. The upstream caller (job runner / API
endpoint) can then serve the file through ``GET /api/download/{filename}``.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.url_safety import get_safe_async_client, validate_public_http_url

logger = logging.getLogger(__name__)

# ─── Binary content-type detection ─────────────────────────────────────

# MIME types we consider binary — the scraper should save these as-is
# rather than trying to parse them as HTML.
_BINARY_MIME_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"^application/(pdf|zip|gzip|x-tar|x-bzip2|x-7z-compressed|x-rar-compressed|x-msdownload|vnd\.ms-|x-iso|octet-stream)$",
        re.IGNORECASE,
    ),
    re.compile(r"^image/", re.IGNORECASE),
    re.compile(r"^audio/", re.IGNORECASE),
    re.compile(r"^video/", re.IGNORECASE),
    re.compile(r"^font/", re.IGNORECASE),
    re.compile(
        r"^application/vnd\.openxmlformats|application/vnd\.oasis|application/vnd\.ms-|application/vnd\.google-apps",
        re.IGNORECASE,
    ),
    re.compile(r"^application/json", re.IGNORECASE),
]

# Extension -> content-type mapping for URLs without explicit Content-Type
_EXTENSION_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".gz": "application/gzip",
    ".tar": "application/x-tar",
    ".bz2": "application/x-bzip2",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/x-rar-compressed",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".ttf": "font/ttf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

# Thread-safe store for downloaded binary metadata
_binary_store: dict[str, dict[str, Any]] = {}
_binary_store_lock = threading.Lock()


def _sanitize_filename(filename: str) -> str:
    """Strip path separators from *filename* to prevent path traversal.

    Returns only the basename component after stripping slashes and
    raising if the cleaned name is empty or contains ``..`` segments.
    """
    safe = Path(filename).name  # strips any directory components
    if not safe or safe == "." or ".." in Path(safe).parts:
        msg = f"Invalid filename: {filename!r}"
        raise ValueError(msg)
    return safe


def _get_binaries_dir() -> Path:
    """Return the directory where binary downloads are stored, creating it if needed."""
    base = Path(settings.DATA_DIR).resolve()
    binaries_dir = base / "binaries"
    binaries_dir.mkdir(parents=True, exist_ok=True)
    return binaries_dir


def _detect_content_type_from_url(url: str) -> str | None:
    """Guess content type from URL extension when no Content-Type header is available."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    for ext, mime in _EXTENSION_MAP.items():
        if path.endswith(ext):
            return mime
    return None


def is_binary_content_type(content_type: str | None) -> bool:
    """Return True if the content-type indicates binary content.

    A ``None`` or empty content-type is considered *not binary* so the
    normal HTML pipeline runs (the HEAD pre-check is advisory only).
    """
    if not content_type:
        return False
    ct = content_type.split(";")[0].strip()
    return any(pattern.match(ct) for pattern in _BINARY_MIME_PATTERNS)


def _get_extension_for_content_type(content_type: str) -> str:
    """Return a suitable file extension for the given content type."""
    ct = content_type.split(";", maxsplit=1)[0].strip().lower()
    # Reverse lookup from _EXTENSION_MAP
    for ext, mime in _EXTENSION_MAP.items():
        if mime == ct:
            return ext
    # Try mimetypes stdlib
    guessed_ext = mimetypes.guess_extension(ct)
    if guessed_ext:
        return guessed_ext
    # Fallback: derive from type
    if ct.startswith("image/"):
        return ".img"
    if ct.startswith("video/"):
        return ".vid"
    if ct.startswith("audio/"):
        return ".aud"
    if ct.startswith("font/"):
        return ".fnt"
    return ".bin"


def _write_binary_file_atomic(save_path: Path, raw_content: bytes) -> None:
    """Write a binary payload durably via a temporary sibling file."""
    temp_path = save_path.with_suffix(save_path.suffix + ".tmp")
    try:
        with open(temp_path, "wb") as f:
            f.write(raw_content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, save_path)
    except (OSError, ValueError):
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


async def download_binary(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    usage_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Download binary content from *url* and save it to the binaries directory.

    Returns a metadata dict:

    .. code-block:: python

        {
            "content_type": "application/pdf",
            "file_size": 123456,
            "saved_path": "/app/backend/data/binaries/abc-123.pdf",
            "download_url": "/api/download/abc-123.pdf",
            "filename": "abc-123.pdf",
            "original_url": "https://example.com/report.pdf",
        }

    Raises ``ValueError`` if the URL does not point to binary content.
    """
    validate_public_http_url(url)

    content_type = _detect_content_type_from_url(url)
    file_ext = _get_extension_for_content_type(content_type or "application/octet-stream")

    file_id = f"{uuid.uuid4().hex[:12]}"
    filename = f"{file_id}{file_ext}"
    # Sanitize immediately to prevent injection via file_ext
    filename = _sanitize_filename(filename)

    binaries_dir = _get_binaries_dir()
    save_path = binaries_dir / filename

    request_headers = dict(headers or {})
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        request_headers.setdefault("Cookie", cookie_str)

    async with get_safe_async_client(timeout=httpx.Timeout(60.0), follow_redirects=True) as client:
        resp = await client.get(url, headers=request_headers)
        try:
            resp.raise_for_status()
            raw_content = resp.content

            # Use the response content-type if available (more accurate than extension guess)
            actual_ct = resp.headers.get("content-type", "").split(";")[0].strip()
            if actual_ct:
                if not is_binary_content_type(actual_ct):
                    msg = f"URL did not return binary content: {actual_ct}"
                    raise ValueError(msg)
                content_type = actual_ct
                # Recompute extension if the content-type differs from the URL guess
                ext_from_ct = _get_extension_for_content_type(actual_ct)
                if ext_from_ct != file_ext:
                    filename = _sanitize_filename(f"{file_id}{ext_from_ct}")
                    save_path = binaries_dir / filename
            elif not is_binary_content_type(content_type):
                msg = "URL did not return a binary Content-Type"
                raise ValueError(msg)
        finally:
            await resp.aclose()

        await asyncio.to_thread(_write_binary_file_atomic, save_path, raw_content)

    file_size = len(raw_content)
    download_url = f"/api/download/{filename}"

    meta: dict[str, Any] = {
        "content_type": content_type,
        "file_size": file_size,
        "saved_path": str(save_path),
        "download_url": download_url,
        "filename": filename,
        "original_url": url,
    }
    if usage_context:
        meta.update(
            {
                "created_by": str(usage_context.get("user_id") or ""),
                "org_id": str(usage_context.get("org_id") or ""),
                "project_id": str(usage_context.get("project_id") or ""),
                "job_id": str(usage_context.get("job_id") or ""),
            }
        )

    # Record in the in-memory store so the download endpoint can serve it
    with _binary_store_lock:
        _binary_store[filename] = meta

    logger.info(
        "Downloaded binary %s (%s, %d bytes) from %s",
        filename,
        content_type,
        file_size,
        url,
    )
    return meta


def get_binary_metadata(filename: str) -> dict[str, Any] | None:
    """Return stored metadata for a previously-downloaded binary file.

    Returns ``None`` if the file is not in the in-memory store (may
    still exist on disk from a previous process lifetime). The caller
    should check the filesystem directly when the store returns None.
    """
    safe = _sanitize_filename(filename)
    with _binary_store_lock:
        return _binary_store.get(safe)


def _get_binary_file_path_raw(filename: str) -> Path | None:
    """Return the filesystem path for a binary file, or None if it doesn't exist.

    **Does not** sanitize *filename* — only call this with pre-sanitized input.
    """
    binaries_dir = _get_binaries_dir()
    path = binaries_dir / filename
    if path.exists() and path.is_file():
        return path
    return None


def get_binary_file_path(filename: str) -> Path | None:
    """Return the filesystem path for a binary file, or None if it doesn't exist.

    Path-traversal safe: *filename* is sanitized before filesystem access.
    """
    safe = _sanitize_filename(filename)
    return _get_binary_file_path_raw(safe)


def _iter_binary_file(filename: str, chunk_size: int = 65536):
    """Iterate over a binary file in chunks, yielding bytes.

    Path-traversal safe: *filename* is sanitized before filesystem access.
    Uses chunked reads so large files (hundreds of MB) do not spike memory.
    """
    safe = _sanitize_filename(filename)
    path = _get_binary_file_path_raw(safe)
    if path is None:
        return
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk
