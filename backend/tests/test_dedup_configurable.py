"""Wave 6 Qual 1: Configurable deduplication — content-hash and URL+field
hash keys with keep_first / keep_last / union_fields strategies."""

from __future__ import annotations

from app.utils.quality import DedupConfig, configurable_deduplicate_records

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

RECORDS_SAME_CONTENT = [
    {"title": "Widget A", "price": 10.0, "color": "red"},
    {"title": "Widget A", "price": 10.0, "color": "red"},  # exact dup
    {"title": "Widget B", "price": 20.0, "color": "blue"},
]

RECORDS_DIFFERENT_URL_SAME_TITLE = [
    {
        "title": "Widget A",
        "price": 10.0,
        "source_url": "https://shop.example.com/widget-a",
    },
    {
        "title": "Widget A",
        "price": 15.0,
        "source_url": "https://other.example.com/widget-a",
    },
    {
        "title": "Widget B",
        "price": 20.0,
        "source_url": "https://shop.example.com/widget-b",
    },
]

RECORDS_SAME_URL_DIFFERENT_EXTRA = [
    {
        "title": "Widget A",
        "price": 10.0,
        "color": "red",
        "source_url": "https://shop.example.com/widget-a",
    },
    {
        "title": "Widget A",
        "price": 10.0,
        "color": "blue",
        "source_url": "https://shop.example.com/widget-a",
    },
    {
        "title": "Widget B",
        "price": 20.0,
        "color": "green",
        "source_url": "https://shop.example.com/widget-b",
    },
]


# ---------------------------------------------------------------------------
# Tests: key = content_hash
# ---------------------------------------------------------------------------


class TestDedupContentHashKeepFirst:
    """Dedup by full content fingerprint, keeping the first occurrence."""

    def test_exact_duplicates_removed(self) -> None:
        cfg = DedupConfig(key="content_hash", strategy="keep_first")
        unique, removed = configurable_deduplicate_records(RECORDS_SAME_CONTENT, cfg)
        assert len(unique) == 2
        assert removed == 1
        # First occurrence preserved
        assert unique[0]["color"] == "red"

    def test_empty_input(self) -> None:
        cfg = DedupConfig(key="content_hash", strategy="keep_first")
        unique, removed = configurable_deduplicate_records([], cfg)
        assert unique == []
        assert removed == 0


class TestDedupContentHashKeepLast:
    """Dedup by full content fingerprint, keeping the last occurrence."""

    def test_last_wins(self) -> None:
        """With content_hash, only records with identical content get the same
        fingerprint. The keep_last strategy replaces the stored record with the
        later occurrence."""
        # Two records share the same data payload but differ in a metadata
        # field that is excluded from the content hash, plus one pure dup.
        records = [
            {"title": "A", "price": 5, "_record_id": "r1"},
            {"title": "A", "price": 5, "_record_id": "r2"},  # same content, different _record_id
            {"title": "A", "price": 5, "_record_id": "r2"},  # exact dup of previous
        ]
        cfg = DedupConfig(key="content_hash", strategy="keep_last")
        unique, removed = configurable_deduplicate_records(records, cfg)
        assert len(unique) == 1
        # keep_last => last-seen _record_id should be in the result
        assert unique[0]["_record_id"] == "r2"


# ---------------------------------------------------------------------------
# Tests: key = url_field_hash
# ---------------------------------------------------------------------------


class TestDedupUrlFieldHash:
    """Dedup by URL + key-fields fingerprint."""

    def test_same_url_and_key_fields_deduped(self) -> None:
        cfg = DedupConfig(key="url_field_hash", strategy="keep_first", key_fields=["title"])
        unique, removed = configurable_deduplicate_records(RECORDS_SAME_URL_DIFFERENT_EXTRA, cfg)
        # First and second records share same source_url + title => deduped
        assert len(unique) == 2
        assert removed == 1
        # keep_first means color stays "red"
        assert unique[0]["color"] == "red"

    def test_different_url_same_title_not_deduped(self) -> None:
        cfg = DedupConfig(key="url_field_hash", strategy="keep_first", key_fields=["title"])
        unique, removed = configurable_deduplicate_records(RECORDS_DIFFERENT_URL_SAME_TITLE, cfg)
        # Different source_url => different fingerprints
        assert len(unique) == 3
        assert removed == 0


# ---------------------------------------------------------------------------
# Tests: strategy = union_fields
# ---------------------------------------------------------------------------


class TestDedupUnionFields:
    """Merge duplicates by unioning field values."""

    def test_scalar_merge_fills_none(self) -> None:
        records = [
            {"title": "A", "price": 10, "color": None, "source_url": "https://x.com/a"},
            {"title": "A", "price": 10, "color": "blue", "source_url": "https://x.com/a"},
        ]
        cfg = DedupConfig(key="url_field_hash", strategy="union_fields", key_fields=["title"])
        unique, removed = configurable_deduplicate_records(records, cfg)
        assert len(unique) == 1
        # color was None in first record, filled from second
        assert unique[0]["color"] == "blue"
        # non-None scalar fields are NOT overwritten
        assert unique[0]["price"] == 10

    def test_list_union_concatenates(self) -> None:
        records = [
            {
                "title": "A",
                "tags": ["fast", "cheap"],
                "source_url": "https://x.com/a",
            },
            {
                "title": "A",
                "tags": ["cheap", "reliable"],
                "source_url": "https://x.com/a",
            },
        ]
        cfg = DedupConfig(key="url_field_hash", strategy="union_fields", key_fields=["title"])
        unique, removed = configurable_deduplicate_records(records, cfg)
        assert len(unique) == 1
        # Tags are unioned and deduped
        tags = unique[0]["tags"]
        assert set(tags) == {"fast", "cheap", "reliable"}


# ---------------------------------------------------------------------------
# Tests: default config (smoke)
# ---------------------------------------------------------------------------


class TestDedupDefaultConfig:
    """Default DedupConfig should behave like keep_first with content_hash."""

    def test_default_removes_exact_dup(self) -> None:
        records = [
            {"title": "X", "value": 1},
            {"title": "X", "value": 1},
            {"title": "Y", "value": 2},
        ]
        unique, removed = configurable_deduplicate_records(records)
        assert len(unique) == 2
        assert removed == 1
