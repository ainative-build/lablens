"""Deterministic interpretation engine — 8-step decision pipeline.

Pure Python, zero external API calls. Same input always produces same output.
"""

import logging

from lablens.interpretation.band_validator import validate_band_contiguity
from lablens.interpretation.confidence import calculate_confidence
from lablens.interpretation.evidence import build_evidence_trace
from lablens.interpretation.models import InterpretedReport, InterpretedResult
from lablens.interpretation.panel_checker import check_panels
from lablens.knowledge.rules_loader import get_rule, load_all_rules

logger = logging.getLogger(__name__)

# Maps YAML severity band names to severity tiers
_SEVERITY_TIERS = {
    "normal": "normal",
    "mild_low": "mild",
    "mild_high": "mild",
    "moderate_low": "moderate",
    "moderate_high": "moderate",
    "critical_low": "critical",
    "critical_high": "critical",
}

# Maps severity tiers to default actionability
_DEFAULT_ACTIONABILITY = {
    "normal": "routine",
    "mild": "monitor",
    "moderate": "consult",
    "critical": "urgent",
}

# Qualitative values indicating normal/expected results
_NORMAL_QUALITATIVE = {
    "negative", "non-reactive", "nonreactive", "normal", "not detected",
    "absent", "clear", "âm tính", "négatif",
}

# Qualitative values indicating abnormal/unexpected results
_ABNORMAL_QUALITATIVE = {
    "positive", "reactive", "abnormal", "detected", "present",
    "dương tính", "positif",
}


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
            result.direction, result.confidence = self._interpret_qualitative(
                v["value"], v.get("flag")
            )
            result.evidence_trace = {"note": "Qualitative interpretation", "raw": str(v["value"])}
            return result

        value = float(v["value"])
        loinc = v.get("loinc_code", "")
        rule = get_rule(loinc, self.rules) if loinc else None

        # Step 1: Select reference range
        ref_low, ref_high, range_source = self._select_range(v, rule)
        result.reference_range_low = ref_low
        result.reference_range_high = ref_high
        result.range_source = range_source

        if ref_low is None or ref_high is None:
            # Fallback: use OCR flag for direction if available
            flag = v.get("flag")
            if flag and flag.upper() in ("H", "A"):
                result.direction = "high"
                result.range_source = "ocr-flag"
            elif flag and flag.upper() == "L":
                result.direction = "low"
                result.range_source = "ocr-flag"
            else:
                result.direction = "indeterminate"
            result.confidence = "low"
            result.evidence_trace = build_evidence_trace(
                result, rule, match_confidence
            )
            return result

        # Step 2: Determine direction
        result.direction = self._determine_direction(value, ref_low, ref_high)

        # Step 3: Apply severity band (curated rule or heuristic deviation)
        result.severity = self._apply_severity(value, rule)
        if result.severity == "normal" and result.direction != "in-range":
            # Heuristic fallback: estimate severity from deviation %
            result.severity = self._heuristic_severity(value, ref_low, ref_high)

        # Step 4: Check panic threshold
        result.is_panic = self._check_panic(value, rule)

        # Step 5: Assign actionability
        result.actionability = _DEFAULT_ACTIONABILITY.get(result.severity, "routine")
        if result.is_panic:
            result.actionability = "urgent"

        # Step 6: Calculate confidence
        result.confidence = calculate_confidence(
            match_confidence=match_confidence,
            range_source=range_source,
            unit_confidence=v.get("unit_confidence", "high"),
        )

        # Step 7: Evidence trace
        result.evidence_trace = build_evidence_trace(result, rule, match_confidence)

        return result

    @staticmethod
    def _select_range(v: dict, rule: dict | None) -> tuple:
        """Step 1: Lab-provided preferred, curated fallback."""
        # Support both abbreviated and full key names from pipeline
        low = v.get("reference_range_low", v.get("ref_range_low"))
        high = v.get("reference_range_high", v.get("ref_range_high"))
        if low is not None and high is not None:
            return low, high, "lab-provided"
        if rule:
            ranges = rule.get("reference_ranges", [])
            if ranges:
                default = ranges[0]
                return default["low"], default["high"], "curated-fallback"
        return None, None, "none"

    @staticmethod
    def _determine_direction(value: float, low: float, high: float) -> str:
        """Step 2: Compare value against reference range."""
        if value < low:
            return "low"
        if value > high:
            return "high"
        return "in-range"

    @staticmethod
    def _apply_severity(value: float, rule: dict | None) -> str:
        """Step 3: Map value to severity band.

        Finding #7: If value falls in a band gap, return based on whether
        it's outside the normal range (not silently 'normal').
        """
        if not rule or "severity_bands" not in rule:
            return "normal"

        bands = rule["severity_bands"]
        # Check bands in priority order (most severe first)
        for band_name in [
            "critical_low", "critical_high",
            "moderate_low", "moderate_high",
            "mild_low", "mild_high",
            "normal",
        ]:
            band = bands.get(band_name)
            if band and band["low"] <= value <= band["high"]:
                return _SEVERITY_TIERS.get(band_name, "normal")

        # Band gap fallback (Finding #7)
        normal_band = bands.get("normal")
        if normal_band and not (normal_band["low"] <= value <= normal_band["high"]):
            return "moderate"  # Outside normal, no band matched
        return "normal"

    @staticmethod
    def _check_panic(value: float, rule: dict | None) -> bool:
        """Step 4: Check panic thresholds."""
        if not rule or "panic_thresholds" not in rule:
            return False
        panic = rule["panic_thresholds"]
        return (
            value <= panic.get("low", float("-inf"))
            or value >= panic.get("high", float("inf"))
        )

    @staticmethod
    def _heuristic_severity(value: float, ref_low: float, ref_high: float) -> str:
        """Estimate severity from deviation % when no curated severity bands exist."""
        range_span = ref_high - ref_low
        if range_span <= 0:
            return "mild"
        if value < ref_low:
            deviation = (ref_low - value) / range_span
        else:
            deviation = (value - ref_high) / range_span
        if deviation <= 0.1:
            return "mild"
        return "moderate"

    @staticmethod
    def _interpret_qualitative(value: str, flag: str | None) -> tuple[str, str]:
        """Interpret non-numeric qualitative lab values. Returns (direction, confidence)."""
        val_lower = str(value).strip().lower()
        if val_lower in _NORMAL_QUALITATIVE:
            return "in-range", "medium"
        if val_lower in _ABNORMAL_QUALITATIVE:
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
