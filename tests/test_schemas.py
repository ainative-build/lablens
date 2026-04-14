"""Validate all pipeline data contracts are importable and constructible."""

from lablens.models.lab_report import LabReport, LabValue
from lablens.models.schemas import (
    AnalysisReport,
    EvidenceTrace,
    ExplanationPayload,
    InterpretedValue,
    NormalizedValue,
    Severity,
)


def test_lab_value_minimal():
    v = LabValue(test_name="Glucose", value=95.0)
    assert v.test_name == "Glucose"
    assert v.loinc_code is None


def test_lab_report_with_values():
    report = LabReport(
        source_language="en",
        values=[
            LabValue(test_name="Glucose", value=95.0, unit="mg/dL"),
            LabValue(test_name="HbA1c", value="5.4", unit="%"),
        ],
    )
    assert len(report.values) == 2


def test_normalized_value():
    nv = NormalizedValue(
        test_name="Glucose",
        original_name="GLUCOSE, FASTING",
        value=95.0,
        unit="mg/dL",
        loinc_code="2345-7",
        mapping_confidence=0.95,
    )
    assert nv.loinc_code == "2345-7"


def test_interpreted_value():
    iv = InterpretedValue(
        test_name="Glucose",
        loinc_code="2345-7",
        value=250.0,
        unit="mg/dL",
        direction="high",
        severity=Severity.SEVERE,
        confidence=0.9,
    )
    assert iv.severity == Severity.SEVERE


def test_evidence_trace():
    et = EvidenceTrace(loinc_code="2345-7", rule_id="glucose-high-01")
    assert et.range_source == ""


def test_explanation_payload():
    ep = ExplanationPayload(
        test_name="Glucose",
        loinc_code="2345-7",
        summary="Your blood sugar is elevated.",
    )
    assert "elevated" in ep.summary


def test_analysis_report():
    report = AnalysisReport(
        report_id="test-001",
        total_analytes=5,
        interpreted_count=4,
        coverage_score=0.8,
    )
    assert report.coverage_score == 0.8
    assert report.interpreted_count == 4
