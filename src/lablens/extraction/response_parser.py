"""Validate, filter, and deduplicate extracted lab values."""

import logging
import re

from lablens.models.lab_report import LabReport, LabValue

logger = logging.getLogger(__name__)

# --- Noise filter: language-agnostic heuristics ---
# Instead of blacklisting specific noise patterns per language, we define
# what a valid lab result looks like and reject everything else.

# Valid qualitative result values (case-insensitive)
_QUALITATIVE_VALUES = {
    "positive", "negative", "reactive", "non-reactive", "nonreactive",
    "normal", "abnormal", "detected", "not detected", "trace",
    "present", "absent", "borderline", "indeterminate", "equivocal",
    "high", "low", "moderate", "mild", "severe",
    "clear", "cloudy", "turbid", "hazy", "amber", "yellow", "straw",
    "+", "++", "+++", "++++", "1+", "2+", "3+", "4+",
    "âm tính", "dương tính",  # Vietnamese: negative, positive
    "négatif", "positif",  # French
}

# Patterns that indicate metadata/noise in the test_name (language-agnostic)
_METADATA_NAME_PATTERNS = [
    re.compile(r":\s*$"),  # Ends with colon ("Loại mẫu:", "Sample type:")
    re.compile(r"exact name as printed", re.I),  # JSON schema leakage
    re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}"),  # Date as test name
    re.compile(r"^interpretation$", re.I),  # Summary/interpretation label, not a test
]

# Patterns that indicate a value is a date, not a measurement
_DATE_VALUE = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{2,4}$")


def _has_valid_value(v: LabValue) -> bool:
    """Check if the value field looks like a real lab measurement."""
    if isinstance(v.value, (int, float)):
        return True
    val = str(v.value).strip().lower() if v.value is not None else ""
    if not val:
        return False
    if val in _QUALITATIVE_VALUES:
        return True
    # Numeric string (e.g., "6.40" not yet cast to float)
    try:
        float(val)
        return True
    except ValueError:
        pass
    return False


def _is_noise_value(v: LabValue) -> bool:
    """Detect entries that are not real lab results using language-agnostic heuristics.

    A real lab result has: a recognizable test name + a measured value (numeric or
    qualitative like Positive/Negative). Anything else is noise.
    """
    name = v.test_name.strip()
    val_str = str(v.value).strip() if v.value is not None else ""

    # Rule 1: Name too short (single char) or empty
    if len(name) < 2:
        return True

    # Rule 2: Name matches metadata patterns (colon-suffixed labels, schema leaks)
    for pattern in _METADATA_NAME_PATTERNS:
        if pattern.search(name):
            return True

    # Rule 3: No valid measurement value
    if not _has_valid_value(v):
        return True

    # Rule 4: Value looks like a date (metadata leaking into values)
    if isinstance(v.value, str) and _DATE_VALUE.match(val_str):
        return True

    # Rule 5: Value is long free text (>50 chars) — real results are short
    if isinstance(v.value, str) and len(v.value) > 50:
        return True

    # Rule 6: Test name is very long (>80 chars) without units — likely description text
    if len(name) > 80 and not v.unit:
        return True

    return False


def filter_noise_values(values: list[LabValue]) -> list[LabValue]:
    """Remove non-test-result entries that the OCR incorrectly extracted."""
    filtered = []
    for v in values:
        if _is_noise_value(v):
            logger.info("Filtered noise: %s = %s", v.test_name[:60], str(v.value)[:30])
        else:
            filtered.append(v)
    if len(filtered) < len(values):
        logger.info(
            "Noise filter: kept %d/%d values (%d removed)",
            len(filtered), len(values), len(values) - len(filtered),
        )
    return filtered


def validate_extraction(report: LabReport) -> list[str]:
    """Validate extracted report, return list of warnings."""
    warnings = []
    if not report.values:
        warnings.append("No lab values extracted")
        return warnings

    for i, v in enumerate(report.values):
        if v.value is None:
            warnings.append(f"Value #{i} ({v.test_name}): missing value")
        if v.unit is None:
            warnings.append(f"Value #{i} ({v.test_name}): missing unit")
    return warnings


def deduplicate_values(values: list[LabValue]) -> list[LabValue]:
    """Remove exact duplicates (same test_name + value from multi-page overlap)."""
    seen: set[tuple] = set()
    unique = []
    for v in values:
        key = (v.test_name, str(v.value), v.unit)
        if key not in seen:
            seen.add(key)
            unique.append(v)
        else:
            logger.info("Deduplicated: %s = %s", v.test_name, v.value)
    return unique
