"""Deterministic interpretation engine — 8-step decision pipeline.

Pure Python, zero external API calls. Same input always produces same output.
"""

import logging

from lablens.interpretation.band_validator import validate_band_contiguity
from lablens.interpretation.confidence import calculate_confidence
from lablens.interpretation.evidence import build_evidence_trace
from lablens.interpretation.models import InterpretedReport, InterpretedResult
from lablens.interpretation.panel_checker import check_panels
from lablens.interpretation.qualitative import interpret_qualitative
from lablens.interpretation.range_selection import (
    determine_direction,
    direction_from_text,
    select_range,
)
from lablens.interpretation.severity import (
    DEFAULT_ACTIONABILITY,
    apply_severity,
    check_panic,
    heuristic_severity,
)
from lablens.knowledge.rules_loader import get_rule, load_all_rules

logger = logging.getLogger(__name__)


class InterpretationEngine:
    """Core deterministic engine — no LLM, no network."""

    def __init__(self, rules: dict | None = None):
        self.rules = rules if rules is not None else load_all_rules()
        errors = validate_band_contiguity(self.rules)
        if errors:
            logger.warning("Band contiguity warnings: %s", errors)

    def interpret_report(
        self, values: list[dict], match_confidences: dict[int, str] | None = None
    ) -> InterpretedReport:
        """Interpret all lab values in a report.

        Args:
            values: list of dicts with keys: test_name, value, unit, loinc_code,
                    ref_range_low, ref_range_high, unit_confidence
            match_confidences: {index: "high"|"medium"|"low"} from terminology mapper
        """
        if match_confidences is None:
            match_confidences = {}

        results = []
        for i, v in enumerate(values):
            result = self._interpret_single(v, match_confidences.get(i, "low"))
            results.append(result)

        present_codes = [r.loinc_code for r in results if r.loinc_code]
        panels = check_panels(present_codes, self.rules)
        abnormal = [r for r in results if r.direction in ("high", "low")]

        return InterpretedReport(
            values=results,
            panels=panels,
            total_parsed=len(results),
            total_abnormal=len(abnormal),
            total_explained=len(abnormal),
        )

    def _interpret_single(self, v: dict, match_confidence: str) -> InterpretedResult:
        """Apply 8-step decision order to a single lab value."""
        result = InterpretedResult(
            test_name=v["test_name"],
            loinc_code=v.get("loinc_code"),
            value=v["value"],
            unit=v.get("unit", ""),
        )

        # Non-numeric: interpret qualitative values
        if not isinstance(v["value"], (int, float)):
            result.direction, result.confidence = interpret_qualitative(
                v["value"], v.get("flag")
            )
            result.evidence_trace = {"note": "Qualitative interpretation", "raw": str(v["value"])}
            return result

        value = float(v["value"])
        loinc = v.get("loinc_code", "")
        rule = get_rule(loinc, self.rules) if loinc else None
        range_trust = v.get("range_trust", "high")
        restricted_flag = v.get("restricted_flag", False)

        # Step 1: Select reference range
        ref_low, ref_high, range_source = select_range(v, rule)

        # Guard: curated fallback with low unit confidence is unreliable
        unit_confidence = v.get("unit_confidence", "high")
        if range_source == "curated-fallback" and unit_confidence == "low":
            logger.info(
                "Low unit confidence for %s — clearing curated fallback range",
                v.get("test_name", "?"),
            )
            ref_low, ref_high, range_source = None, None, "no-range"

        # Guard: curated fallback with empty unit — can't verify unit system
        unit_str = v.get("unit") or ""
        if range_source == "curated-fallback" and not unit_str.strip():
            logger.info(
                "Empty unit for %s — clearing curated fallback range",
                v.get("test_name", "?"),
            )
            ref_low, ref_high, range_source = None, None, "no-range"

        # Suspicious lab range override: prefer curated only if unit-compatible
        if range_source == "lab-provided" and range_trust == "low":
            if rule:
                ranges = rule.get("reference_ranges", [])
                if ranges:
                    curated_unit = (rule.get("unit") or "").strip().lower()
                    value_unit = (v.get("unit") or "").strip().lower()
                    units_compatible = (
                        curated_unit and value_unit
                        and curated_unit == value_unit
                    )
                    if units_compatible:
                        cur_low, cur_high = ranges[0]["low"], ranges[0]["high"]
                        logger.info(
                            "Low-trust lab range for %s — unit-compatible "
                            "curated [%s-%s] %s (was [%s-%s])",
                            v.get("test_name", "?"), cur_low, cur_high,
                            curated_unit, ref_low, ref_high,
                        )
                        ref_low, ref_high = cur_low, cur_high
                        range_source = "curated-fallback"
                    else:
                        # Unit mismatch — can't safely use curated or lab range
                        logger.info(
                            "Low-trust lab range for %s — curated unit '%s' "
                            "differs from value unit '%s', degrading to "
                            "indeterminate",
                            v.get("test_name", "?"), curated_unit, value_unit,
                        )
                        result.direction = "indeterminate"
                        result.range_source = "no-range"
                        result.range_trust = range_trust
                        result.confidence = "low"
                        result.evidence_trace = build_evidence_trace(
                            result, rule, match_confidence
                        )
                        return result

        # Decision-threshold tests with suspicious ranges → indeterminate
        # These tests (HbA1c, lipids) use clinical cut-points, not reference
        # intervals — a suspicious lab range is unreliable for interpretation
        is_decision_threshold = v.get("is_decision_threshold", False)
        if is_decision_threshold and range_source == "lab-provided" and range_trust == "low":
            logger.info(
                "Decision-threshold test %s with low-trust lab range — "
                "degrading to indeterminate",
                v.get("test_name", "?"),
            )
            result.direction = "indeterminate"
            result.range_source = "no-range"
            result.range_trust = range_trust
            result.confidence = "low"
            result.evidence_trace = build_evidence_trace(
                result, rule, match_confidence
            )
            return result

        # Expand range_source with trust level
        if range_source == "lab-provided":
            if range_trust == "low":
                # Low trust but no curated fallback available — keep but mark suspicious
                range_source = "lab-provided-suspicious"
            else:
                range_source = "lab-provided-validated"

        result.reference_range_low = ref_low
        result.reference_range_high = ref_high
        result.range_source = range_source
        result.range_trust = range_trust

        if ref_low is None or ref_high is None:
            return self._handle_no_range(result, v, value, rule, match_confidence, restricted_flag)

        # Step 2: Determine direction
        result.direction = determine_direction(value, ref_low, ref_high)

        # Steps 3-5: Severity, panic, actionability
        self._apply_severity_and_actionability(
            result, value, ref_low, ref_high, rule, range_source, range_trust
        )

        # Step 6: Calculate confidence
        result.confidence = calculate_confidence(
            match_confidence=match_confidence,
            range_source=range_source,
            unit_confidence=v.get("unit_confidence", "high"),
        )

        # Step 7: Evidence trace
        result.evidence_trace = build_evidence_trace(result, rule, match_confidence)

        return result

    def _handle_no_range(
        self, result: InterpretedResult, v: dict, value: float,
        rule: dict | None, match_confidence: str, restricted_flag: bool,
    ) -> InterpretedResult:
        """Handle values with no usable reference range (text fallback, OCR flag, indeterminate)."""
        # Try to extract direction from reference_range_text
        ref_text = v.get("reference_range_text", "")
        if ref_text and isinstance(value, (int, float)):
            direction = direction_from_text(value, ref_text)
            if direction:
                result.direction = direction
                result.range_source = "range-text"
                result.confidence = "low"
                result.evidence_trace = build_evidence_trace(result, rule, match_confidence)
                return result

        # Last resort: OCR flag — only if unit is known and not restricted
        flag = v.get("flag")
        unit = v.get("unit") or ""
        if not unit.strip():
            result.direction = "indeterminate"
        elif restricted_flag:
            # Hormones, tumor markers, infectious — flag is unreliable
            result.direction = "indeterminate"
            result.range_source = "no-range"
        elif flag and flag.upper() in ("H", "A"):
            result.direction = "high"
            result.range_source = "ocr-flag-fallback"
        elif flag and flag.upper() == "L":
            result.direction = "low"
            result.range_source = "ocr-flag-fallback"
        else:
            result.direction = "indeterminate"
        result.confidence = "low"
        result.evidence_trace = build_evidence_trace(result, rule, match_confidence)
        return result

    def _apply_severity_and_actionability(
        self, result: InterpretedResult, value: float,
        ref_low: float, ref_high: float, rule: dict | None,
        range_source: str, range_trust: str,
    ) -> None:
        """Steps 3-5: Severity band, panic check, actionability assignment."""
        if result.direction == "in-range":
            # Hard guard: in-range values are always normal severity
            result.severity = "normal"
            result.actionability = "routine"
            result.is_panic = False
            return

        # Low-trust lab range -> cap severity at mild
        if range_trust == "low":
            result.severity = heuristic_severity(value, ref_low, ref_high)
            if result.severity in ("moderate", "critical"):
                result.severity = "mild"
        elif rule and range_source == "curated-fallback":
            result.severity = apply_severity(value, rule)
        elif rule and range_source.startswith("lab-provided"):
            result.severity = heuristic_severity(value, ref_low, ref_high)
        else:
            result.severity = "normal"

        if result.severity == "normal" and result.direction != "in-range":
            result.severity = heuristic_severity(value, ref_low, ref_high)

        # Severity cap: never critical without curated bands
        if result.severity == "critical" and range_source != "curated-fallback":
            result.severity = "moderate"

        # Step 4: Check panic threshold (only with curated fallback)
        result.is_panic = (
            check_panic(value, rule)
            if range_source == "curated-fallback"
            else False
        )

        # Step 5: Assign actionability
        result.actionability = DEFAULT_ACTIONABILITY.get(result.severity, "routine")
        if result.is_panic:
            result.actionability = "urgent"
