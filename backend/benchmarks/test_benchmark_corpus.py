#!/usr/bin/env python3
"""
Comprehensive Benchmark Corpus Suite for DataForge Scraper.

Validates the extraction engine across:
- Static HTML (books, quotes, tables, cards)
- JS-rendered Pages (delayed content, lazy loading)
- Pagination (next-page, infinite scroll)
- Bad HTML (malformed tags, missing fields)
- Schema Extraction (product, person, article)
- Network Payload Extraction (JSON endpoints)
- Failure Cases (auth, CAPTCHA, empty page, blocked page)

Calculates precision, recall, F1, field accuracy, record completeness,
runtime, timeout rate, and zero-result classification accuracy, enforcing
the strict target thresholds.
"""

from __future__ import annotations

import logging
import os
import sys

# Ensure backend is in the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger(__name__)
