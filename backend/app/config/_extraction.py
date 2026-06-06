"""Extraction, AI structuring, scoring, and quality configuration."""

from pydantic_settings import BaseSettings


class ExtractionSettings(BaseSettings):
    """Extraction, AI structuring, scoring, and quality settings."""

    # ─── Extraction & AI Structuring ───────────────────────────────────
    MAX_RECORDS_PER_SOURCE: int = 25
    """Max records kept from a single URL after scoring / dedup."""
    DEFAULT_MIN_RECORD_SCORE: float = 0.35
    """Default minimum quality score for a record to be accepted."""
    RECORD_ACCEPTANCE_FACTOR: float = 0.8
    """Factor applied to min_record_score for final record acceptance."""
    CONTACT_BOOST_MIN_RECORDS: int = 2
    """Minimum records required to trigger page-level contact boosting."""
    CONTACT_BOOST_THRESHOLD: float = 0.2
    """Percentage of records with contacts below which boosting is triggered."""
    AI_STRUCTURING_CHUNK_SIZE: int = 15
    """Records per chunk when batch-cleaning via LLM."""
    AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES: int = 5
    """Stop trying AI cleaning after this many consecutive failures."""
    AI_CLEAN_TARGET_RECORDS: int = 30
    """Max top-scored records sent to AI cleaning (to save tokens)."""
    SCORE_GATE_THRESHOLD_FACTOR: float = 0.5
    """Factor of min_record_score used as the selector quality gate floor."""
    SCORE_GATE_ABSOLUTE_MIN: float = 0.1
    """Absolute floor for the quality gate threshold."""

    # ─── Insight Engine ───────────────────────────────────────────────
    INSIGHT_MAX_FIELDS: int = 8
    """Max fields suggested by intent parser."""
    INSIGHT_SAMPLE_SIZE: int = 20
    """Number of records used for dataset insight generation."""
    INSIGHT_TEMPERATURE: float = 0.5
    """Temperature for insight generation LLM calls."""

    # ─── URL Analyzer ─────────────────────────────────────────────────
    URL_ANALYZER_MAX_FIELDS: int = 30
    """Max fields returned by the URL analyzer."""
    URL_ANALYZER_SNIPPET_MAX_CHARS: int = 30000
    """Max characters of HTML sent to LLM for URL analysis."""
    URL_ANALYZER_TEMPERATURE: float = 0.5
    """Temperature for URL analysis LLM calls."""
    URL_ANALYZER_TIMEOUT: int = 120
    """Max seconds for URL analysis endpoint."""

    # ─── Scraper Heuristics (Grounding abstractions) ───────────────────
    SELECTOR_SNIPPET_MAX_CHARS: int = 16000
    """Max characters of HTML sent to LLM for selector discovery."""
    REGEX_MAX_CONTAINERS: int = 300
    """Hard limit on containers scanned by regex fallback."""
    SELECTOR_MIN_TEXT_LEN: int = 5
    """Min text length for a node to be considered a data container."""
    SELECTOR_HEADING_FALLBACK_LEN: int = 70
    """Max length of text considered as a heading fallback."""
    NOISE_COHESION_THRESHOLD: float = 0.2
    """Cohesion score below which a record is flagged as noise."""
    NOISE_MIN_VALUES_FOR_REPETITION_CHECK: int = 3
    """Number of identical fields required to trigger template-noise flag."""
    NOISE_SOCIAL_PLATFORM_THRESHOLD: int = 3
    """Number of social platforms seen in a row before flagging as footer noise."""
    CONTACT_VALID_PHONE_MIN_DIGITS: int = 7
    """Min digits for a valid phone number."""
    CONTACT_VALID_PHONE_MAX_DIGITS: int = 15
    """Max digits for a valid phone number."""
    SELECTOR_MEMORY_MAX_FAILURES: int = 3
    """Max consecutive failures for a remembered selector before it's suspended."""

    # ─── Scorer Heuristics ─────────────────────────────────────────────
    SCORE_QUALITY_WEIGHT: float = 0.55
    SCORE_COVERAGE_WEIGHT: float = 0.20
    SCORE_SOURCE_TRUST_WEIGHT: float = 0.15
    SCORE_TYPE_INTEGRITY_WEIGHT: float = 0.10

    # ─── Record Quality Scoring ────────────────────────────────────────
    QUALITY_BASE_SCORE: float = 0.3
    """Base quality score for non-empty text values."""
    QUALITY_TEXT_LEN_THRESHOLD_1: int = 4
    """Text longer than this gets a length bonus (+0.2)."""
    QUALITY_TEXT_LEN_THRESHOLD_2: int = 20
    """Text longer than this gets another length bonus (+0.1)."""
    QUALITY_NOISE_PENALTY: float = 0.6
    """Penalty for noise phrases in identity fields."""
    QUALITY_SHORT_IDENTITY_PENALTY: float = 0.2
    """Penalty for short text in identity fields (< 3 chars)."""
    QUALITY_STATUS_LONG_PENALTY: float = 0.4
    """Penalty for long text in status fields (> 25 chars)."""
    QUALITY_STATUS_MISMATCH_PENALTY: float = 0.2
    """Penalty for status fields without known phrases and long text."""
    QUALITY_PRESENT_FIELD_THRESHOLD: float = 0.2
    """Field quality above this counts as 'present'."""
    QUALITY_REQUIRED_MISSING_THRESHOLD: float = 0.3
    """Required field quality below this increments missing count."""
    QUALITY_REQUIRED_WEIGHT: float = 1.2
    """Weight multiplier for required fields in scoring."""
    QUALITY_PRESENCE_COHESION_THRESHOLD: float = 0.3
    """Presence vote below this triggers a cohesion penalty."""
    QUALITY_PRESENCE_VOTE_WEIGHT: float = 0.3
    """Weight for presence vote in ensemble blend."""
    QUALITY_QUALITY_VOTE_WEIGHT: float = 0.7
    """Weight for quality vote in ensemble blend."""

    # ─── Selector Fallback Extraction ──────────────────────────────────
    SELECTOR_FUZZY_MIN_WORDS: int = 2
    """Min words in example value for fuzzy matching."""
    SELECTOR_FUZZY_MAX_WORDS: int = 5
    """Max words in example value for fuzzy matching."""
    SELECTOR_FUZZY_MATCH_RATIO: float = 0.7
    """Min word match ratio for fuzzy example matching."""
    SELECTOR_CONTEXT_WINDOW_MAX_LEN: int = 120
    """Max characters for context window around fuzzy match."""
    SELECTOR_MIN_SEGMENT_LEN: int = 3
    """Min characters for extracted context segment."""
