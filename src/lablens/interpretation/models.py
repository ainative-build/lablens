"""Data models for the interpretation engine output."""

from dataclasses import dataclass, field


@dataclass
class InterpretedResult:
    """Single analyte after deterministic interpretation."""

    test_name: str
    loinc_code: str | None
    value: float | str
    unit: str

    # Interpretation
    direction: str = "indeterminate"  # low | high | in-range | indeterminate
    severity: str = "normal"  # normal | mild | moderate | critical
    is_panic: bool = False
    actionability: str = "routine"  # routine | monitor | consult | urgent
    confidence: str = "low"  # high | medium | low

    # Range provenance
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    range_source: str = "no-range"
    # lab-provided-validated | lab-provided-suspicious | curated-fallback
    # | ocr-flag-fallback | range-text | no-range
    range_trust: str = "high"  # high | medium | low
    rule_source: str | None = None
    evidence_trace: dict = field(default_factory=dict)

    # Extraction metadata (carried through from pipeline enrichment)
    section_type: str | None = None
    verification_verdict: str = "accepted"
    unit_confidence: str = "high"
    source_flag: str | None = None  # Raw OCR flag (audit-only, not semantic)

    # Classification state — first-class uncertainty tag surfaced in UI + export.
    #   "classified"         — trustworthy direction + severity
    #   "low_confidence"     — direction kept but severity suppressed to normal
    #                          because rule support is weak (no curated bands,
    #                          unvalidated lab range, etc.)
    #   "could_not_classify" — direction is indeterminate; not enough data
    classification_state: str = "classified"

    # Phase 1a: health-topic tagging (one of the 11 buckets in
    # health_topic_mapper.KNOWN_TOPICS). Stamped by the pipeline after
    # LOINC mapping. None until tagged.
    health_topic: str | None = None


@dataclass
class PanelCompleteness:
    """Track which tests from a panel are present/missing."""

    panel_name: str
    expected: list[str]
    present: list[str]
    missing: list[str]


@dataclass
class InterpretedReport:
    """Full interpretation output for a lab report."""

    values: list[InterpretedResult]
    panels: list[PanelCompleteness]
    total_parsed: int = 0
    total_abnormal: int = 0
    total_explained: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def coverage_score(self) -> str:
        return (
            f"{self.total_parsed}/{self.total_parsed} analytes parsed, "
            f"{self.total_abnormal} abnormal detected"
        )
