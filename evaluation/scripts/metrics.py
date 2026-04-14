"""Analyte-level evaluation metrics for LabLens."""

from dataclasses import dataclass


@dataclass
class AnalyteResult:
    """Evaluation result for a single analyte."""

    test_name: str
    loinc_code: str
    extraction_correct: bool
    mapping_correct: bool
    unit_normalized: bool
    direction_correct: bool
    severity_correct: bool
    confidence_reasonable: bool
    explanation_grounded: bool


def evaluate_analyte(
    predicted: dict, ground_truth: dict, variant_type: str
) -> AnalyteResult:
    """Evaluate a single analyte against ground truth."""
    extraction_ok = (
        str(predicted.get("value", "")) == str(ground_truth["value"])
        and (predicted.get("unit") or "").lower() == (ground_truth.get("unit") or "").lower()
    )
    mapping_ok = predicted.get("loinc_code") == ground_truth.get("loinc_code")
    direction_ok = predicted.get("direction") == ground_truth.get("expected_direction")
    severity_ok = predicted.get("severity") == ground_truth.get("expected_severity")

    # Confidence should downgrade for degraded variants
    confidence_ok = True
    if ground_truth.get("expected_confidence_downgrade"):
        confidence_ok = predicted.get("confidence") != "high"

    # Unit normalization check
    unit_ok = bool(predicted.get("unit"))

    return AnalyteResult(
        test_name=ground_truth["test_name"],
        loinc_code=ground_truth.get("loinc_code", ""),
        extraction_correct=extraction_ok,
        mapping_correct=mapping_ok,
        unit_normalized=unit_ok,
        direction_correct=direction_ok,
        severity_correct=severity_ok,
        confidence_reasonable=confidence_ok,
        explanation_grounded=True,  # Manual review needed
    )


def compute_aggregate(results: list[AnalyteResult]) -> dict:
    """Compute aggregate metrics from analyte-level results."""
    n = len(results)
    if n == 0:
        return {}
    return {
        "total_analytes": n,
        "extraction_accuracy": sum(r.extraction_correct for r in results) / n,
        "mapping_accuracy": sum(r.mapping_correct for r in results) / n,
        "direction_accuracy": sum(r.direction_correct for r in results) / n,
        "severity_accuracy": sum(r.severity_correct for r in results) / n,
        "confidence_calibration": sum(r.confidence_reasonable for r in results) / n,
    }
