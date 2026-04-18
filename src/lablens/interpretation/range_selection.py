"""Range selection and direction determination for lab values.

Handles Step 1 (range selection) and Step 2 (direction) of the
8-step interpretation pipeline.
"""

import logging
import re

logger = logging.getLogger(__name__)


def select_range(v: dict, rule: dict | None) -> tuple:
    """Step 1: Lab-provided preferred, curated fallback.

    Cross-validates lab range against curated rule when both exist.
    If curated says in-range but lab says out-of-range, the lab range
    is likely an OCR row-swap — prefer curated.
    """
    low = v.get("reference_range_low", v.get("ref_range_low"))
    high = v.get("reference_range_high", v.get("ref_range_high"))
    value = v.get("value")

    if low is not None and high is not None:
        # Cross-validate against curated if available and value is numeric
        if rule and isinstance(value, (int, float)):
            ranges = rule.get("reference_ranges", [])
            if ranges:
                cur_low = ranges[0]["low"]
                cur_high = ranges[0]["high"]
                lab_says_abnormal = value < low or value > high
                curated_says_in_range = cur_low <= value <= cur_high
                if lab_says_abnormal and curated_says_in_range:
                    logger.info(
                        "Lab range [%s-%s] flags %s as abnormal but curated "
                        "[%s-%s] says in-range — likely OCR row-swap, "
                        "preferring curated for %s",
                        low, high, value, cur_low, cur_high,
                        v.get("test_name", "?"),
                    )
                    return cur_low, cur_high, "curated-fallback"
        return low, high, "lab-provided"
    if rule:
        # Prefer severity_bands.normal over reference_ranges[0]. When a rule
        # has sex-differentiated ranges (Hb, HCT, RBC, Uric Acid, Ferritin,
        # Iron), ranges[0] is male by convention, while severity_bands.normal
        # is the sex-union. Using the male range for sex-unknown patients
        # misclassifies half the population — a female with Hb 12.8 shows
        # as "low" vs male [13.5-17.5] but the band normal=[12.0-17.5]
        # (the clinically correct range) says in-range. The severity pipeline
        # already trusts severity_bands.normal as ground truth; align the
        # direction signal with it so direction and severity stop contradicting.
        bands = rule.get("severity_bands") or {}
        normal = bands.get("normal")
        if normal and "low" in normal and "high" in normal:
            return normal["low"], normal["high"], "curated-fallback"
        ranges = rule.get("reference_ranges", [])
        if ranges:
            default = ranges[0]
            return default["low"], default["high"], "curated-fallback"
    return None, None, "no-range"


def determine_direction(value: float, low: float, high: float) -> str:
    """Step 2: Compare value against reference range."""
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "in-range"


_NUMERIC_RANGE_TEXT = re.compile(r"^\s*([\d.]+)\s*[-–—]\s*([\d.]+)\s*$")


def parse_numeric_range_text(ref_text: str) -> tuple[float, float] | None:
    """Parse a printed 'low - high' numeric range (e.g. '220 - 450').

    Returns (low, high) when the text is a well-formed range with low < high,
    otherwise None. Does not handle comparison operators — that's
    `direction_from_text`'s job.
    """
    if not ref_text:
        return None
    m = _NUMERIC_RANGE_TEXT.match(ref_text.strip())
    if not m:
        return None
    low = float(m.group(1))
    high = float(m.group(2))
    return (low, high) if low < high else None


def direction_from_text(value: float, ref_text: str) -> str | None:
    """Try to extract direction from reference_range_text like '<= 39', '< 200',
    or a printed numeric range like '220 - 450'.

    Returns direction string or None if text is not parseable.
    """
    text = ref_text.strip()
    # Pattern: "< 200", "<= 39", "≤ 39"
    m = re.search(r"[<≤]\s*=?\s*([\d.]+)", text)
    if m:
        threshold = float(m.group(1))
        return "high" if value > threshold else "in-range"
    # Pattern: "> 60", ">= 3.5", "≥ 3.5"
    m = re.search(r"[>≥]\s*=?\s*([\d.]+)", text)
    if m:
        threshold = float(m.group(1))
        return "low" if value < threshold else "in-range"
    # Pattern: "220 - 450" / "220–450" / "220—450" — printed numeric ranges.
    # Safety net for rows where the preprocessor couldn't lift the range into
    # numeric fields; lets _handle_no_range still classify with range-text.
    bounds = parse_numeric_range_text(text)
    if bounds is not None:
        low, high = bounds
        if value < low:
            return "low"
        if value > high:
            return "high"
        return "in-range"
    return None
