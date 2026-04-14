"""PDF extraction pipeline — PDF → Canonical Lab JSON."""

from lablens.extraction.ocr_extractor import OCRExtractor
from lablens.extraction.pii_stripper import strip_pii_from_report
from lablens.extraction.plausibility_validator import run_all_plausibility_checks
from lablens.extraction.response_parser import deduplicate_values, validate_extraction

__all__ = [
    "OCRExtractor",
    "deduplicate_values",
    "run_all_plausibility_checks",
    "strip_pii_from_report",
    "validate_extraction",
]
