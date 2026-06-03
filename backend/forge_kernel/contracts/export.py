"""
Export contract — canonical model for export artifacts.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExportArtifact(BaseModel):
    """Describes a completed export artifact."""

    format: str = Field(..., description="'csv', 'json', or 'xlsx'")
    path: str = Field(default="", description="File path if stored on disk")
    row_count: int = 0
    generated_at: str = Field(default="", description="ISO timestamp")
    byte_size: Optional[int] = None
