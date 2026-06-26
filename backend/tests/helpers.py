"""Test helper constants for deterministic URL fixtures.

All test files should import URL constants from here instead of embedding
live-looking URLs like ``https://example.com``. These constants use the
RFC 2606 reserved ``.invalid`` TLD, which is guaranteed non-resolvable.

The conftest DNS stand-in blocks all real DNS lookups in unmarked tests,
so even live-looking URLs are safe. However, using these constants makes
the intent explicit and keeps a single place to update URL patterns.
"""

# Base URL using the RFC 2606 reserved ``.invalid`` TLD — guaranteed
# to never resolve to a real host.
TEST_URL_BASE: str = "https://test.invalid"

# Common URL patterns for test fixtures
TEST_URL_PAGE: str = f"{TEST_URL_BASE}/page"
TEST_URL_PRODUCT: str = f"{TEST_URL_BASE}/products"
TEST_URL_SEARCH: str = f"{TEST_URL_BASE}/search"
TEST_URL_API: str = f"{TEST_URL_BASE}/api/data"
TEST_URL_ITEM: str = f"{TEST_URL_BASE}/item"
TEST_URL_DATA: str = f"{TEST_URL_BASE}/data"
TEST_URL_LIST: str = f"{TEST_URL_BASE}/list"
TEST_URL_FLIGHT: str = f"{TEST_URL_BASE}/flights"
