"""Evidence trace builder for interpretation provenance."""

from lablens.interpretation.models import InterpretedResult


def build_evidence_trace(
    result: InterpretedResult, rule: dict | None, match_confidence: str
) -> dict:
    """Build full provenance trace for an interpreted value."""
    trace = {
        "test_name": result.test_name,
        "loinc_code": result.loinc_code,
        "value": result.value,
        "unit": result.unit,
        "range_source": result.range_source,
        "reference_range": {
            "low": result.reference_range_low,
            "high": result.reference_range_high,
        },
        "match_confidence": match_confidence,
        "direction": result.direction,
        "severity": result.severity,
        "is_panic": result.is_panic,
        "actionability": result.actionability,
        "composite_confidence": result.confidence,
    }
    if rule:
        ranges = rule.get("reference_ranges", [{}])
        trace["rule_source_note"] = ranges[0].get("source", "") if ranges else ""
    return trace
