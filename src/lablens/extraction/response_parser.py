"""Validate and deduplicate extracted lab values."""

import logging

from lablens.models.lab_report import LabReport, LabValue

logger = logging.getLogger(__name__)


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
