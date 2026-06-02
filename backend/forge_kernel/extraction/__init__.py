"""
Extraction — deterministic staged pipeline for web data extraction.

Pipeline stages: fetch → extract → quality → clean
Each stage produces typed output that feeds into the next.
"""

from forge_kernel.extraction.fetch import (
    FetchResult,
    FetchStrategy,
    fetch_page_content,
)
from forge_kernel.extraction.pipeline import ExtractionPipeline
from forge_kernel.extraction.quality import (
    build_quality_report,
    score_record_quality,
)

__all__ = [
    "ExtractionPipeline",
    "FetchResult",
    "fetch_page_content",
    "FetchStrategy",
    "score_record_quality",
    "build_quality_report",
]
