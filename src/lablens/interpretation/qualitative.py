"""Qualitative (non-numeric) lab value interpretation.

Handles interpretation of values like "Positive", "Negative",
"Reactive", semi-quantitative (+, ++, +++), and flag-based fallback.
"""

# Qualitative values indicating normal/expected results
NORMAL_QUALITATIVE = {
    "negative", "non-reactive", "nonreactive", "normal", "not detected",
    "absent", "clear", "âm tính", "négatif",
}

# Qualitative values indicating abnormal/unexpected results
ABNORMAL_QUALITATIVE = {
    "positive", "reactive", "abnormal", "detected", "present",
    "dương tính", "positif",
}


def interpret_qualitative(value: str, flag: str | None) -> tuple[str, str]:
    """Interpret non-numeric qualitative lab values.

    Returns (direction, confidence).
    """
    val_lower = str(value).strip().lower()
    if val_lower in NORMAL_QUALITATIVE:
        return "in-range", "medium"
    if val_lower in ABNORMAL_QUALITATIVE:
        return "high", "medium"
    # Semi-quantitative: +, ++, +++, 1+, 2+, etc.
    if val_lower in {"+", "++", "+++", "++++", "1+", "2+", "3+", "4+"}:
        return "high", "low"
    # Flag-based fallback
    if flag and flag.upper() in ("H", "A"):
        return "high", "low"
    if flag and flag.upper() == "L":
        return "low", "low"
    return "indeterminate", "low"
