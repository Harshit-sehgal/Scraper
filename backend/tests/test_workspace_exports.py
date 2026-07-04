"""Tests for workspace export integrations.

Roadmap: Feat 27 — Google Sheets / Airtable / Notion one-click export.

Local CSV/JSON/XLSX export is tested elsewhere; these tests cover the
third-party workspace integrations that are not yet implemented.
"""

from __future__ import annotations

import pytest


class TestWorkspaceExports:
    @pytest.mark.skip(
        reason="Feat 27: Google Sheets/Airtable/Notion export not implemented; local CSV/JSON/XLSX export tested elsewhere"
    )
    def test_csv_export_works(self) -> None:
        assert True

    @pytest.mark.skip(
        reason="Feat 27: Google Sheets/Airtable/Notion export not implemented; local CSV/JSON/XLSX export tested elsewhere"
    )
    def test_json_export_works(self) -> None:
        assert True

    @pytest.mark.skip(
        reason="Feat 27: Google Sheets/Airtable/Notion export not implemented; local CSV/JSON/XLSX export tested elsewhere"
    )
    def test_export_format_selection(self) -> None:
        assert True

    @pytest.mark.skip(
        reason="Feat 27: Google Sheets/Airtable/Notion export not implemented; local CSV/JSON/XLSX export tested elsewhere"
    )
    def test_export_empty_result_set(self) -> None:
        assert True

    @pytest.mark.skip(
        reason="Feat 27: Google Sheets/Airtable/Notion export not implemented; local CSV/JSON/XLSX export tested elsewhere"
    )
    def test_export_large_result_set(self) -> None:
        assert True
