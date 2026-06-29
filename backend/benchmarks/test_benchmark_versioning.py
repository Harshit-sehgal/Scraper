"""Corpus versioning enforcement tests.

Verifies the local corpus manifest (`local_corpus_expected.json`) is
versioned properly:

  * ``test_corpus_version_is_reasonable_date`` -- the version string
    starts with a current date (today or yesterday).
  * ``test_manifest_version_hash_matches_stored`` -- the sha256
    stored in ``.version_hash`` matches the manifest.
  * ``test_required_categories_stable`` -- the set of required
    categories cannot shrink silently.
  * ``test_case_count_grows_monotonically`` -- case count is monotonic.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "local_corpus_expected.json"
VERSION_HASH_PATH = Path(__file__).parent / ".version_hash"
BASELINE_CATEGORIES_PATH = Path(__file__).parent / ".version_categories"


def _load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _hash_manifest(manifest_bytes: bytes) -> str:
    return hashlib.sha256(manifest_bytes).hexdigest()


def test_corpus_version_is_reasonable_date() -> None:
    """Manifest version must begin with today's or yesterday's ISO date."""
    manifest = _load_manifest()
    version = manifest["version"]
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    acceptable = {today.isoformat(), yesterday.isoformat()}

    assert version[:10] in acceptable, (
        f"Corpus version '{version}' must begin with today's or yesterday's "
        f"date ({today} or {yesterday}). Update the manifest version to a "
        "current date when modifying cases."
    )


def test_manifest_version_hash_matches_stored() -> None:
    """Stored .version_hash must match the manifest's current sha256.

    Regenerate via:
        sha256sum backend/benchmarks/local_corpus_expected.json \
            | awk '{print $1}' > backend/benchmarks/.version_hash
    """
    manifest_bytes = MANIFEST_PATH.read_bytes()
    actual_hash = _hash_manifest(manifest_bytes)
    expected_hash = VERSION_HASH_PATH.read_text(encoding="utf-8").strip()

    assert actual_hash == expected_hash, (
        f"Manifest sha256 ({actual_hash}) does not match stored "
        f".version_hash ({expected_hash}). Regenerate the hash after "
        "modifying the manifest."
    )


def test_required_categories_stable() -> None:
    """Required categories cannot shrink.

    First run: writes baseline. Subsequent runs require superset.
    """
    manifest = _load_manifest()
    current = set(manifest["required_categories"])

    if not BASELINE_CATEGORIES_PATH.exists():
        BASELINE_CATEGORIES_PATH.write_text(
            "\n".join(sorted(current)) + "\n",
            encoding="utf-8",
        )
        return

    baseline = {line.strip() for line in BASELINE_CATEGORIES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()}

    missing = baseline - current
    assert not missing, (
        f"Required categories removed from manifest: {sorted(missing)}. Categories can be added but never silently removed."
    )


def test_case_count_grows_monotonically() -> None:
    """Case count must not decrease between commits."""
    manifest = _load_manifest()
    current_count = len(manifest["cases"])

    counter_path = Path(__file__).parent / ".version_case_count"
    if not counter_path.exists():
        counter_path.write_text(str(current_count), encoding="utf-8")
        return

    floor = int(counter_path.read_text(encoding="utf-8").strip())
    assert current_count >= floor, (
        f"Case count decreased: was {floor}, now {current_count}. Update .version_case_count if this is an intentional reset."
    )
    if current_count > floor:
        counter_path.write_text(str(current_count), encoding="utf-8")
