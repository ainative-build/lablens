"""Plausibility validation for extracted lab values.

Defends against prompt injection (Finding #13) and validates LLM-extracted
reference ranges (Finding #14). Values outside human-possible bounds are flagged.
"""

import logging

from lablens.models.lab_report import LabReport, LabValue

logger = logging.getLogger(__name__)

# Human-possible bounds per LOINC code (absolute physiological limits)
HUMAN_POSSIBLE_BOUNDS: dict[str, tuple[float, float]] = {
    "6690-2": (0.1, 500.0),  # WBC K/uL
    "2345-7": (1.0, 5000.0),  # Glucose mg/dL
    "2160-0": (0.01, 100.0),  # Creatinine mg/dL
    "718-7": (1.0, 30.0),  # Hemoglobin g/dL
    "4544-3": (5.0, 100.0),  # Hematocrit %
    "777-3": (1.0, 5000.0),  # Platelets K/uL
    "2093-3": (10.0, 2000.0),  # Total Cholesterol mg/dL
    "2571-8": (10.0, 50000.0),  # Triglycerides mg/dL
    "2951-2": (80.0, 200.0),  # Sodium mmol/L
    "2823-3": (1.0, 15.0),  # Potassium mmol/L
    "3016-3": (0.001, 500.0),  # TSH mIU/L
}


def check_value_plausibility(v: LabValue) -> list[str]:
    """Check extracted numeric value against human-possible bounds."""
    warnings = []
    if not isinstance(v.value, (int, float)):
        return warnings
    val = float(v.value)
    if v.loinc_code and v.loinc_code in HUMAN_POSSIBLE_BOUNDS:
        lo, hi = HUMAN_POSSIBLE_BOUNDS[v.loinc_code]
        if not (lo <= val <= hi):
            msg = f"Plausibility fail: {v.test_name}={val} outside [{lo},{hi}]"
            warnings.append(msg)
            logger.warning(msg)
    return warnings


def validate_reference_range(v: LabValue) -> list[str]:
    """Validate LLM-extracted reference ranges for consistency."""
    warnings = []
    if v.reference_range_low is None or v.reference_range_high is None:
        return warnings
    if v.reference_range_low >= v.reference_range_high:
        msg = (
            f"Invalid ref range for {v.test_name}: "
            f"low={v.reference_range_low} >= high={v.reference_range_high}. Clearing."
        )
        warnings.append(msg)
        v.reference_range_low = None
        v.reference_range_high = None
        return warnings
    if v.reference_range_low < 0 or v.reference_range_high < 0:
        msg = (
            f"Negative ref range for {v.test_name}: "
            f"[{v.reference_range_low},{v.reference_range_high}]. Clearing."
        )
        warnings.append(msg)
        v.reference_range_low = None
        v.reference_range_high = None
    return warnings


def run_all_plausibility_checks(report: LabReport) -> list[str]:
    """Run value plausibility + range validation on all extracted values."""
    all_warnings = []
    for v in report.values:
        all_warnings.extend(check_value_plausibility(v))
        all_warnings.extend(validate_reference_range(v))
    return all_warnings
