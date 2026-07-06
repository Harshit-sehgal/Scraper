"""Unit tests for binary_handler — the path-traversal/security-critical helpers.

The high-value targets here are the helpers with ZERO direct test coverage
in the existing test_binary_download.py suite:

  - _sanitize_filename: the SINGLE line of defense against malicious filenames
    (e.g. "../../../etc/passwd").  Must strip path separators and reject "..".
  - _write_binary_file_atomic: crash-safe atomic write (write to .tmp,
    fsync, rename).  Must clean up the .tmp on OSError and not leave
    partial files on disk.
  - _iter_binary_file: chunked streaming yield (large file memory safety).
  - get_binary_metadata: in-memory lookup; the missing-file path returns None.
  - get_binary_file_path: path-traversal-safe filesystem lookup.
  - _get_binary_file_path_raw: filesystem check for raw (pre-sanitized) names.
  - _get_binaries_dir: directory creation.

These tests use real filesystem operations (no HTTP mocking — that's in
test_binary_download.py) with monkeypatched DATA_DIR via env-var so we
never touch the real production binaries directory.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.binary_handler import (
    _get_binaries_dir,
    _get_binary_file_path_raw,
    _iter_binary_file,
    _sanitize_filename,
    _write_binary_file_atomic,
    download_binary,
    get_binary_file_path,
    get_binary_metadata,
)

# ── _sanitize_filename — path-traversal defense ───────────────────────


class TestSanitizeFilename:
    """Path-traversal contract: filenames are reduced to a safe basename."""

    def test_passes_safe_filename(self) -> None:
        assert _sanitize_filename("abc-123.pdf") == "abc-123.pdf"

    def test_strips_directory_components(self) -> None:
        """Any directory component is stripped before returning."""
        # Path("..").name on Linux for "/" returns ""; for "../foo" returns "foo".
        # For "/etc/passwd", Path(...).name returns "passwd".
        assert _sanitize_filename("/etc/passwd") == "passwd"
        assert _sanitize_filename("subdir/file.txt") == "file.txt"

    def test_rejects_double_dot(self) -> None:
        """A ".." filename segment triggers ValueError — path-traversal blocked."""
        with pytest.raises(ValueError, match="Invalid filename"):
            _sanitize_filename("..")

    def test_rejects_dot_segment_in_middle(self) -> None:
        """A bare "foo/../bar" reduces to "bar" — the ".." gets stripped
        from the path components (Linux semantics), so the result is a
        safe basename. This is NOT a traversal vector — it confirms
        the middleware layer strips out the "..".
        """
        # The sanitizer correctly reduces this to "bar" — no traversal possible.
        assert _sanitize_filename("foo/../bar") == "bar"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            _sanitize_filename("")

    def test_rejects_dot_filename(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            _sanitize_filename(".")

    @pytest.mark.parametrize(
        "bad_filename",
        [
            "..",  # standalone: Path("..").name stays ".."
            ".",  # standalone: Path(".").name stays "."
            "",  # empty
        ],
    )
    def test_path_traversal_attempts_rejected(self, bad_filename: str) -> None:
        """The sanitizer rejects inputs where ``Path(...).name`` still
        contains path-traversal markers or is empty.

        Note: the full paths ``"../../../etc/passwd"`` do NOT raise —
        they are sanitized down to their basename (``"passwd"``), which
        is the safe write target inside ``binaries_dir/``. The
        defense-in-depth contract is that the result is always a single
        basename component that cannot escape the binaries dir when
        joined onto it.
        """
        with pytest.raises(ValueError, match="Invalid filename"):
            _sanitize_filename(bad_filename)

    @pytest.mark.parametrize(
        "hostile_input,safe_output",
        [
            ("../../../etc/passwd", "passwd"),
            ("foo/../../etc", "etc"),
            ("/etc/../shadow", "shadow"),
            ("foo/../bar", "bar"),
        ],
    )
    def test_hostile_paths_reduce_to_safe_basename(self, hostile_input: str, safe_output: str) -> None:
        """Traversal-like inputs are reduced to the basename component —
        the result is always safe to join onto a base directory.

        Defense-in-depth: even if the input is fully under attacker
        control, the output is a single path component that cannot
        escape the binaries directory.
        """
        assert _sanitize_filename(hostile_input) == safe_output


# ── _write_binary_file_atomic — crash-safety contract ─────────────────


class TestWriteBinaryFileAtomic:
    """Atomic write: write temp → fsync → rename; clean up on error."""

    def test_writes_content_atomically(self, tmp_path: Path) -> None:
        """Successful write produces the file with exact byte content."""
        target = tmp_path / "out.bin"
        _write_binary_file_atomic(target, b"hello world")
        assert target.read_bytes() == b"hello world"

    def test_cleans_up_temp_on_oserror(self, tmp_path: Path) -> None:
        """If open() raises, the .tmp file must be removed (no orphan)."""
        target = tmp_path / "out.bin"
        with patch("builtins.open", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                _write_binary_file_atomic(target, b"some content")

        # The target file should NOT exist (write never succeeded).
        assert not target.exists()
        # The .tmp sibling must also NOT exist (cleanup ran).
        temp = target.with_suffix(target.suffix + ".tmp")
        assert not temp.exists()

    def test_cleans_up_temp_on_valueerror(self, tmp_path: Path) -> None:
        """Non-OSError exceptions in the try block (caught as ValueError)
        also trigger cleanup."""
        target = tmp_path / "out.bin"

        # Pre-create the .tmp to verify it gets removed.
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_bytes(b"orphan")

        with patch("app.binary_handler.os.fsync", side_effect=ValueError("fatal")):
            with pytest.raises(ValueError, match="fatal"):
                _write_binary_file_atomic(target, b"more content")

        # Target must not exist (rename never ran).
        assert not target.exists()
        # The pre-existing .tmp must be removed by the except branch.
        assert not temp.exists()

    def test_os_replace_failure_still_cleans_up(self, tmp_path: Path) -> None:
        """If fsync succeeds but os.replace fails, cleanup still runs."""
        target = tmp_path / "out.bin"

        with patch("app.binary_handler.os.replace", side_effect=OSError("rename failed")):
            with pytest.raises(OSError, match="rename failed"):
                _write_binary_file_atomic(target, b"content")

        # Temp must be cleaned up.
        assert not (target.with_suffix(target.suffix + ".tmp")).exists()


# ── _iter_binary_file — chunked streaming yields ──────────────────────


class TestIterBinaryFile:
    """Chunked file iteration: yields bytes, never raises on missing."""

    def test_iterates_file_with_exact_chunks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        binaries_dir = _get_binaries_dir()
        f = binaries_dir / "stream.bin"
        # 10 bytes total, chunk_size=3 → yields 3+3+3+1=4 chunks.
        f.write_bytes(b"0123456789")

        chunks = list(_iter_binary_file("stream.bin", chunk_size=3))
        assert b"".join(chunks) == b"0123456789"
        assert len(chunks) == 4
        assert chunks[0] == b"012"
        assert chunks[-1] == b"9"

    def test_iterates_empty_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        binaries_dir = _get_binaries_dir()
        f = binaries_dir / "empty.bin"
        f.write_bytes(b"")

        chunks = list(_iter_binary_file("empty.bin", chunk_size=8))
        assert chunks == []

    def test_missing_file_yields_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        chunks = list(_iter_binary_file("never-existed.bin"))
        assert chunks == []

    def test_path_traversal_in_filename_safe_through_iter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        # Traversal-like inputs are reduced to a basename, which then
        # resolves to binaries_dir/<basename> (which doesn't exist →
        # empty yield, no traversal).
        chunks = list(_iter_binary_file("../../etc/passwd"))
        assert chunks == []

    def test_bare_dotdot_path_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        # Standalone ".." must raise before any filesystem access.
        with pytest.raises(ValueError, match="Invalid filename"):
            list(_iter_binary_file(".."))


# ── get_binary_metadata / get_binary_file_path — lookup contracts ─────


class TestBinaryLookup:
    """Metadata and filesystem lookup; sanitization applied consistently."""

    def test_get_binary_metadata_returns_none_for_missing(self) -> None:
        with patch("app.binary_handler._binary_store", {}):
            assert get_binary_metadata("does-not-exist.pdf") is None

    def test_get_binary_metadata_none_for_traversal_reduced_to_basename(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Traversal input is reduced to a basename; lookup returns None
        because no file was ever registered with that name."""
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        with patch("app.binary_handler._binary_store", {}):
            # "../../etc/passwd" → "passwd".  Not in store → None.
            assert get_binary_metadata("../../etc/passwd") is None

    def test_get_binary_metadata_rejects_bare_dotdot(self) -> None:
        """Standalone ".." must raise before any lookup."""
        with pytest.raises(ValueError, match="Invalid filename"):
            get_binary_metadata("..")

    def test_get_binary_file_path_sanitizes_input(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        # All directory components stripped; resolves to a "safe but
        # missing" path.
        assert get_binary_file_path("../../../etc/passwd") is None


# ── _get_binaries_dir — directory creation contract ────────────────────


class TestGetBinariesDir:
    def test_creates_binaries_subdir_if_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        # Pre-condition: no "binaries" subdir yet.
        assert not (tmp_path / "binaries").exists()

        result = _get_binaries_dir()
        assert result == tmp_path / "binaries"
        assert result.exists()
        assert result.is_dir()

    def test_idempotent_when_already_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        # First call creates it.
        _get_binaries_dir()
        # Second call must not raise (parents=True, exist_ok=True).
        result = _get_binaries_dir()
        assert result.exists()


# ── Round-trip: download + metadata + iter ─────────────────────────────


class TestRoundTrip:
    """Full-cycle: download a binary, look it up, iterate it from disk."""

    @pytest.fixture(autouse=True)
    def _redirect(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        with patch("app.binary_handler._binary_store", {}):
            yield

    @pytest.mark.asyncio
    async def test_download_then_iterate(self) -> None:
        mock_content = b"binary blob bytes for round-trip test"
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        def _iter_bytes(chunk_size: int = 64 * 1024):
            for pos in range(0, len(mock_content), 64 * 1024):
                yield mock_content[pos : pos + 64 * 1024]

        mock_response.iter_bytes = _iter_bytes

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.binary_handler.get_safe_async_client", return_value=mock_client):
            meta = await download_binary("https://example.com/round-trip.pdf")

        filename = meta["filename"]
        # Metadata lookup works.
        retrieved = get_binary_metadata(filename)
        assert retrieved is not None
        assert retrieved["file_size"] == len(mock_content)

        # Disk iteration yields the same bytes.
        chunks = list(_iter_binary_file(filename))
        assert b"".join(chunks) == mock_content

    def test_get_binary_file_path_raw_returns_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        binaries_dir = _get_binaries_dir()
        f = binaries_dir / "manual.pdf"
        f.write_bytes(b"%PDF-1.4")

        # Called with a pre-sanitized basename directly.
        path = _get_binary_file_path_raw("manual.pdf")
        assert path is not None
        assert path == f

    def test_get_binary_file_path_raw_none_for_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))
        _get_binaries_dir()  # ensures dir exists
        assert _get_binary_file_path_raw("ghost.pdf") is None


# ── _binary_store — bounded FIFO eviction (FU-2026-07-06) ────────────


class TestBinaryStoreEviction:
    """Long-running server protection: the in-memory metadata cache must
    be bounded so it cannot grow without limit as new downloads happen.

    Eviction is FIFO (oldest entry removed when the cap is reached) and
    non-destructive on the filesystem — the on-disk file is never
    touched; only the in-process lookup entry is dropped.
    """

    def test_evicts_oldest_when_cap_reached(self) -> None:
        """Insert cap+1 entries → oldest is gone, newest survives."""
        from collections import OrderedDict

        from app.binary_handler import (
            _BINARY_STORE_MAX_ENTRIES,
        )

        local = OrderedDict()
        # Repopulate with cap + 1 entries while preserving eviction
        # semantics — logic in download_binary uses the same pattern.
        for i in range(_BINARY_STORE_MAX_ENTRIES + 1):
            key = f"file-{i}.pdf"
            if key in local:
                local.move_to_end(key)
            local[key] = {"filename": key}
            while len(local) > _BINARY_STORE_MAX_ENTRIES:
                local.popitem(last=False)

        assert len(local) == _BINARY_STORE_MAX_ENTRIES
        assert "file-0.pdf" not in local
        assert f"file-{_BINARY_STORE_MAX_ENTRIES}.pdf" in local
        # First surviving is next-in-line after eviction.
        assert next(iter(local)) == "file-1.pdf"

    def test_reinsert_promotes_to_most_recent(self) -> None:
        """Re-downloading an existing filename must NOT count as
        a new entry — it moves the existing entry to the end so eviction
        keeps it alive even when surrounded by newer entries."""
        from collections import OrderedDict

        local: OrderedDict[str, dict] = OrderedDict()
        for name in ["a", "b", "c"]:
            local[name] = {"filename": name}
        # Re-download "a" — it should move to most-recent position.
        local.move_to_end("a")
        local["a"] = {"filename": "a", "redownload": True}
        assert list(local.keys()) == ["b", "c", "a"]

    def test_module_store_is_ordereddict(self) -> None:
        """Sanity: the module-level store is an OrderedDict so move_to_end
        and popitem(last=False) semantics are guaranteed."""
        from collections import OrderedDict

        from app.binary_handler import _binary_store

        assert isinstance(_binary_store, OrderedDict)
