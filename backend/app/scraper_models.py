"""Scraping models — data structures used by the scraping engine.

Extracted from ``scraper.py`` during the Phase C refactoring.

Provides:
- ``ScrapeAttemptResult`` — list subclass carrying rich scrape metadata
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.zero_result_classifier import ZeroResultClassification


class ScrapeAttemptResult(list):
    """Subclass of list that holds rich metadata about a scrape attempt.

    Behaves as a plain list of records for backward compatibility while
    carrying context about how the page was fetched, extracted, and classified.
    """

    def __init__(
        self,
        records: list[dict],
        html: str | None = None,
        final_url: str | None = None,
        fetch_method: str | None = None,
        extraction_method: str | None = None,
        telemetry: Any = None,
        zero_result_classification: ZeroResultClassification | None = None,
        acquisition_lineage: dict | None = None,
        anti_bot_score: float = 0.0,
        data_evidence_score: float = 0.0,
        recommended_next_action: str = "",
        warnings: list[str] | None = None,
        network_diagnostics: list[str] | None = None,
    ) -> None:
        super().__init__(records)
        self.html = html
        self.final_url = final_url
        self.fetch_method = fetch_method
        self.extraction_method = extraction_method
        self.telemetry = telemetry
        self.zero_result_classification = zero_result_classification
        self.acquisition_lineage = acquisition_lineage
        self.anti_bot_score = anti_bot_score
        self.data_evidence_score = data_evidence_score
        self.recommended_next_action = recommended_next_action
        self.warnings = warnings or []
        self.network_diagnostics = network_diagnostics or []

    def to_telemetry_dict(self) -> dict:
        """Return scrape metadata as a dict for diagnostics."""
        return {
            "records": len(self),
            "html_length": len(self.html) if self.html else 0,
            "final_url": self.final_url,
            "fetch_method": self.fetch_method,
            "extraction_method": self.extraction_method,
            "anti_bot_score": self.anti_bot_score,
            "data_evidence_score": self.data_evidence_score,
            "recommended_next_action": self.recommended_next_action,
            "zero_result_classification": (
                self.zero_result_classification.to_dict() if self.zero_result_classification else None
            ),
            "warnings": self.warnings,
        }
