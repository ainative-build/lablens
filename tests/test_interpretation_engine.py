"""Tests for the deterministic interpretation engine."""

import pytest

from lablens.interpretation.engine import InterpretationEngine


@pytest.fixture
def engine():
    return InterpretationEngine()


# --- Step 1: Range selection ---


def test_lab_provided_range_preferred(engine):
    values = [{
        "test_name": "Glucose", "value": 90, "unit": "mg/dL",
        "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100,
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].range_source == "lab-provided-validated"


def test_curated_fallback_range(engine):
    values = [{
        "test_name": "Glucose", "value": 90, "unit": "mg/dL",
        "loinc_code": "2345-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].range_source == "curated-fallback"


def test_no_range_available(engine):
    values = [{
        "test_name": "Unknown", "value": 42, "unit": "mg/dL",
        "loinc_code": None,
    }]
    report = engine.interpret_report(values, {0: "low"})
    assert report.values[0].direction == "indeterminate"
    assert report.values[0].range_source == "no-range"


def test_curated_fallback_uses_sex_union_band_for_hemoglobin(engine):
    """Arabic-report regression: female patient, Hb 12.8 g/dL, no printed range.
    reference_ranges[0] is male-default [13.5-17.5] by convention, but
    severity_bands.normal is the sex-union [12.0-17.5]. Using ranges[0] would
    mark 12.8 as 'low' and the override at engine._apply_severity_and_actionability
    would re-run heuristic_severity → 'moderate'. Must use severity_bands.normal
    so 12.8 lands in-range/normal."""
    values = [{
        "test_name": "Hemoglobin", "value": 12.8, "unit": "g/dL",
        "loinc_code": "718-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.range_source == "curated-fallback"
    assert r.direction == "in-range"
    assert r.severity == "normal"
    assert r.actionability == "routine"


def test_curated_fallback_uses_sex_union_band_for_hematocrit(engine):
    """Arabic-report regression: female patient, HCT 37.0%, no printed range.
    Male range [38.8-50] would mark 37 as low → moderate. Sex-union band
    [36.0-50] says normal."""
    values = [{
        "test_name": "Hematocrit", "value": 37.0, "unit": "%",
        "loinc_code": "4544-3",
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.range_source == "curated-fallback"
    assert r.direction == "in-range"
    assert r.severity == "normal"
    assert r.actionability == "routine"


# --- Step 2: Direction ---


def test_normal_glucose(engine):
    values = [{
        "test_name": "Glucose", "value": 90, "unit": "mg/dL",
        "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100,
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].direction == "in-range"


def test_high_glucose(engine):
    values = [{
        "test_name": "Glucose", "value": 250, "unit": "mg/dL",
        "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100,
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].direction == "high"


def test_low_glucose(engine):
    values = [{
        "test_name": "Glucose", "value": 50, "unit": "mg/dL",
        "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100,
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].direction == "low"


def test_boundary_value_in_range(engine):
    values = [{
        "test_name": "Glucose", "value": 70, "unit": "mg/dL",
        "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100,
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].direction == "in-range"


# --- Step 3: Severity ---


def test_severity_normal(engine):
    values = [{
        "test_name": "Glucose", "value": 85, "unit": "mg/dL",
        "loinc_code": "2345-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].severity == "normal"


def test_severity_mild(engine):
    values = [{
        "test_name": "Glucose", "value": 110, "unit": "mg/dL",
        "loinc_code": "2345-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].severity == "mild"


def test_severity_moderate(engine):
    values = [{
        "test_name": "Glucose", "value": 200, "unit": "mg/dL",
        "loinc_code": "2345-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].severity == "moderate"


def test_severity_critical(engine):
    values = [{
        "test_name": "Glucose", "value": 30, "unit": "mg/dL",
        "loinc_code": "2345-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].severity == "critical"


# --- Non-numeric ---


def test_non_numeric_positive_detected_as_high(engine):
    values = [{
        "test_name": "HIV Screening", "value": "Positive",
        "unit": None, "loinc_code": "75622-1",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].direction == "high"


def test_non_numeric_negative_detected_as_in_range(engine):
    values = [{
        "test_name": "HIV Screening", "value": "Negative",
        "unit": None, "loinc_code": "75622-1",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].direction == "in-range"


# --- Step 5: Actionability ---


def test_actionability_normal(engine):
    values = [{
        "test_name": "Glucose", "value": 85, "unit": "mg/dL",
        "loinc_code": "2345-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].actionability == "routine"


def test_actionability_urgent_on_critical(engine):
    values = [{
        "test_name": "Glucose", "value": 30, "unit": "mg/dL",
        "loinc_code": "2345-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].actionability == "urgent"


# --- Step 6: Confidence ---


def test_confidence_high_all_good(engine):
    values = [{
        "test_name": "Glucose", "value": 85, "unit": "mg/dL",
        "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100,
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].confidence == "high"


def test_confidence_medium_curated_range(engine):
    values = [{
        "test_name": "Glucose", "value": 85, "unit": "mg/dL",
        "loinc_code": "2345-7",
    }]
    report = engine.interpret_report(values, {0: "high"})
    assert report.values[0].confidence == "medium"


def test_confidence_low_no_match(engine):
    values = [{
        "test_name": "Unknown", "value": 42, "unit": "mg/dL",
        "loinc_code": None,
    }]
    report = engine.interpret_report(values, {0: "low"})
    assert report.values[0].confidence == "low"


# --- Step 7: Evidence trace ---


def test_evidence_trace_populated(engine):
    values = [{
        "test_name": "Glucose", "value": 250, "unit": "mg/dL",
        "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100,
    }]
    report = engine.interpret_report(values, {0: "high"})
    trace = report.values[0].evidence_trace
    assert trace["direction"] == "high"
    assert trace["range_source"] == "lab-provided-validated"
    assert trace["match_confidence"] == "high"


# --- Coverage and report ---


def test_coverage_score(engine):
    values = [
        {"test_name": "Glucose", "value": 250, "unit": "mg/dL",
         "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100},
        {"test_name": "BUN", "value": 15, "unit": "mg/dL",
         "loinc_code": "3094-0", "ref_range_low": 7, "ref_range_high": 20},
    ]
    report = engine.interpret_report(values, {0: "high", 1: "high"})
    assert "2/2 analytes parsed" in report.coverage_score


def test_multi_value_report(engine):
    values = [
        {"test_name": "WBC", "value": 7.5, "unit": "K/uL",
         "loinc_code": "6690-2"},
        {"test_name": "RBC", "value": 4.8, "unit": "M/uL",
         "loinc_code": "789-8"},
        {"test_name": "Hemoglobin", "value": 14.0, "unit": "g/dL",
         "loinc_code": "718-7"},
    ]
    report = engine.interpret_report(values, {0: "high", 1: "high", 2: "high"})
    assert report.total_parsed == 3
    assert all(r.direction == "in-range" for r in report.values)


# --- Determinism ---


def test_deterministic_output(engine):
    values = [{
        "test_name": "Glucose", "value": 250, "unit": "mg/dL",
        "loinc_code": "2345-7", "ref_range_low": 70, "ref_range_high": 100,
    }]
    report1 = engine.interpret_report(values, {0: "high"})
    report2 = engine.interpret_report(values, {0: "high"})
    assert report1.values[0].direction == report2.values[0].direction
    assert report1.values[0].severity == report2.values[0].severity
    assert report1.values[0].confidence == report2.values[0].confidence
