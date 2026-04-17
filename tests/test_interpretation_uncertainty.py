"""Phase 1 — classification_state uncertainty tagging.

Covers the judge-review P0 fix: never force "mild abnormal" onto an analyte
we have no clinical rule for. Rows fall into one of three states:
  - classified          (trustworthy direction + severity)
  - low_confidence      (direction kept, severity suppressed to normal)
  - could_not_classify  (direction is indeterminate; can't call it)
"""

import pytest

from lablens.interpretation.engine import InterpretationEngine


@pytest.fixture
def engine():
    return InterpretationEngine()


# --- Baseline: curated rule present ---


def test_curated_calcium_in_range_classified(engine):
    """Curated Calcium with in-range value → classified / normal."""
    values = [{
        "test_name": "Calcium", "value": 9.2, "unit": "mg/dL",
        "loinc_code": "17861-6",
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.direction == "in-range"
    assert r.severity == "normal"
    assert r.classification_state == "classified"


def test_curated_calcium_out_of_range_classified(engine):
    """Curated Calcium out-of-range uses curated bands → classified / mild."""
    values = [{
        "test_name": "Calcium", "value": 11.0, "unit": "mg/dL",
        "loinc_code": "17861-6",
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.direction == "high"
    assert r.severity in ("mild", "moderate")
    assert r.classification_state == "classified"


def test_curated_calcium_moderate_high(engine):
    """11.6-13.0 falls in moderate_high band → moderate, classified."""
    values = [{
        "test_name": "Calcium", "value": 12.0, "unit": "mg/dL",
        "loinc_code": "17861-6",
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.direction == "high"
    assert r.severity == "moderate"
    assert r.classification_state == "classified"


# --- Uncertainty gate: no curated rule ---


def test_no_curated_rule_in_range_baseline(engine):
    """No curated rule + in-range lab value → classified / normal (no gate fire)."""
    values = [{
        "test_name": "Mystery Analyte", "value": 5.0, "unit": "mg/dL",
        "loinc_code": None,
        "ref_range_low": 1.0, "ref_range_high": 10.0,
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.direction == "in-range"
    assert r.severity == "normal"
    assert r.classification_state == "classified"


def test_no_curated_rule_out_of_range_high_trust_gate_fires(engine):
    """No curated rule + high-trust lab range + out-of-range → low_confidence.

    Direction still reported, severity suppressed to normal — the gate's
    whole point is refusing to call "mild abnormal" without rule support.
    """
    values = [{
        "test_name": "Mystery Analyte", "value": 15.0, "unit": "mg/dL",
        "loinc_code": None,
        "ref_range_low": 1.0, "ref_range_high": 10.0,
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.direction == "high"
    assert r.severity == "normal"
    assert r.actionability == "routine"
    assert r.is_panic is False
    assert r.classification_state == "low_confidence"


def test_no_curated_rule_out_of_range_low_trust_gate_fires(engine):
    """Low-trust lab range + out-of-range + no curated rule → low_confidence."""
    values = [{
        "test_name": "Mystery Analyte", "value": 0.1, "unit": "mg/dL",
        "loinc_code": None,
        "ref_range_low": 1.0, "ref_range_high": 10.0,
    }]
    report = engine.interpret_report(values, {0: "low"})
    r = report.values[0]
    assert r.direction == "low"
    assert r.severity == "normal"
    assert r.classification_state == "low_confidence"


# --- could_not_classify: missing data paths ---


def test_empty_unit_could_not_classify(engine):
    """Unit is empty and no range → could_not_classify."""
    values = [{
        "test_name": "Orphan", "value": 42, "unit": "",
        "loinc_code": None,
    }]
    report = engine.interpret_report(values, {0: "low"})
    r = report.values[0]
    assert r.direction == "indeterminate"
    assert r.classification_state == "could_not_classify"


def test_no_range_no_flag_could_not_classify(engine):
    """Unit present but no range, no flag → catch-all could_not_classify."""
    values = [{
        "test_name": "Orphan", "value": 42, "unit": "mg/dL",
        "loinc_code": None,
    }]
    report = engine.interpret_report(values, {0: "low"})
    r = report.values[0]
    assert r.direction == "indeterminate"
    assert r.classification_state == "could_not_classify"


def test_ocr_flag_fallback_still_classified(engine):
    """Unit present + OCR flag (H/L) + no range → flag classifies direction.

    This path does NOT stamp could_not_classify — we have a signal, so the
    engine keeps it as a low-confidence classified row (existing behavior).
    """
    values = [{
        "test_name": "Orphan", "value": 42, "unit": "mg/dL",
        "loinc_code": None, "flag": "H",
    }]
    report = engine.interpret_report(values, {0: "low"})
    r = report.values[0]
    assert r.direction == "high"
    # Not stamped as could_not_classify — flag gave us a direction.
    assert r.classification_state != "could_not_classify"


# --- Qualitative propagation ---


def test_qualitative_unknown_value_could_not_classify(engine):
    """Unmapped qualitative string → fallback stamps could_not_classify."""
    values = [{
        "test_name": "Mystery Serology", "value": "weakly suspicious",
        "unit": None, "loinc_code": None,
    }]
    report = engine.interpret_report(values, {0: "low"})
    r = report.values[0]
    assert r.direction == "indeterminate"
    assert r.classification_state == "could_not_classify"


def test_qualitative_known_negative_classified(engine):
    """Known qualitative value → classified (baseline, no regression)."""
    values = [{
        "test_name": "HIV Screening", "value": "Negative",
        "unit": None, "loinc_code": "75622-1",
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.direction == "in-range"
    assert r.classification_state == "classified"
