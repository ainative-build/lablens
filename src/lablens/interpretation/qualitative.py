"""Qualitative (non-numeric) lab value interpretation.

LOINC-aware dispatch for assay-native semantics.
Returns dict of InterpretedResult fields (no separate dataclass).
Falls back to keyword matching for unmapped tests.
"""

import logging

from lablens.knowledge.rules_loader import load_qualitative_rules

logger = logging.getLogger(__name__)

# Fallback keyword sets for unmapped LOINCs (preserved from original)
# NOTE: "normal" omitted — value_aliases maps it to "negative" before lookup
NORMAL_QUALITATIVE = {
    "negative", "non-reactive", "nonreactive", "not detected",
    "absent", "clear", "âm tính", "négatif",
}
ABNORMAL_QUALITATIVE = {
    "positive", "reactive", "abnormal", "detected", "present",
    "dương tính", "positif",
}

# Semi-quantitative aliases: OCR variants → canonical grade
_SEMI_QUANT_ALIASES: dict[str, str] = {
    "+": "1+", "++": "2+", "+++": "3+", "++++": "4+",
}
_SEMI_QUANT_ORDER = ["trace", "1+", "2+", "3+", "4+"]

# Module-level cache for test-name fallback index
_test_name_index: dict[str, dict] | None = None


def _build_test_name_index(tests: dict) -> dict[str, dict]:
    """Build normalized test_name → rule dict for loinc_code=None fallback."""
    index: dict[str, dict] = {}
    for _loinc, rule in tests.items():
        name = rule.get("test_name", "").strip().lower()
        if name:
            index[name] = rule
    return index


def _make_result(
    direction: str,
    confidence: str,
    severity: str,
    actionability: str,
    is_panic: bool,
    note: str,
    context: str = "",
) -> dict:
    """Build result dict with all fields needed by InterpretedResult."""
    return {
        "direction": direction,
        "confidence": confidence,
        "severity": severity,
        "actionability": actionability,
        "is_panic": is_panic,
        "evidence_trace": {
            "note": note,
            "explanation_hint": context,
            "severity_source": "qualitative-rule",
        },
    }


def _grade_gte(grade: str, threshold: str) -> bool:
    """True if grade >= threshold in semi-quantitative order."""
    try:
        return _SEMI_QUANT_ORDER.index(grade) >= _SEMI_QUANT_ORDER.index(threshold)
    except ValueError:
        return False


def interpret_qualitative(
    value: str,
    flag: str | None,
    loinc_code: str | None = None,
    test_name: str | None = None,
) -> dict:
    """Interpret non-numeric qualitative lab value.

    Returns dict with keys: direction, confidence, severity, actionability,
    is_panic, range_source, evidence_trace.
    Caller merges into InterpretedResult.
    """
    global _test_name_index
    rules = load_qualitative_rules()
    tests = rules.get("tests", {})
    value_aliases = rules.get("value_aliases", {})

    # Normalize value (single boundary for alias resolution)
    val_lower = str(value).strip().lower()
    val_canonical = value_aliases.get(val_lower, val_lower)

    # Also normalize via semi_quant_canonical from YAML
    semi_quant_map = rules.get("semi_quant_canonical", {})
    if val_canonical in semi_quant_map:
        val_canonical = semi_quant_map[val_canonical]

    # LOINC-aware dispatch
    rule = None
    method = "qualitative-fallback"
    if loinc_code and loinc_code in tests:
        rule = tests[loinc_code]
        method = "qualitative-loinc"
    elif test_name:
        # Test-name fallback when LOINC is None
        if _test_name_index is None:
            _test_name_index = _build_test_name_index(tests)
        rule = _test_name_index.get(test_name.strip().lower())
        if rule:
            method = "qualitative-name-fallback"

    if rule:
        result = _interpret_with_rule(rule, val_canonical, flag)
    else:
        result = _interpret_fallback(val_canonical, flag)

    result["range_source"] = "qualitative-rule" if rule else "no-range"
    result["evidence_trace"]["interpretation_method"] = method
    result["evidence_trace"]["loinc_code"] = loinc_code
    return result


def _interpret_with_rule(rule: dict, val: str, flag: str | None) -> dict:
    """Dispatch to category-specific interpreter."""
    category = rule.get("category", "expected_negative")
    if category == "categorical":
        return _interpret_categorical(rule, val)
    elif category == "semi_quantitative":
        return _interpret_semi_quantitative(rule, val, flag)
    elif category == "expected_positive":
        return _interpret_expected_positive(rule, val, flag)
    else:
        return _interpret_expected_negative(rule, val, flag)


def _interpret_categorical(rule: dict, val: str) -> dict:
    """Blood type, Rh, pregnancy — always in-range, informational."""
    return _make_result(
        direction="in-range",
        confidence="high",
        severity="normal",
        actionability="routine",
        is_panic=False,
        note=f"Categorical result: {val}",
        context=rule.get("explanation_context", ""),
    )


def _interpret_expected_negative(rule: dict, val: str, flag: str | None) -> dict:
    """HBsAg, HCV, HIV etc. — positive = abnormal."""
    if val in NORMAL_QUALITATIVE:
        return _make_result(
            direction=rule.get("negative_direction", "in-range"),
            confidence="high",
            severity="normal",
            actionability="routine",
            is_panic=False,
            note="Expected negative result",
            context=rule.get("explanation_context", ""),
        )
    if val in ABNORMAL_QUALITATIVE:
        sev = rule.get("severity_when_positive", "moderate")
        return _make_result(
            direction=rule.get("positive_direction", "high"),
            confidence="high",
            severity=sev,
            actionability=rule.get("actionability_when_positive", "follow-up"),
            is_panic=(sev == "critical"),
            note="Abnormal positive result",
            context=rule.get("explanation_context", ""),
        )
    return _make_result(
        "indeterminate", "low", "normal", "routine", False,
        f"Unknown qualitative value: {val}",
    )


def _interpret_expected_positive(rule: dict, val: str, flag: str | None) -> dict:
    """HBsAb — INVERTED: positive = normal (immune)."""
    if val in ABNORMAL_QUALITATIVE:
        return _make_result(
            direction=rule.get("positive_direction", "in-range"),
            confidence="high",
            severity="normal",
            actionability="routine",
            is_panic=False,
            note=f"Expected positive result ({rule.get('normal_status', 'normal')})",
            context=rule.get("explanation_context", ""),
        )
    if val in NORMAL_QUALITATIVE:
        return _make_result(
            direction=rule.get("negative_direction", "high"),
            confidence="high",
            severity=rule.get("severity_when_abnormal", "mild"),
            actionability=rule.get("actionability_when_abnormal", "follow-up"),
            is_panic=False,
            note=f"Abnormal negative result ({rule.get('abnormal_status', 'abnormal')})",
            context=rule.get("explanation_context", ""),
        )
    return _make_result(
        "indeterminate", "low", "normal", "routine", False,
        f"Unknown value for expected-positive test: {val}",
    )


def _interpret_semi_quantitative(rule: dict, val: str, flag: str | None) -> dict:
    """Urinalysis dipstick: trace/1+/2+/3+/4+ with per-analyte normal values."""
    normal_values = set(rule.get("normal_values", ["negative"]))
    grade_severity = rule.get("grade_severity", {})

    # val is already canonicalized by semi_quant_canonical in interpret_qualitative()
    normalized = val

    if normalized in normal_values or val in normal_values:
        sev = grade_severity.get(normalized, "normal")
        return _make_result(
            direction="in-range",
            confidence="high",
            severity=sev,
            actionability="routine",
            is_panic=False,
            note=f"Normal for this analyte ({normalized})",
            context=rule.get("explanation_context", ""),
        )

    # Abnormal grade
    sev = grade_severity.get(normalized, "mild")
    act_threshold = rule.get("actionability_threshold", "1+")
    act = "follow-up" if _grade_gte(normalized, act_threshold) else "routine"
    return _make_result(
        direction="high",
        confidence="high",
        severity=sev,
        actionability="urgent" if sev == "critical" else act,
        is_panic=(sev == "critical"),
        note=f"Abnormal grade: {normalized} (severity: {sev})",
        context=rule.get("explanation_context", ""),
    )


def _interpret_fallback(val: str, flag: str | None) -> dict:
    """Keyword-only fallback for unmapped LOINCs. Preserves existing behavior."""
    if val in NORMAL_QUALITATIVE:
        return _make_result(
            "in-range", "medium", "normal", "routine", False,
            "Qualitative interpretation (keyword fallback)",
        )
    if val in ABNORMAL_QUALITATIVE:
        return _make_result(
            "high", "medium", "mild", "routine", False,
            "Qualitative interpretation (keyword fallback)",
        )
    normalized = _SEMI_QUANT_ALIASES.get(val, val)
    if normalized in _SEMI_QUANT_ORDER:
        return _make_result(
            "high", "low", "normal", "routine", False,
            "Semi-quantitative (keyword fallback)",
        )
    if flag and flag.upper() in ("H", "A"):
        return _make_result(
            "high", "low", "normal", "routine", False,
            "Flag-based fallback",
        )
    if flag and flag.upper() == "L":
        return _make_result(
            "low", "low", "normal", "routine", False,
            "Flag-based fallback",
        )
    return _make_result(
        "indeterminate", "low", "normal", "routine", False,
        f"Unknown qualitative value: {val}",
    )
