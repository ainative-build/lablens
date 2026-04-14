"""Tests for PDF extraction pipeline components."""

import pytest

from lablens.extraction.ocr_extractor import OCRExtractor
from lablens.extraction.pii_stripper import strip_pii_from_report, strip_pii_from_text
from lablens.extraction.plausibility_validator import (
    check_value_plausibility,
    run_all_plausibility_checks,
    validate_reference_range,
)
from lablens.extraction.response_parser import deduplicate_values, validate_extraction
from lablens.models.lab_report import LabReport, LabValue


# --- Response parser ---


def test_validate_empty_report():
    report = LabReport(values=[])
    warnings = validate_extraction(report)
    assert "No lab values extracted" in warnings


def test_validate_missing_unit():
    report = LabReport(values=[LabValue(test_name="Glucose", value=100, unit=None)])
    warnings = validate_extraction(report)
    assert any("missing unit" in w for w in warnings)


def test_validate_complete_report():
    report = LabReport(
        values=[LabValue(test_name="Glucose", value=100, unit="mg/dL")]
    )
    warnings = validate_extraction(report)
    assert len(warnings) == 0


def test_deduplicate_values():
    values = [
        LabValue(test_name="Glucose", value=100, unit="mg/dL"),
        LabValue(test_name="Glucose", value=100, unit="mg/dL"),
        LabValue(test_name="BUN", value=15, unit="mg/dL"),
    ]
    result = deduplicate_values(values)
    assert len(result) == 2


def test_deduplicate_keeps_different_values():
    values = [
        LabValue(test_name="Glucose", value=100, unit="mg/dL"),
        LabValue(test_name="Glucose", value=200, unit="mg/dL"),
    ]
    result = deduplicate_values(values)
    assert len(result) == 2


# --- JSON parser ---


def test_parse_json_with_fences():
    raw = '```json\n{"values": [{"test_name": "WBC", "value": 7.5}]}\n```'
    result = OCRExtractor._parse_json_response(raw)
    assert result is not None
    assert result["values"][0]["test_name"] == "WBC"


def test_parse_json_plain():
    raw = '{"values": [{"test_name": "RBC", "value": 4.5}]}'
    result = OCRExtractor._parse_json_response(raw)
    assert result["values"][0]["value"] == 4.5


def test_parse_json_invalid():
    raw = "This is not JSON at all"
    result = OCRExtractor._parse_json_response(raw)
    assert result is None


# --- PII stripper ---


def test_pii_strip_clears_patient_id():
    report = LabReport(
        patient_id="12345678",
        raw_text="Patient John Smith, DOB 01/15/1990",
        values=[LabValue(test_name="Glucose", value=100, unit="mg/dL")],
    )
    stripped = strip_pii_from_report(report)
    assert stripped.patient_id is None
    assert stripped.raw_text is None
    # Original unchanged
    assert report.patient_id == "12345678"


def test_pii_strip_text_email():
    text = "Patient email: john@example.com"
    result = strip_pii_from_text(text)
    assert "[EMAIL]" in result
    assert "john@example.com" not in result


def test_pii_strip_text_phone():
    text = "Phone: 555-123-4567"
    result = strip_pii_from_text(text)
    assert "[PHONE]" in result


# --- Plausibility validator ---


def test_plausibility_normal_value():
    v = LabValue(test_name="WBC", value=7.5, unit="K/uL", loinc_code="6690-2")
    warnings = check_value_plausibility(v)
    assert len(warnings) == 0


def test_plausibility_impossible_value():
    v = LabValue(test_name="WBC", value=99999, unit="K/uL", loinc_code="6690-2")
    warnings = check_value_plausibility(v)
    assert len(warnings) == 1
    assert "Plausibility fail" in warnings[0]


def test_plausibility_non_numeric():
    v = LabValue(test_name="HIV", value="Negative", unit=None, loinc_code="6690-2")
    warnings = check_value_plausibility(v)
    assert len(warnings) == 0


def test_plausibility_unknown_loinc():
    v = LabValue(test_name="Unknown", value=999, unit="U/L", loinc_code="99999-9")
    warnings = check_value_plausibility(v)
    assert len(warnings) == 0  # No bounds defined, passes through


def test_reference_range_valid():
    v = LabValue(
        test_name="Glucose",
        value=100,
        reference_range_low=70,
        reference_range_high=100,
    )
    warnings = validate_reference_range(v)
    assert len(warnings) == 0


def test_reference_range_inverted():
    v = LabValue(
        test_name="Glucose",
        value=100,
        reference_range_low=200,
        reference_range_high=100,
    )
    warnings = validate_reference_range(v)
    assert len(warnings) == 1
    assert v.reference_range_low is None
    assert v.reference_range_high is None


def test_reference_range_negative():
    v = LabValue(
        test_name="Glucose",
        value=100,
        reference_range_low=-10,
        reference_range_high=100,
    )
    warnings = validate_reference_range(v)
    assert len(warnings) == 1
    assert v.reference_range_low is None


def test_run_all_plausibility_checks():
    report = LabReport(
        values=[
            LabValue(test_name="WBC", value=7.5, unit="K/uL", loinc_code="6690-2"),
            LabValue(
                test_name="Glucose",
                value=100,
                unit="mg/dL",
                loinc_code="2345-7",
                reference_range_low=70,
                reference_range_high=100,
            ),
        ]
    )
    warnings = run_all_plausibility_checks(report)
    assert len(warnings) == 0
