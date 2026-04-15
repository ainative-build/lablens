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

        # Guard: curated fallback with low unit confidence is unreliable
        # (e.g. HDL-C=0.92 "mg/dL" against curated [40-999] mg/dL when
        # the actual unit is mmol/L)
        unit_confidence = v.get("unit_confidence", "high")
        if range_source == "curated-fallback" and unit_confidence == "low":
            logger.info(
                "Low unit confidence for %s — clearing curated fallback range",
                v.get("test_name", "?"),
            )
            ref_low, ref_high, range_source = None, None, "none"

        # Guard: curated fallback with empty unit — can't verify unit system
        # (e.g. Free T4=13.59 with no unit, curated expects ng/dL but
        # value may be in pmol/L)
        unit_str = v.get("unit") or ""
        if range_source == "curated-fallback" and not unit_str.strip():
            logger.info(
                "Empty unit for %s — clearing curated fallback range",
                v.get("test_name", "?"),
            )
            ref_low, ref_high, range_source = None, None, "none"

        result.reference_range_low = ref_low
        result.reference_range_high = ref_high
        result.range_source = range_source

        if ref_low is None or ref_high is None:
            # Try to extract direction from reference_range_text (e.g. "≤ 39", "< 200")
            ref_text = v.get("reference_range_text", "")
            if ref_text and isinstance(value, (int, float)):
                direction = self._direction_from_text(value, ref_text)
                if direction:
                    result.direction = direction
                    result.range_source = "range-text"
                    result.confidence = "low"
                    result.evidence_trace = build_evidence_trace(
                        result, rule, match_confidence
                    )
                    return result

            # Last resort: use OCR flag for direction — but only if unit is known
            flag = v.get("flag")
            unit = v.get("unit") or ""
            if not unit.strip():
                # No unit + no range = too uncertain — flag is unreliable
                result.direction = "indeterminate"
            elif flag and flag.upper() in ("H", "A"):
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

        # Step 3: Apply severity band
        if result.direction == "in-range":
            # Hard guard: in-range values are always normal severity
            result.severity = "normal"
            result.actionability = "routine"
            result.is_panic = False
        else:
            # Only apply severity bands when value is actually out of range
            # AND curated rule units match the value's units (range_source check)
            if rule and range_source == "curated-fallback":
                # Curated fallback range was used — severity bands are in same unit system
                result.severity = self._apply_severity(value, rule)
            elif rule and range_source == "lab-provided":
                # Lab-provided range — curated severity bands may be in different units
                # Use heuristic severity based on deviation from lab range instead
                result.severity = self._heuristic_severity(value, ref_low, ref_high)
            else:
                result.severity = "normal"

            if result.severity == "normal" and result.direction != "in-range":
                result.severity = self._heuristic_severity(value, ref_low, ref_high)

            # Step 4: Check panic threshold (only with curated fallback — same unit system)
            result.is_panic = (
                self._check_panic(value, rule)
                if range_source == "curated-fallback"
                else False
            )

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
        """Step 1: Lab-provided preferred, curated fallback.

        Cross-validates lab range against curated rule when both exist.
        If curated says in-range but lab says out-of-range, the lab range
        is likely an OCR row-swap — prefer curated.
        """
        low = v.get("reference_range_low", v.get("ref_range_low"))
        high = v.get("reference_range_high", v.get("ref_range_high"))
        value = v.get("value")

        if low is not None and high is not None:
            # Cross-validate against curated if available and value is numeric
            if rule and isinstance(value, (int, float)):
                ranges = rule.get("reference_ranges", [])
                if ranges:
                    cur_low = ranges[0]["low"]
                    cur_high = ranges[0]["high"]
                    lab_says_abnormal = value < low or value > high
                    curated_says_in_range = cur_low <= value <= cur_high
                    if lab_says_abnormal and curated_says_in_range:
                        logger.info(
                            "Lab range [%s-%s] flags %s as abnormal but curated "
                            "[%s-%s] says in-range — likely OCR row-swap, "
                            "preferring curated for %s",
                            low, high, value, cur_low, cur_high,
                            v.get("test_name", "?"),
                        )
                        return cur_low, cur_high, "curated-fallback"
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
    def _direction_from_text(value: float, ref_text: str) -> str | None:
        """Try to extract direction from reference_range_text like '≤ 39', '< 200'.

        Returns direction string or None if text is not parseable.
        """
        import re
        text = ref_text.strip()
        # Pattern: "< 200", "<= 39", "≤ 39"
        m = re.search(r"[<≤]\s*=?\s*([\d.]+)", text)
        if m:
            threshold = float(m.group(1))
            return "high" if value > threshold else "in-range"
        # Pattern: "> 60", ">= 3.5", "≥ 3.5"
        m = re.search(r"[>≥]\s*=?\s*([\d.]+)", text)
        if m:
            threshold = float(m.group(1))
            return "low" if value < threshold else "in-range"
        return None

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
