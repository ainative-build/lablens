"""Section type enum and classification metadata.

Defines the 5 section types for document-aware routing (Contract A).
"""

from dataclasses import dataclass, field
from enum import Enum


class SectionType(str, Enum):
    """Section types for lab report pages/sub-blocks."""

    STANDARD_LAB_TABLE = "standard_lab_table"
    HPLC_DIABETES_BLOCK = "hplc_diabetes_block"
    HORMONE_IMMUNOLOGY_BLOCK = "hormone_immunology_block"
    SCREENING_ATTACHMENT = "screening_attachment"
    APPENDIX_TEXT = "appendix_text"


@dataclass
class ClassifiedBlock:
    """A contiguous block of rows sharing one section type (Contract A).

    Produced by SectionClassifier, consumed by parsers (P2, P3) and pipeline.
    """

    section_type: SectionType
    rows: list[dict]
    confidence: float  # 0.0-1.0
    trigger_keywords: list[str] = field(default_factory=list)
