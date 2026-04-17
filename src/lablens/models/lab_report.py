"""Canonical Lab JSON schema — the extraction output format."""

from enum import Enum

from pydantic import BaseModel


class AbnormalityDirection(str, Enum):
    LOW = "low"
    HIGH = "high"
    IN_RANGE = "in-range"


class LabValue(BaseModel):
    """Single extracted analyte from a lab report."""

    test_name: str
    value: float | str
    unit: str | None = None
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    reference_range_text: str | None = None
    flag: str | None = None  # From PDF (e.g., "H", "L", "A")
    loinc_code: str | None = None  # Filled by terminology mapper
    section_type: str | None = None  # SectionType value, nullable for backward compat


class LabReport(BaseModel):
    """Full extracted lab report in canonical format."""

    source_language: str = "en"
    patient_id: str | None = None
    report_date: str | None = None
    lab_name: str | None = None
    values: list[LabValue] = []
    screening_results: list[dict] = []  # Typed ScreeningResult in Phase 3
    raw_text: str | None = None
    page_count: int = 1
    # Extraction diagnostics — lets the API distinguish "OCR returned nothing"
    # from "parser rejected everything as noise" (common with lab menus or
    # multi-column reports where OCR picked up reference ranges instead of
    # patient values).
    raw_extracted_count: int = 0
    filtered_noise_count: int = 0
