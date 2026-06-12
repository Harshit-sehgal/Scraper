# Data Quality

**Date:** 2026-06-13
**Status:** Implemented

---

## Overview

The data quality pipeline provides cleaning, validation, deduplication, and scoring for extracted records.

## 1. Cleaning Rules

| Field Type | Rule |
|------------|------|
| Text | Trim whitespace, normalize spaces |
| Price | Remove currency symbols, convert to float |
| Date | Normalize format |
| URL | Ensure absolute, remove tracking params (utm_, fbclid, gclid) |
| Email | Lowercase, strip |
| Phone | Extract digits |
| Number | Convert to int/float |

## 2. Validation Rules

| Field Type | Validation |
|------------|-----------|
| Email | Contains @ and valid domain |
| URL | Starts with http:// or https:// |
| Phone | 7-15 digits |
| Number | Is int or float |
| Required | Not empty |

## 3. Deduplication

Exact duplicate removal using sorted JSON serialization.

## 4. Quality Score

- Per-record: 0.0 to 1.0 based on field completeness and type validity
- Overall: Average of all records

## 5. Usage

```python
from app.data_quality import run_quality_pipeline
from app.models import FieldType, SchemaField

schema = [
    SchemaField(name="title", field_type=FieldType.STRING, required=True),
    SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
]

result = run_quality_pipeline(records, schema)
# result["valid_records"] — records passing validation
# result["duplicates_removed"] — count
# result["quality_score"] — 0.0 to 1.0
# result["warnings"] — list of warnings
```

## 6. Tests

`backend/tests/test_extraction_depth.py`
