"""Startup validation for severity band contiguity (Finding #7).

Checks that severity bands in YAML rules have no gaps that could cause
values to fall through unclassified.
"""

import logging

logger = logging.getLogger(__name__)


def validate_band_contiguity(rules: dict) -> list[str]:
    """Check severity bands in each rule have no gaps.

    Returns list of error messages (empty = all valid).
    """
    errors = []
    for loinc_code, rule in rules.items():
        bands = rule.get("severity_bands", {})
        if not bands:
            continue

        all_ranges = []
        for name, band in bands.items():
            if isinstance(band, dict) and "low" in band and "high" in band:
                all_ranges.append((band["low"], band["high"], name))

        if not all_ranges:
            continue

        all_ranges.sort()

        for i in range(len(all_ranges) - 1):
            _, prev_high, prev_name = all_ranges[i]
            next_low, _, next_name = all_ranges[i + 1]
            # Allow touching or overlapping boundaries
            if next_low > prev_high + 1.0:
                errors.append(
                    f"Rule {loinc_code}: gap between '{prev_name}' "
                    f"(high={prev_high}) and '{next_name}' (low={next_low})"
                )

    if errors:
        for e in errors:
            logger.error("Band contiguity error: %s", e)

    return errors
