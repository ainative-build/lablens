"""HPLC section semantic validation for HbA1c NGSP/IFCC/eAG.

The HPLC (Electrophoresis) subsection in lab reports has a compact layout
where HbA1c NGSP, IFCC, and eAG values/units/ranges sit close together.
Generic OCR row extraction commonly scrambles ranges across these analytes.

This module validates unit-value consistency and clears implausible ranges
from OCR output. It does NOT change test names, values, or units — only
ranges that fail semantic checks.
"""

import logging

logger = logging.getLogger(__name__)

# Rules for HPLC analytes: expected unit and plausible value ranges.
# Used to detect range scrambling from adjacent rows.
_HPLC_RULES: list[dict] = [
    {
        "pattern": "hba1c",
        "exclude": ["ifcc"],
        "expected_unit": "%",
        "value_range": (3.0, 15.0),
    },
    {
        "pattern": "hba1c",
        "require": ["ifcc"],
        "expected_unit": "mmol/mol",
        "value_range": (10.0, 150.0),
    },
    {
        "pattern": "estimated average glucose",
        "expected_units": ["mmol/l", "mg/dl"],
        "value_range_by_unit": {
            "mmol/l": (3.0, 20.0),
            "mg/dl": (50.0, 400.0),
        },
    },
]


def validate_hplc_semantics(v: dict) -> dict:
    """Validate and fix HPLC section values (HbA1c NGSP, IFCC, eAG).

    Clears implausible ranges that result from OCR grabbing adjacent rows
    in the compact HPLC layout. Does NOT change test_name, value, or unit.
    """
    name = (v.get("test_name") or "").lower()
    unit = (v.get("unit") or "").strip().lower()
    ref_low = v.get("reference_range_low")
    ref_high = v.get("reference_range_high")

    for rule in _HPLC_RULES:
        if rule["pattern"] not in name:
            continue
        if "require" in rule and not any(r in name for r in rule["require"]):
            continue
        if "exclude" in rule and any(e in name for e in rule["exclude"]):
            continue

        # Check unit consistency
        expected = rule.get("expected_unit")
        expected_units = rule.get("expected_units", [expected] if expected else [])
        if unit and expected_units and unit not in [u.lower() for u in expected_units]:
            logger.info(
                "HPLC semantic: %s has unit '%s', expected %s — clearing ranges",
                v.get("test_name", "?"), unit, expected_units,
            )
            v["reference_range_low"] = None
            v["reference_range_high"] = None
            return v

        # Check if range is plausible for this analyte+unit
        if ref_low is not None and ref_high is not None:
            try:
                low_f, high_f = float(ref_low), float(ref_high)
            except (ValueError, TypeError):
                break

            # Get expected value range
            vr = rule.get("value_range")
            if not vr and "value_range_by_unit" in rule:
                vr = rule["value_range_by_unit"].get(unit)
            if vr:
                range_mid = (low_f + high_f) / 2
                if range_mid < vr[0] * 0.5 or range_mid > vr[1] * 2:
                    logger.info(
                        "HPLC semantic: %s range [%s-%s] implausible for %s "
                        "(expected value range %s) — clearing",
                        v.get("test_name", "?"), ref_low, ref_high, unit, vr,
                    )
                    v["reference_range_low"] = None
                    v["reference_range_high"] = None
                    return v
        break

    return v
