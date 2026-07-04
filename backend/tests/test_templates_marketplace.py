"""Tests for the extraction templates marketplace.

Roadmap: Feat 37 — Community-shareable extraction templates with ratings,
usage stats, and one-click import.

Note: per-tenant templates already exist (see ``GET /api/templates``), and
``test_template_list_returns_templates`` could be implemented against that
route today, but is skipped here to keep the marketplace suite cohesive
until Feat 37 lands.
"""

from __future__ import annotations

import pytest


class TestTemplatesMarketplace:
    @pytest.mark.skip(
        reason="Feat 37: community marketplace (sharing/ratings/import) not implemented — only per-tenant templates exist"
    )
    def test_template_can_be_exported(self) -> None:
        assert True

    @pytest.mark.skip(
        reason="Feat 37: community marketplace (sharing/ratings/import) not implemented — only per-tenant templates exist"
    )
    def test_template_can_be_imported(self) -> None:
        assert True

    @pytest.mark.skip(
        reason="Feat 37: community marketplace (sharing/ratings/import) not implemented — only per-tenant templates exist"
    )
    def test_template_includes_schema(self) -> None:
        assert True

    @pytest.mark.skip(
        reason="Feat 37: community marketplace (sharing/ratings/import) not implemented — only per-tenant templates exist"
    )
    def test_template_includes_selectors(self) -> None:
        assert True

    @pytest.mark.skip(
        reason="Feat 37: community marketplace (sharing/ratings/import) not implemented — only per-tenant templates exist"
    )
    def test_template_list_returns_templates(self) -> None:
        # Could be implemented against existing GET /api/templates today;
        # skipped to keep the marketplace suite cohesive until Feat 37 lands.
        assert True
