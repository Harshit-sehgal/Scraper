"""F-SELECTOR-MEM-001: domain-vs-URL-path keying.

Verifies that ``SelectorMemory._extract_domain`` produces distinct keys for
different page types on the same domain, while still grouping different
items within the same page type under one key.
"""

from __future__ import annotations

from app.selector_memory import SelectorMemory


class TestExtractDomainPathKeying:
    """Verify domain+path-prefix composite keys."""

    def test_same_domain_different_path_types(self) -> None:
        """``/products`` and ``/blog`` on the same domain must produce
        distinct keys so selectors don't cross-contaminate."""
        key_products = SelectorMemory._extract_domain("https://example.com/products")
        key_blog = SelectorMemory._extract_domain("https://example.com/blog")
        assert key_products == "example.com/products"
        assert key_blog == "example.com/blog"
        assert key_products != key_blog, (
            f"Same-domain different paths must have different keys, got {key_products!r} and {key_blog!r}"
        )

    def test_same_page_type_different_items_share_key(self) -> None:
        """Different items on ``/products/`` must share the same key."""
        key1 = SelectorMemory._extract_domain("https://example.com/products/42")
        key2 = SelectorMemory._extract_domain("https://example.com/products/99")
        assert key1 == key2 == "example.com/products", f"Product items must share key, got {key1!r} and {key2!r}"

    def test_numeric_id_skipped(self) -> None:
        """Path segments that are pure digits must be treated as leaf IDs
        and skipped so ``/items/42`` keys to ``/items``."""
        key = SelectorMemory._extract_domain("https://example.com/items/42")
        assert key == "example.com/items", f"Expected example.com/items, got {key!r}"

    def test_uuid_like_segment_skipped(self) -> None:
        """UUID- or hash-like segments (>=32 chars with hyphens) must be skipped."""
        key = SelectorMemory._extract_domain("https://example.com/orders/550e8400-e29b-41d4-a716-446655440000")
        assert key == "example.com/orders", f"Expected example.com/orders, got {key!r}"

    def test_homepage_no_path(self) -> None:
        """Root URL must return just the domain."""
        key = SelectorMemory._extract_domain("https://example.com")
        assert key == "example.com", f"Expected example.com, got {key!r}"

        key2 = SelectorMemory._extract_domain("https://example.com/")
        assert key2 == "example.com", f"Expected example.com, got {key2!r}"

    def test_trailing_slash_normalized(self) -> None:
        """Trailing slashes must be normalized away."""
        key_with = SelectorMemory._extract_domain("https://example.com/catalog/")
        key_without = SelectorMemory._extract_domain("https://example.com/catalog")
        assert key_with == key_without == "example.com/catalog"

    def test_subdomain_retained(self) -> None:
        """Subdomain must be part of the key."""
        key = SelectorMemory._extract_domain("https://shop.example.com/products")
        assert key == "shop.example.com/products", f"Unexpected key: {key!r}"

    def test_port_retained_in_netloc(self) -> None:
        """Port numbers must be preserved in the netloc."""
        key = SelectorMemory._extract_domain("http://localhost:8080/admin")
        assert key == "localhost:8080/admin", f"Unexpected key: {key!r}"

    def test_deep_path_only_first_meaningful(self) -> None:
        """Only the first meaningful segment is used."""
        key = SelectorMemory._extract_domain("https://example.com/api/v2/items/123/details")
        assert key == "example.com/api", f"Expected example.com/api, got {key!r}"

    def test_invalid_url_returns_none(self) -> None:
        """Unparseable URLs must return None."""
        assert SelectorMemory._extract_domain("not-a-url") is None
        assert SelectorMemory._extract_domain("") is None

    def test_no_host_returns_none(self) -> None:
        """URLs without a host must return None."""
        assert SelectorMemory._extract_domain("file:///tmp/foo") is None


class TestSelectorMemoryBackwardCompat:
    """Verify old domain-only lookups still work via the new keying.

    Existing data with plain domain keys (no path prefix) will not match
    the new composite keys, so we verify the public API degrades
    gracefully: ``get_selectors`` returns None for domains not yet
    stored under a composite key.
    """

    def test_get_selectors_returns_none_for_old_style_key(self, tmp_path) -> None:
        """An old domain-only entry won't match under new composite keys."""
        mem = SelectorMemory(storage_path=str(tmp_path / "backcompat.json"))

        # Manually insert old-style domain-only entry
        mem._memory["example.com"] = {
            "selectors": {"fields": {"title": "h1"}},
            "success_count": 5,
            "failure_count": 0,
            "first_seen": 0,
            "last_success": 9999999999,
        }
        mem._save()

        # Look up with a URL that has a path — should not match
        # because the composite key would be "example.com/products", not
        # "example.com".
        result = mem.get_selectors("https://example.com/products")
        assert result is None, (
            "Old domain-only key 'example.com' must not match composite key 'example.com/products' — data needs to be re-learned"
        )

        # But the raw domain-only key lookup still works from _memory dict
        # (used by get_memory_stats and force_cleanup).
        stats = mem.get_memory_stats()
        assert stats["total_domains"] == 1

    def test_new_key_round_trip(self, tmp_path) -> None:
        """A selector learned with a composite-keyed URL must be
        retrievable with the same page type."""
        mem = SelectorMemory(storage_path=str(tmp_path / "roundtrip.json"))

        mem.record_success(
            "https://example.com/products",
            {"fields": {"title": "h1.product-title"}},
        )
        result = mem.get_selectors("https://example.com/products/item-42")
        assert result is not None, "Selector learned on /products must be retrievable for /products/item-42"
        assert result["fields"]["title"] == "h1.product-title"

    def test_has_memory_for_composite_key(self, tmp_path) -> None:
        """``has_memory_for`` must respect composite keying."""
        mem = SelectorMemory(storage_path=str(tmp_path / "hasmem.json"))

        mem.record_success(
            "https://example.com/search",
            {"fields": {"result": "div.search-result"}},
        )
        assert mem.has_memory_for("https://example.com/search/")
        assert mem.has_memory_for("https://example.com/search?q=test")
        assert not mem.has_memory_for("https://example.com/blog")

    def test_invalidate_domain_composite_key(self, tmp_path) -> None:
        """Invalidating one page type must not affect another on the same domain."""
        mem = SelectorMemory(storage_path=str(tmp_path / "inval.json"))

        mem.record_success(
            "https://example.com/products",
            {"fields": {"title": "h1"}},
        )
        mem.record_success(
            "https://example.com/blog",
            {"fields": {"title": "article h1"}},
        )

        assert mem.has_memory_for("https://example.com/products")
        assert mem.has_memory_for("https://example.com/blog")

        # Invalidate only the /products page type
        assert mem.invalidate_domain("https://example.com/products/42")
        assert not mem.has_memory_for("https://example.com/products")
        # /blog must be untouched
        assert mem.has_memory_for("https://example.com/blog")
