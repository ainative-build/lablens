"""Plausibility validation for extracted lab values.

Defends against prompt injection (Finding #13) and validates LLM-extracted
reference ranges (Finding #14). Values outside human-possible bounds are flagged.
"""

import logging

from lablens.models.lab_report import LabReport, LabValue

logger = logging.getLogger(__name__)

# Analyte-specific physiological limits (LOINC-keyed).
# Tighter than _UNIT_BOUNDS. Overrides generic unit bounds when available.
# All bounds are "hard impossible" — no clinical/demographic adjustments.
HUMAN_POSSIBLE_BOUNDS: dict[str, tuple[float, float]] = {
    # CBC
    "6690-2": (0.1, 500.0),    # WBC K/uL
    "718-7": (1.0, 30.0),      # Hemoglobin g/dL
    "4544-3": (5.0, 100.0),    # Hematocrit %
    "777-3": (1.0, 5000.0),    # Platelets K/uL
    # BMP / electrolytes
    "2345-7": (1.0, 5000.0),   # Glucose mg/dL
    "2951-2": (80.0, 200.0),   # Sodium mmol/L
    "2823-3": (1.0, 15.0),     # Potassium mmol/L
    "17861-6": (0.1, 30.0),    # Calcium mg/dL
    # Kidney
    "2160-0": (0.01, 100.0),   # Creatinine mg/dL
    "33914-3": (2.0, 200.0),   # eGFR mL/min/1.73m2
    "3094-0": (0.5, 200.0),    # BUN mg/dL
    # Liver enzymes
    "1742-6": (1.0, 20000.0),  # ALT U/L
    "1920-8": (1.0, 20000.0),  # AST U/L
    "6768-6": (1.0, 5000.0),   # ALP U/L
    "2324-2": (1.0, 10000.0),  # GGT U/L
    # Lipids
    "2093-3": (10.0, 2000.0),  # Total Cholesterol mg/dL
    "2571-8": (10.0, 50000.0), # Triglycerides mg/dL
    "2085-9": (1.0, 500.0),    # HDL mg/dL
    "13457-7": (1.0, 1000.0),  # LDL mg/dL
    # Thyroid
    "3016-3": (0.001, 500.0),  # TSH mIU/L
    # Vitamins / minerals
    "1989-3": (1.0, 500.0),    # Vitamin D ng/mL
    "2132-9": (10.0, 100000.0),# Vitamin B12 pg/mL
    "2284-8": (0.5, 100.0),    # Folate ng/mL
    "2498-4": (1.0, 2000.0),   # Iron ug/dL
    "2276-4": (1.0, 100000.0), # Ferritin ng/mL
    # Inflammatory
    "1988-5": (0.01, 1000.0),  # CRP mg/L
    # Other
    "3084-1": (0.1, 50.0),     # Uric Acid mg/dL
    "4548-4": (1.0, 25.0),     # HbA1c %
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
