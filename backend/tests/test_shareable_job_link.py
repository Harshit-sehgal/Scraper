"""Tests for public shareable job link.

Roadmap: Feat 38 — GET /share/{job_token} renders a read-only view of
extraction results without authentication.
"""

from __future__ import annotations

import pytest


class TestShareableJobLink:
    @pytest.mark.skip(reason="Feat 38: public shareable job link not implemented")
    def test_share_link_generates(self) -> None:
        assert True

    @pytest.mark.skip(reason="Feat 38: public shareable job link not implemented")
    def test_share_link_returns_results(self) -> None:
        assert True

    @pytest.mark.skip(reason="Feat 38: public shareable job link not implemented")
    def test_share_link_expires(self) -> None:
        assert True

    @pytest.mark.skip(reason="Feat 38: public shareable job link not implemented")
    def test_invalid_share_link_returns_404(self) -> None:
        assert True

    @pytest.mark.skip(reason="Feat 38: public shareable job link not implemented")
    def test_share_link_readonly(self) -> None:
        assert True
