"""Pre-processing for OCR-extracted reference ranges and values.

Handles range field parsing, plausibility validation, and threshold-style
range detection before values enter the interpretation pipeline.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Pattern: "3.2 - 7.4", "0.22 - 0.45", etc.
_RANGE_PATTERN = re.compile(r"^\s*([\d.]+)\s*[-–—]\s*([\d.]+)\s*$")
# Pattern: "< 200", "<= 1.7", "≤ 5.0"
_UPPER_BOUND_PATTERN = re.compile(r"^\s*[<≤]\s*=?\s*([\d.]+)\s*$")
# Pattern: "> 60", ">= 3.5", "≥ 3.5"
_LOWER_BOUND_PATTERN = re.compile(r"^\s*[>≥]\s*=?\s*([\d.]+)\s*$")
# Pattern: text with embedded range, e.g. "Normal: 3.2 - 7.4"
_TEXT_RANGE_PATTERN = re.compile(r"([\d.]+)\s*[-–—]\s*([\d.]+)")


def _normalize_decimal_comma(s: str) -> str:
    """Replace decimal commas: '3,2' → '3.2' but NOT '3,200' → '3.200'.

    Comma followed by 1-2 digits (not 3+) is a decimal separator.
    """
    return re.sub(r'(\d),(\d{1,2})(?!\d)', r'\1.\2', s)


def fix_range_fields(v: dict) -> dict:
    """Pre-process reference range fields from LLM output before Pydantic validation.

    Handles cases where the LLM returns range strings instead of separate numbers.
    """
    for field in ("reference_range_low", "reference_range_high"):
        val = v.get(field)
        if val is None or isinstance(val, (int, float)):
            continue
        val = str(val).strip()
        val = _normalize_decimal_comma(val)

        # Try simple "low - high" range pattern
        m = _RANGE_PATTERN.match(val)
        if m:
            v["reference_range_low"] = float(m.group(1))
            v["reference_range_high"] = float(m.group(2))
            if not v.get("reference_range_text"):
                v["reference_range_text"] = val
            return v

        # Try upper bound: "< 200"
        m = _UPPER_BOUND_PATTERN.match(val)
        if m:
            v["reference_range_low"] = None
            v["reference_range_high"] = float(m.group(1))
            if not v.get("reference_range_text"):
                v["reference_range_text"] = val
            return v

        # Try lower bound: "> 60"
        m = _LOWER_BOUND_PATTERN.match(val)
        if m:
            v["reference_range_low"] = float(m.group(1))
            v["reference_range_high"] = None
            if not v.get("reference_range_text"):
                v["reference_range_text"] = val
            return v

        # Try extracting embedded range from text like "Normal: 3.2 - 7.4"
        m = _TEXT_RANGE_PATTERN.search(val)
        if m:
            v["reference_range_low"] = float(m.group(1))
            v["reference_range_high"] = float(m.group(2))
            if not v.get("reference_range_text"):
                v["reference_range_text"] = val
            return v

        # Unparseable — save as text, set numeric to None
        v["reference_range_text"] = val
        v[field] = None

    # Recovery: LLM sometimes emits the printed range only as text (leaving the
    # numeric fields None) — e.g. Uric Acid "220 - 450" ending up in
    # `reference_range_text` alone. Lift the numbers so the engine can classify
    # deterministically instead of dropping to ocr-flag-fallback. Embedded-in-
    # prose and threshold-style ranges are handled downstream (validator clears
    # them when keywords like "Normal:" / "Prediabetes" are present).
    if (
        v.get("reference_range_low") is None
        and v.get("reference_range_high") is None
    ):
        ref_text = v.get("reference_range_text")
        if ref_text and isinstance(ref_text, str):
            text = _normalize_decimal_comma(ref_text.strip())
            m = _RANGE_PATTERN.match(text)
            if m:
                v["reference_range_low"] = float(m.group(1))
                v["reference_range_high"] = float(m.group(2))

    return v


def validate_range_plausibility(v: dict) -> dict:
    """Check if OCR-extracted ranges are plausible for the value.

    Catches row-swap errors where OCR grabs an adjacent row's range.
    If range is implausible, clear it so the engine falls back to curated ranges.
    """
    # Coerce range bounds to float (OCR may return strings)
    for rf in ("reference_range_low", "reference_range_high"):
        rv = v.get(rf)
        if rv is not None and not isinstance(rv, (int, float)):
            try:
                v[rf] = float(rv)
            except (ValueError, TypeError):
                v[rf] = None
    low = v.get("reference_range_low")
    high = v.get("reference_range_high")
    val = v.get("value")

    if low is None or high is None:
        return v

    # Range must be low < high
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        if low >= high:
            logger.info("Clearing inverted range for %s: [%s-%s]", v.get("test_name", "?"), low, high)
            v["reference_range_low"] = None
            v["reference_range_high"] = None
            return v

    # Coerce value to float for comparison (OCR often returns strings like "163")
    if val is not None and not isinstance(val, (int, float)):
        try:
            val = float(val)
        except (ValueError, TypeError):
            return v

    # If value is numeric, check it's within plausible distance of range
    if isinstance(val, (int, float)) and isinstance(low, (int, float)) and isinstance(high, (int, float)):
        try:
            numeric_val = float(val)
            range_mid = (low + high) / 2
            range_span = high - low
            if range_span > 0 and range_mid > 0:
                ratio = numeric_val / range_mid
                if ratio > 10 or ratio < 0.1:
                    logger.info(
                        "Suspicious range for %s: val=%s range=[%s-%s] ratio=%.1f — clearing",
                        v.get("test_name", "?"), val, low, high, ratio,
                    )
                    v["reference_range_low"] = None
                    v["reference_range_high"] = None
        except (ValueError, ZeroDivisionError):
            pass

    # Detect threshold/category-style ranges (e.g. "Desirable: < 1.7")
    ref_text = v.get("reference_range_text", "")
    if ref_text and isinstance(ref_text, str):
        threshold_keywords = (
            "desirable", "optimal", "borderline", "risk", "target",
            "acceptable", "ideal", "goal", "category",
            "prediabetes", "diabetes", "normal:",
        )
        if any(kw in ref_text.lower() for kw in threshold_keywords):
            logger.info(
                "Clearing threshold-style range for %s: text='%s'",
                v.get("test_name", "?"), ref_text,
            )
            v["reference_range_low"] = None
            v["reference_range_high"] = None

    return v


def is_page_suspicious(values: list[dict]) -> bool:
    """Detect if a page's extraction results are suspicious and need re-parsing.

    Suspicious indicators:
    - >50% of values missing units
    - >50% of values missing reference ranges
    - <3 values extracted from a page that likely has more
    """
    if not values:
        return False

    total = len(values)
    if total < 3:
        return True

    missing_units = sum(1 for v in values if not v.get("unit"))
    missing_ranges = sum(
        1 for v in values
        if v.get("reference_range_low") is None and v.get("reference_range_high") is None
    )

    unit_miss_rate = missing_units / total
    range_miss_rate = missing_ranges / total

    if unit_miss_rate > 0.5 or range_miss_rate > 0.5:
        logger.info(
            "Page suspicious: %d values, %.0f%% missing units, %.0f%% missing ranges",
            total, unit_miss_rate * 100, range_miss_rate * 100,
        )
        return True

    return False
