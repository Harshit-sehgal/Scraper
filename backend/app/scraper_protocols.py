from __future__ import annotations
from typing import Protocol, List, Dict, Any, Optional
from dataclasses import dataclass, field
from app.models import SchemaField

@dataclass
class ExtractionResult:
    """Deterministic result of an extraction attempt."""
    records: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None

class ExtractionContract(Protocol):
    """Defines the contract for extracting data from a page.
    Implementations must be deterministic and testable.
    """
    
    async def extract(self, url: str, schema_fields: List[SchemaField], **kwargs) -> ExtractionResult:
        """Extract records based on schema fields."""
        ...

class ScraperProtocol(Protocol):
    """Defines the interface for a web scraper cognition engine."""
    
    async def fetch(self, url: str) -> str:
        """Fetch the raw HTML content of a URL."""
        ...
        
    def clean_html(self, html: str) -> str:
        """Clean HTML for semantic processing."""
        ...

    def extract_semantic_graph(self, html: str) -> Any: # Returns SemanticGraph
        """Generate a semantic graph from cleaned HTML."""
        ...
