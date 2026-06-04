"""
Domain contracts — canonical models for the product kernel.

All cross-module data flows use these contracts.
No experimental / research fields leak into these models.
"""

from forge_kernel.contracts.analysis import AnalyzeUrlResponse, ExtractionAttempt
from forge_kernel.contracts.export import ExportArtifact
from forge_kernel.contracts.job import (
    CreateJobRequest,
    FilterOperator,
    FilterRule,
    Job,
    JobStatus,
    LogEntry,
    SchemaField,
    ScrapeMode,
    SourcePolicy,
)
from forge_kernel.contracts.result import FailureState, QualityReport, ResultRecord

__all__ = [
    "AnalyzeUrlResponse",
    "CreateJobRequest",
    "ExportArtifact",
    "ExtractionAttempt",
    "FailureState",
    "FilterOperator",
    "FilterRule",
    "Job",
    "JobStatus",
    "LogEntry",
    "QualityReport",
    "ResultRecord",
    "SchemaField",
    "ScrapeMode",
    "SourcePolicy",
]
