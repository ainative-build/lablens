"""Tests for the evaluation framework — metrics and gate checks."""

import json
from pathlib import Path

from lablens.interpretation.engine import InterpretationEngine


SEED_GT_PATH = Path(__file__).parent.parent / "evaluation" / "ground-truth" / "seed-001-en.json"


def test_ground_truth_schema_valid():
    """Ground truth file is valid JSON with required fields."""
    gt = json.loads(SEED_GT_PATH.read_text())
    assert "report_id" in gt
    assert "source_language" in gt
    assert "variant_type" in gt
    assert "values" in gt
    assert len(gt["values"]) > 0


def test_engine_against_ground_truth():
    """Core evaluation: engine output matches ground truth expectations."""
    gt = json.loads(SEED_GT_PATH.read_text())
    engine = InterpretationEngine()

    values = []
    match_confidences = {}
    for i, v in enumerate(gt["values"]):
        values.append({
            "test_name": v["test_name"],
            "value": v["value"],
            "unit": v["unit"],
            "loinc_code": v["loinc_code"],
            "ref_range_low": v.get("reference_range_low"),
            "ref_range_high": v.get("reference_range_high"),
        })
        match_confidences[i] = "high"

    report = engine.interpret_report(values, match_confidences)

    # Check direction accuracy
    direction_correct = 0
    severity_correct = 0
    for interpreted, gt_val in zip(report.values, gt["values"]):
        if interpreted.direction == gt_val["expected_direction"]:
            direction_correct += 1
        if interpreted.severity == gt_val["expected_severity"]:
            severity_correct += 1

    n = len(gt["values"])
    direction_acc = direction_correct / n
    severity_acc = severity_correct / n

    assert direction_acc >= 0.9, f"Direction accuracy {direction_acc:.0%} < 90%"
    assert severity_acc >= 0.85, f"Severity accuracy {severity_acc:.0%} < 85%"


def test_all_abnormal_detected():
    """Safety gate: no abnormal analyte is missed."""
    gt = json.loads(SEED_GT_PATH.read_text())
    engine = InterpretationEngine()

    values = []
    match_confidences = {}
    for i, v in enumerate(gt["values"]):
        values.append({
            "test_name": v["test_name"],
            "value": v["value"],
            "unit": v["unit"],
            "loinc_code": v["loinc_code"],
            "ref_range_low": v.get("reference_range_low"),
            "ref_range_high": v.get("reference_range_high"),
        })
        match_confidences[i] = "high"

    report = engine.interpret_report(values, match_confidences)

    for interpreted, gt_val in zip(report.values, gt["values"]):
        if gt_val["expected_direction"] != "in-range":
            assert interpreted.direction != "in-range", (
                f"Missed abnormal: {gt_val['test_name']} "
                f"(expected {gt_val['expected_direction']}, got {interpreted.direction})"
            )


def test_confidence_high_for_clean_report():
    """Clean report with lab-provided ranges should have high confidence."""
    gt = json.loads(SEED_GT_PATH.read_text())
    engine = InterpretationEngine()

    values = []
    match_confidences = {}
    for i, v in enumerate(gt["values"]):
        values.append({
            "test_name": v["test_name"],
            "value": v["value"],
            "unit": v["unit"],
            "loinc_code": v["loinc_code"],
            "ref_range_low": v.get("reference_range_low"),
            "ref_range_high": v.get("reference_range_high"),
        })
        match_confidences[i] = "high"

    report = engine.interpret_report(values, match_confidences)

    for interpreted in report.values:
        assert interpreted.confidence == "high", (
            f"{interpreted.test_name}: expected high confidence, got {interpreted.confidence}"
        )
