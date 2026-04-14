"""Pipeline data contracts — shared between all stages.

Every pipeline stage communicates via these locked Pydantic schemas.
Schema changes require updating all consumers.
"""

from enum import Enum

from pydantic import BaseModel, Field


# --- Stage 1→2: Post-terminology-mapping ---


class NormalizedValue(BaseModel):
    """Analyte after LOINC mapping and unit normalization."""

    test_name: str
    original_name: str  # As extracted from PDF
    value: float | str
    unit: str  # Canonical unit after normalization
    original_unit: str | None = None
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    reference_range_text: str | None = None
    loinc_code: str  # Mapped LOINC code
    loinc_display_name: str = ""
    component: str = ""  # LOINC component (e.g., "Glucose")
    system: str = ""  # LOINC system (e.g., "Ser/Plas")
    mapping_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# --- Stage 2→3: Post-interpretation ---


class Severity(str, Enum):
    NORMAL = "normal"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


class Actionability(str, Enum):
    ROUTINE = "routine"  # No action needed
    MONITOR = "monitor"  # Retest or watch
    CONSULT = "consult"  # See a doctor
    URGENT = "urgent"  # Immediate medical attention


class InterpretedValue(BaseModel):
    """Single analyte after deterministic interpretation."""

    test_name: str
    loinc_code: str
    value: float | str
    unit: str
    direction: str  # "low", "high", "in-range"
    severity: Severity = Severity.NORMAL
    actionability: Actionability = Actionability.ROUTINE
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    rule_id: str | None = None  # Which interpretation rule was applied
    evidence: list["EvidenceTrace"] = []


# --- Stage 3→4: Post-explanation ---


class EvidenceTrace(BaseModel):
    """Provenance record for a single analyte's interpretation."""

    loinc_code: str
    rule_id: str | None = None  # YAML rule that fired
    range_source: str = ""  # Where the reference range came from
    range_citation: str = ""  # Published guideline citation
    graph_context: list[str] = []  # Related conditions from GDB
    education_sources: list[str] = []  # MedlinePlus URLs or IDs


class ExplanationPayload(BaseModel):
    """Patient-friendly explanation for a single analyte."""

    test_name: str
    loinc_code: str
    summary: str  # 1-2 sentence plain-language explanation
    detail: str = ""  # Extended explanation if available
    recommendations: list[str] = []
    education_url: str | None = None  # MedlinePlus link
    language: str = "en"
    evidence: EvidenceTrace | None = None


# --- Final output ---


class AnalysisReport(BaseModel):
    """Complete analysis output — all interpreted values + metadata."""

    report_id: str
    source_language: str = "en"
    patient_id: str | None = None
    report_date: str | None = None
    lab_name: str | None = None
    interpreted_values: list[InterpretedValue] = []
    explanations: list[ExplanationPayload] = []
    coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    total_analytes: int = 0
    interpreted_count: int = 0
    page_count: int = 1
    processing_time_seconds: float = 0.0


# Rebuild forward refs
InterpretedValue.model_rebuild()
