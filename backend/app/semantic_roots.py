"""Shared semantic root constants.

Extracted from ``semantic_allocation_engine`` to break the circular
dependency between ``semantic_allocation_engine`` and
``semantic_inference_engine``.  Both modules import from here; neither
imports from the other at module-load time.

These are TEMPORARY priors — learning overrides them over time.
"""

from app.semantic_ir import SemanticType

# Bootstrap seeds for role-type compatibility.
UNIVERSAL_ROOTS: list[tuple[list[str], SemanticType]] = [
    (["pric", "cost", "salar", "preci", "prix", "wert"], SemanticType.PRICE),
    (["date", "time", "schedule", "fecha", "zeit", "horar"], SemanticType.DATE),
    # Short codes / identifiers (product codes, SKUs, etc.)
    (["code", "currenc", "ident", "id", "codig", "sku"], SemanticType.CODE),
    (["loc", "city", "addr", "place", "dest", "orig", "ubica", "stadt"], SemanticType.LOCATION),
    (["nam", "comp", "firm", "brand", "make", "model", "builder", "nombr", "title"], SemanticType.ORGANIZATION),
    (["rat", "scor", "review", "calif", "bewert"], SemanticType.RATING),
    (["count", "number", "year", "mileage", "age", "experien", "num", "jahr"], SemanticType.NUMBER),
    (["avail", "stock", "status", "state"], SemanticType.TEXT),
]
