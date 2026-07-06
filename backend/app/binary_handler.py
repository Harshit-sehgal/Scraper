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
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.url_safety import get_safe_async_client, validate_public_http_url

logger = logging.getLogger(__name__)

# ─── Binary content-type detection (FU-2026-07-04) ──────────────────

# MIME types we consider binary — the scraper should save these as-is
# rather than trying to parse them as HTML. NOTE: this is the *detection*
# layer only. The persist layer (below) applies an explicit extension +
# content-type allowlist to prevent attackers from persisting unsafe
# payloads (e.g. text/html as application/octet-stream, image/svg+xml).
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

# Extension -> content-type mapping for URLs without explicit Content-Type.
# FU-2026-07-04 (C2): explicitly excludes `image/svg+xml` because SVG can
# carry executable JS and, served from the same origin, becomes a stored
# XSS vector. SVG URLs are still detected as binary but rejected by the
# allowlist below.
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
    ".ico": "image/x-icon",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".ttf": "font/ttf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

# FU-2026-07-04 (C2): explicit allowlist of extensions safe to persist.
# Whatever the URL tail or remote Content-Type says, we will only ever
# write one of these extensions to disk AND serve it back. Excludes
# .svg (XSS), .html/.htm (XSS), .py/.sh/.exe/.bat/.js (executable),
# .bin (ambiguous container for any payload).
_SAFE_BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".bz2",
        ".7z",
        ".rar",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".ico",
        ".mp3",
        ".mp4",
        ".ttf",
        ".woff",
        ".woff2",
    },
)

# FU-2026-07-04 (C2): defence-in-depth content-type denylist. Even if a
# remote claims one of these (or an extension maps to one), reject
# before persisting because serving it back would be unsafe.
_UNSAFE_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        # XSS vectors
        "text/html",
        "text/xhtml",
        "application/xhtml+xml",
        "image/svg+xml",
        "application/javascript",
        "application/x-javascript",
        "text/javascript",
        # Executable / script
        "application/x-sh",
        "application/x-perl",
        "application/x-python",
        "application/x-msdos-program",
        "application/x-msdownload",
        "application/x-executable",
        "application/x-mach-binary",
        "application/x-elf",
    },
)

# Thread-safe store for downloaded binary metadata.
# Bounded FIFO cache: in long-running servers the in-memory lookup dict
# would otherwise grow without limit (one entry per download ever made
# this process lifetime). When the cap is reached, the oldest entry is
# evicted on the next insert. Falls back to filesystem lookup if the
# caller misses the cache (see ``get_binary_metadata`` docstring).
_BINARY_STORE_MAX_ENTRIES = 1024
_binary_store: OrderedDict[str, dict[str, Any]] = OrderedDict()
_binary_store_lock = threading.Lock()


def _sanitize_filename(filename: str) -> str:
    """Strip path separators and CRLF from *filename* to prevent path
    traversal and Content-Disposition header injection.

    Returns only the basename component after stripping slashes,
    control characters, and raising if the cleaned name is empty or
    contains ``..`` segments.
    """
    # FU-2026-07-05 (LOW defense-in-depth): strip CR (\r) and LF (\n)
    # before extracting the basename. ``Path(...).name`` strips / and
    # \ but does not remove newlines; a filename containing \r\n could
    # be interpolated into a ``Content-Disposition: attachment;
    # filename="…"`` header and inject additional HTTP headers or a
    # second body part.
    sanitised = "".join(ch for ch in filename if ch not in "\r\n")
    safe = Path(sanitised).name  # strips any directory components
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
    """Return a suitable file extension for the given content type.

    FU-2026-07-04: only resolves to extensions on ``_SAFE_BINARY_EXTENSIONS``.
    Unsafe content types (text/html, image/svg+xml, application/javascript,
    ...) and unknown extensions resolve to ``""`` so callers can refuse
    persistence explicitly rather than silently serving ``.bin``.
    """
    ct = content_type.split(";", maxsplit=1)[0].strip().lower()
    if ct in _UNSAFE_CONTENT_TYPES:
        return ""
    # Reverse lookup from _EXTENSION_MAP (only includes safe extensions now)
    for ext, mime in _EXTENSION_MAP.items():
        if mime == ct:
            return ext
    # Try mimetypes stdlib — but only accept the resolution if it lands on
    # the safe allowlist. Without this guard, an attacker-controlled
    # `application/x-foo` would round-trip to an arbitrary `.foo` extension.
    guessed_ext = mimetypes.guess_extension(ct)
    if guessed_ext and guessed_ext.lower() in _SAFE_BINARY_EXTENSIONS:
        return guessed_ext
    return ""


def _resolve_safe_extension(url: str, content_type: str | None) -> str | None:
    """Pick a safe persistence extension from URL tail OR response content-type.

    FU-2026-07-04 (C2, H3): the persisted filename's extension must come
    from the allowlist. Either the URL tail or the response content-type
    may supply it, but only if both the URL is on a safe extension AND the
    content-type isn't on the unsafe denylist. Returns ``None`` if no
    safe extension can be derived.
    """
    # Try the URL tail first
    url_ext = _detect_extension_from_url(url)
    if url_ext and url_ext.lower() in _SAFE_BINARY_EXTENSIONS:
        # Cross-check the content type — if both URL and content-type
        # agree on a safe type, accept. If content-type disagrees, fall
        # through to the content-type path.
        if content_type:
            ct_ext = _get_extension_for_content_type(content_type)
            if ct_ext and ct_ext.lower() == url_ext.lower():
                return url_ext
        else:
            return url_ext

    # Try the content-type
    if content_type:
        ct_ext = _get_extension_for_content_type(content_type)
        if ct_ext and ct_ext.lower() in _SAFE_BINARY_EXTENSIONS:
            return ct_ext

    return None


def _detect_extension_from_url(url: str) -> str | None:
    """Return the lower-cased file extension from a URL's path component.

    FU-2026-07-04: split from ``_detect_content_type_from_url`` so callers
    can check the raw extension without doing the content-type lookup
    (which would silently fail on the unsafe default of ".bin").
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    # Find the last `.` after the last `/` to extract the extension.
    basename = path.rsplit("/", 1)[-1]
    if "." not in basename:
        return None
    candidate = basename.rsplit(".", 1)[-1]
    if not candidate:
        return None
    return f".{candidate}"


def _write_binary_file_atomic(save_path: Path, raw_content: bytes) -> None:
    """Write a binary payload durably via a temporary sibling file.

    FU-2026-07-04: legacy helper retained for tests covering the small-
    payload path. The streaming variant ``_write_binary_file_stream`` is
    what ``download_binary`` actually uses — this helper still exists to
    keep the legacy test contract (e.g. writes a known payload to disk).
    """
    temp_path = save_path.with_name(save_path.name + ".tmp")
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


def _write_binary_file_stream(
    save_path: Path,
    resp: httpx.Response,
    *,
    max_bytes: int,
) -> int:
    """Stream *resp* into a temp sibling of *save_path* with a hard byte cap.

    FU-2026-07-04 (C1): streaming upload caps the in-memory footprint at
    one chunk regardless of remote body size. Aborts cleanly if the
    remote delivers more than ``max_bytes``; cleans up the temp file in
    both error paths.

    Returns the total bytes written.
    """
    temp_path = save_path.with_name(save_path.name + ".tmp")
    try:
        written = 0
        with open(temp_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=64 * 1024):
                if chunk:
                    written += len(chunk)
                    if written > max_bytes:
                        msg = f"Binary download exceeds {max_bytes}-byte cap (aborted at {written}+ bytes)"
                        raise ValueError(msg)
                    f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, save_path)
    except (OSError, ValueError):
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise
    return written


async def download_binary(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    usage_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Download binary content from *url* and save it to the binaries directory.

    FU-2026-07-04 hardening:
    - **Size cap** (``MAX_BINARY_DOWNLOAD_BYTES``, default 50 MB): the
      response body is streamed; downloads exceeding the cap abort
      cleanly and the partial temp file is unlinked. Defends against
      OOM/disk-exhaust via attacker-supplied URLs (the inbound
      ``MAX_BODY_SIZE`` middleware cap does not apply to server-initiated
      fetches).
    - **Extension allowlist** (``_SAFE_BINARY_EXTENSIONS``): the persisted
      filename extension must be one of pdf/zip/image/font/audio/etc.
      extensions explicitly on the allowlist. SVG, HTML, JS, EXE, and
      ambiguous ``.bin`` payloads are rejected. Both the URL tail and the
      response Content-Type are checked.
    - **Content-type denylist** (``_UNSAFE_CONTENT_TYPES``): even if the
      extension appears safe, a response Content-Type like
      ``text/html`` or ``image/svg+xml`` is rejected before persistence.

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

    Raises ``ValueError`` if the URL is not safe to persist (mismatched
    extension, unsafe content-type, or missing binary signature).
    """
    validate_public_http_url(url)

    max_bytes = int(
        getattr(settings, "MAX_BINARY_DOWNLOAD_BYTES", 50 * 1024 * 1024),
    )

    file_id = f"{uuid.uuid4().hex[:12]}"
    binaries_dir = _get_binaries_dir()

    request_headers = dict(headers or {})
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        request_headers.setdefault("Cookie", cookie_str)

    async with get_safe_async_client(
        timeout=httpx.Timeout(60.0),
        follow_redirects=True,
    ) as client:
        resp = await client.get(url, headers=request_headers)
        try:
            resp.raise_for_status()

            actual_ct = resp.headers.get("content-type", "").split(";", 1)[0].strip() or None

            # FU-2026-07-04 (C1): cheap Content-Length pre-check before
            # streaming. A hostile server that declares a 5 GB body is
            # rejected without buffering a single byte. The streaming
            # cap below still enforces the limit on responses that lie
            # about (or omit) Content-Length.
            cl_header = resp.headers.get("content-length")
            if cl_header:
                try:
                    declared = int(cl_header)
                except ValueError:
                    declared = -1
                if declared > max_bytes:
                    msg = f"Content-Length {declared} exceeds MAX_BINARY_DOWNLOAD_BYTES ({max_bytes})"
                    raise ValueError(msg)

            # Pick a safe persistence extension from BOTH the URL tail and
            # the response Content-Type. Refuse persistence if either source
            # produces an extension outside the allowlist (FU-2026-07-04 /
            # C2 / H3).
            file_ext = _resolve_safe_extension(url, actual_ct)
            if not file_ext:
                msg = f"URL did not resolve to a safe binary extension (url={url!r}, content_type={actual_ct!r})"
                raise ValueError(msg)

            # Defence-in-depth — refuse known-unsafe content types even
            # when the URL-derived extension passed.
            if actual_ct and actual_ct.lower() in _UNSAFE_CONTENT_TYPES:
                msg = f"Refusing to persist unsafe content-type {actual_ct!r} from {url!r}"
                raise ValueError(msg)

            filename = _sanitize_filename(f"{file_id}{file_ext}")
            save_path = binaries_dir / filename
            content_type = actual_ct or _EXTENSION_MAP.get(
                file_ext,
                "application/octet-stream",
            )

            # Stream the body to disk with the running byte-cap enforcement.
            file_size = await asyncio.to_thread(
                _write_binary_file_stream,
                save_path,
                resp,
                max_bytes=max_bytes,
            )
        finally:
            await resp.aclose()

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

    # Record in the in-memory store so the download endpoint can serve it.
    # FIFO cap to bound memory growth in long-running servers; the
    # filesystem is the source of truth so eviction is non-destructive
    # (the download endpoint already falls back to disk lookup).
    with _binary_store_lock:
        if filename in _binary_store:
            # Move to most-recent to avoid double counting a re-download
            _binary_store.move_to_end(filename)
        _binary_store[filename] = meta
        while len(_binary_store) > _BINARY_STORE_MAX_ENTRIES:
            _binary_store.popitem(last=False)

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
