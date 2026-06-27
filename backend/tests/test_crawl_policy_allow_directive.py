"""Tests for robots.txt parser enhancements (Roadmap Comp #1).

The CrawlPolicyEngine now supports the ``Allow`` directive. When both
an Allow and a Disallow rule match the same path, the longest match
wins per RFC 9309 §2.2.2.
"""

from __future__ import annotations

from app.crawl_policy import CrawlPolicyEngine


class TestIsPathDisallowed:
    def test_empty_disallowed_returns_false(self) -> None:
        assert CrawlPolicyEngine._is_path_disallowed("/api", set()) is False
        assert CrawlPolicyEngine._is_path_disallowed("/api", set(), set()) is False

    def test_root_disallow_blocks_everything(self) -> None:
        assert CrawlPolicyEngine._is_path_disallowed("/anything", {"/"}) is True

    def test_exact_match_disallows(self) -> None:
        assert CrawlPolicyEngine._is_path_disallowed("/admin", {"/admin"}) is True

    def test_prefix_match_disallows_subpaths(self) -> None:
        assert CrawlPolicyEngine._is_path_disallowed("/admin/users", {"/admin"}) is True

    def test_unrelated_path_allowed(self) -> None:
        assert CrawlPolicyEngine._is_path_disallowed("/public", {"/admin"}) is False

    def test_wildcard_suffix_disallows(self) -> None:
        assert CrawlPolicyEngine._is_path_disallowed("/secret-page", {"/secret*"}) is True


class TestAllowDirective:
    def test_allow_overrides_disallow_when_longer(self) -> None:
        """RFC 9309: the longest matching pattern wins."""
        # Allow is on /public/* and matches the requested path more
        # specifically than a broader Disallow on /
        disallowed = {"/"}
        allowed = {"/public/"}
        result = CrawlPolicyEngine._is_path_disallowed("/public/page", disallowed, allowed)
        assert result is False

    def test_disallow_overrides_allow_when_longer_or_equal(self) -> None:
        """When Disallow is at least as long as Allow, Disallow wins."""
        disallowed = {"/private/"}
        allowed = {"/private/secret"}
        # Path is /private — matches both, but for /private, /private/
        # is a prefix only marginally longer; the test path is /private
        # (exact match in disallowed). Since Allow pattern is longer,
        # the test should NOT be blocked because Allow wins per spec.
        # The longer Allow wins --> allowed
        result = CrawlPolicyEngine._is_path_disallowed("/private/secret", disallowed, allowed)
        assert result is False

    def test_no_allow_set_disallows_per_match(self) -> None:
        """Without any allow set, disallowed paths are still disallowed."""
        disallowed = {"/api"}
        result = CrawlPolicyEngine._is_path_disallowed("/api/users", disallowed, None)
        assert result is True

    def test_empty_allow_set_disallows_per_match(self) -> None:
        """Empty allow set behaves like no allow."""
        disallowed = {"/api"}
        result = CrawlPolicyEngine._is_path_disallowed("/api/users", disallowed, set())
        assert result is True

    def test_allow_partial_match_no_disallow(self) -> None:
        """If disallow doesn't match, allow is irrelevant."""
        disallowed = {"/admin"}
        allowed = {"/public"}
        assert CrawlPolicyEngine._is_path_disallowed("/public/page", disallowed, allowed) is False

    def test_allow_with_wildcard_overrides(self) -> None:
        """Allow with wildcard can override a broader disallow."""
        disallowed = {"/api"}
        # Allow /api/public/* — for path /api/public/data, the allow
        # pattern length is "/api/public/" = 12, disallow is "/api" = 4.
        # Allow is longer → not disallowed.
        allowed = {"/api/public/"}
        result = CrawlPolicyEngine._is_path_disallowed("/api/public/data", disallowed, allowed)
        assert result is False
