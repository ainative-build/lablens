"""Tests for qualitative assay-native semantics.

Two tiers: unit tests on interpret_qualitative() and integration
tests through InterpretationEngine._interpret_single().
"""

import pytest

from lablens.interpretation.qualitative import (
    ABNORMAL_QUALITATIVE,
    NORMAL_QUALITATIVE,
    interpret_qualitative,
    interpret_qualitative_titer,
)
from lablens.knowledge.rules_loader import load_all_rules, load_qualitative_rules


# ── Tier 1: Unit tests on interpret_qualitative() ─────────────────


class TestRulesLoading:
    """Verify qualitative rules YAML loads correctly."""

    def test_rules_load_without_error(self):
        rules = load_qualitative_rules()
        assert "tests" in rules
        assert "value_aliases" in rules

    def test_all_loinc_entries_present(self):
        rules = load_qualitative_rules()
        tests = rules["tests"]
        # At minimum 22 entries
        assert len(tests) >= 22

    def test_value_aliases_map_correctly(self):
        rules = load_qualitative_rules()
        aliases = rules["value_aliases"]
        assert aliases["neg"] == "negative"
        assert aliases["pos"] == "positive"
        assert aliases["non reactive"] == "non-reactive"
        assert aliases["dương tính"] == "positive"
        assert aliases["âm tính"] == "negative"

    def test_load_all_rules_no_crash(self):
        """load_all_rules() must not crash with qualitative.yaml in same dir."""
        rules = load_all_rules()
        # Should still have panel rules (not zero)
        assert len(rules) > 0
        # Should NOT include qualitative LOINC codes (those are in separate loader)
        assert "5195-3" not in rules  # HBsAg is qualitative-only


class TestExpectedNegative:
    """Tests for expected-negative category (positive = abnormal)."""

    def test_hbsag_negative(self):
        r = interpret_qualitative("Negative", None, loinc_code="5195-3")
        assert r["direction"] == "in-range"
        assert r["severity"] == "normal"
        assert r["confidence"] == "high"

    def test_hbsag_positive(self):
        r = interpret_qualitative("Positive", None, loinc_code="5195-3")
        assert r["direction"] == "high"
        assert r["severity"] == "moderate"
        assert r["actionability"] == "follow-up"

    def test_hbsag_reactive_alias(self):
        """'Reactive' should be treated same as 'Positive'."""
        r = interpret_qualitative("Reactive", None, loinc_code="5195-3")
        assert r["direction"] == "high"

    def test_hcv_positive(self):
        r = interpret_qualitative("Positive", None, loinc_code="16128-1")
        assert r["direction"] == "high"
        assert r["severity"] == "moderate"

    def test_hiv_positive_critical(self):
        r = interpret_qualitative("Positive", None, loinc_code="75622-1")
        assert r["direction"] == "high"
        assert r["severity"] == "critical"
        assert r["actionability"] == "urgent"
        assert r["is_panic"] is True

    def test_rpr_non_reactive(self):
        r = interpret_qualitative("Non-Reactive", None, loinc_code="5291-0")
        assert r["direction"] == "in-range"


class TestExpectedPositive:
    """Tests for expected-positive category (HBsAb inversion)."""

    def test_hbsab_positive_is_normal(self):
        """THE critical bug fix: HBsAb Positive = immune = in-range."""
        r = interpret_qualitative("Positive", None, loinc_code="22322-2")
        assert r["direction"] == "in-range"
        assert r["severity"] == "normal"
        assert r["confidence"] == "high"

    def test_hbsab_negative_is_abnormal(self):
        """HBsAb Negative = no immunity = actionable."""
        r = interpret_qualitative("Negative", None, loinc_code="22322-2")
        assert r["direction"] == "high"
        assert r["severity"] == "mild"
        assert r["actionability"] == "follow-up"

    def test_hbsab_reactive_same_as_positive(self):
        r = interpret_qualitative("Reactive", None, loinc_code="22322-2")
        assert r["direction"] == "in-range"


class TestCategorical:
    """Tests for categorical (blood type, Rh) — always in-range."""

    def test_blood_type_a_plus(self):
        r = interpret_qualitative("A+", None, loinc_code="883-9")
        assert r["direction"] == "in-range"
        assert r["severity"] == "normal"

    def test_rh_positive_not_high(self):
        """Rh 'Positive' must NOT be flagged as high."""
        r = interpret_qualitative("Positive", None, loinc_code="10331-7")
        assert r["direction"] == "in-range"
        assert r["severity"] == "normal"

    def test_rh_negative_not_abnormal(self):
        """Rh 'Negative' is NOT abnormal."""
        r = interpret_qualitative("Negative", None, loinc_code="10331-7")
        assert r["direction"] == "in-range"

    def test_abo_o(self):
        r = interpret_qualitative("O", None, loinc_code="883-9")
        assert r["direction"] == "in-range"


class TestSemiQuantitative:
    """Tests for semi-quantitative urinalysis dipstick."""

    def test_ua_protein_negative(self):
        r = interpret_qualitative("Negative", None, loinc_code="20454-5")
        assert r["direction"] == "in-range"

    def test_ua_protein_trace_normal(self):
        """Trace is normal for urine protein."""
        r = interpret_qualitative("Trace", None, loinc_code="20454-5")
        assert r["direction"] == "in-range"

    def test_ua_protein_1plus_mild(self):
        r = interpret_qualitative("1+", None, loinc_code="20454-5")
        assert r["direction"] == "high"
        assert r["severity"] == "mild"

    def test_ua_protein_2plus_moderate(self):
        r = interpret_qualitative("2+", None, loinc_code="20454-5")
        assert r["direction"] == "high"
        assert r["severity"] == "moderate"
        assert r["actionability"] == "follow-up"

    def test_ua_protein_3plus(self):
        r = interpret_qualitative("3+", None, loinc_code="20454-5")
        assert r["direction"] == "high"
        assert r["severity"] == "moderate"

    def test_urobilinogen_trace_normal(self):
        """Trace is NORMAL for urobilinogen (special case)."""
        r = interpret_qualitative("Trace", None, loinc_code="13658-0")
        assert r["direction"] == "in-range"

    def test_urobilinogen_1plus_normal(self):
        """1+ is still normal for urobilinogen."""
        r = interpret_qualitative("1+", None, loinc_code="13658-0")
        assert r["direction"] == "in-range"

    def test_urobilinogen_2plus_abnormal(self):
        r = interpret_qualitative("2+", None, loinc_code="13658-0")
        assert r["direction"] == "high"
        assert r["severity"] == "mild"


class TestSemiQuantAliases:
    """OCR semi-quantitative aliases normalize correctly."""

    def test_single_plus_to_1plus(self):
        r = interpret_qualitative("+", None, loinc_code="5794-3")
        assert r["direction"] == "high"
        assert r["severity"] == "mild"

    def test_double_plus_to_2plus(self):
        r = interpret_qualitative("++", None, loinc_code="5794-3")
        assert r["direction"] == "high"
        assert r["severity"] == "moderate"

    def test_triple_plus_to_3plus(self):
        r = interpret_qualitative("+++", None, loinc_code="5794-3")
        assert r["direction"] == "high"
        assert r["severity"] == "moderate"


class TestFallbackBehavior:
    """Fallback keyword matching for unmapped LOINCs."""

    def test_unmapped_loinc_negative(self):
        r = interpret_qualitative("Negative", None, loinc_code="99999-9")
        assert r["direction"] == "in-range"
        assert r["confidence"] == "medium"

    def test_unmapped_loinc_positive(self):
        r = interpret_qualitative("Positive", None, loinc_code="99999-9")
        assert r["direction"] == "high"
        assert r["confidence"] == "medium"

    def test_no_loinc_negative(self):
        r = interpret_qualitative("Negative", None, loinc_code=None)
        assert r["direction"] == "in-range"

    def test_unknown_value_indeterminate(self):
        r = interpret_qualitative("Equivocal", None, loinc_code=None)
        assert r["direction"] == "indeterminate"
        assert r["confidence"] == "low"


class TestValueAliases:
    """OCR value alias normalization."""

    def test_non_reactive_alias(self):
        r = interpret_qualitative("Non Reactive", None, loinc_code="5195-3")
        assert r["direction"] == "in-range"

    def test_vietnamese_negative(self):
        r = interpret_qualitative("Âm Tính", None, loinc_code="5195-3")
        assert r["direction"] == "in-range"

    def test_vietnamese_positive(self):
        r = interpret_qualitative("Dương Tính", None, loinc_code="5195-3")
        assert r["direction"] == "high"

    def test_neg_abbreviation(self):
        r = interpret_qualitative("NEG", None, loinc_code="5195-3")
        assert r["direction"] == "in-range"


class TestTestNameFallback:
    """LOINC=None with test_name triggers name index lookup."""

    def test_hbsab_by_name(self):
        r = interpret_qualitative(
            "Positive", None, loinc_code=None, test_name="HBsAb"
        )
        assert r["direction"] == "in-range"
        assert r["evidence_trace"]["interpretation_method"] == "qualitative-name-fallback"

    def test_hbsag_by_name(self):
        r = interpret_qualitative(
            "Positive", None, loinc_code=None, test_name="HBsAg"
        )
        assert r["direction"] == "high"

    def test_unknown_name_falls_back(self):
        r = interpret_qualitative(
            "Positive", None, loinc_code=None, test_name="Unknown Test"
        )
        assert r["direction"] == "high"
        assert r["confidence"] == "medium"  # keyword fallback


class TestTiterRouting:
    """Numeric titers route through qualitative rules when titer_positive_threshold exists."""

    def test_hbsab_high_titer_is_immune(self):
        """HBsAb 916.89 mIU/mL >= 10 → positive → in-range (immune)."""
        r = interpret_qualitative_titer(916.89, loinc_code="22322-2")
        assert r is not None
        assert r["direction"] == "in-range"
        assert r["severity"] == "normal"
        assert r["evidence_trace"]["titer_positive"] is True

    def test_hbsab_low_titer_is_nonimmune(self):
        """HBsAb 3.5 mIU/mL < 10 → negative → high (non-immune)."""
        r = interpret_qualitative_titer(3.5, loinc_code="22322-2")
        assert r is not None
        assert r["direction"] == "high"
        assert r["severity"] == "mild"
        assert r["actionability"] == "follow-up"

    def test_hbsab_at_threshold_is_immune(self):
        """HBsAb exactly 10.0 → positive (>= threshold)."""
        r = interpret_qualitative_titer(10.0, loinc_code="22322-2")
        assert r is not None
        assert r["direction"] == "in-range"

    def test_hbsag_above_threshold_is_abnormal(self):
        """HBsAg COI 2.5 >= 1.0 → positive → high (active infection)."""
        r = interpret_qualitative_titer(2.5, loinc_code="5195-3")
        assert r is not None
        assert r["direction"] == "high"
        assert r["severity"] == "moderate"

    def test_hbsag_below_threshold_is_normal(self):
        """HBsAg COI 0.3 < 1.0 → negative → in-range."""
        r = interpret_qualitative_titer(0.3, loinc_code="5195-3")
        assert r is not None
        assert r["direction"] == "in-range"
        assert r["severity"] == "normal"

    def test_hcv_above_threshold(self):
        """HCV Ab COI 1.5 >= 1.0 → high."""
        r = interpret_qualitative_titer(1.5, loinc_code="16128-1")
        assert r is not None
        assert r["direction"] == "high"

    def test_hcv_below_threshold(self):
        """HCV Ab COI 0.1 < 1.0 → in-range."""
        r = interpret_qualitative_titer(0.1, loinc_code="16128-1")
        assert r is not None
        assert r["direction"] == "in-range"

    def test_no_titer_rule_returns_none(self):
        """LOINC without titer_positive_threshold → None (quantitative path)."""
        r = interpret_qualitative_titer(5.0, loinc_code="883-9")  # Blood type
        assert r is None

    def test_unknown_loinc_returns_none(self):
        """Unknown LOINC → None."""
        r = interpret_qualitative_titer(100.0, loinc_code="99999-9")
        assert r is None

    def test_titer_evidence_trace(self):
        """Titer result includes threshold and value in evidence trace."""
        r = interpret_qualitative_titer(916.89, loinc_code="22322-2")
        assert r["evidence_trace"]["titer_value"] == 916.89
        assert r["evidence_trace"]["titer_threshold"] == 10.0
        assert r["evidence_trace"]["interpretation_method"] == "qualitative-loinc-titer"


class TestEngineTiterIntegration:
    """Numeric titers through engine use qualitative titer routing."""

    def _interpret(self, test_name, value, loinc_code=None, unit=""):
        from lablens.interpretation.engine import InterpretationEngine
        engine = InterpretationEngine()
        return engine._interpret_single(
            {
                "test_name": test_name,
                "value": value,
                "unit": unit,
                "loinc_code": loinc_code,
            },
            match_confidence="high",
        )

    def test_hbsab_numeric_titer_through_engine(self):
        """THE critical fix: HBsAb 916.89 mIU/mL through engine → in-range."""
        result = self._interpret("HBsAb", 916.89, loinc_code="22322-2", unit="mIU/mL")
        assert result.direction == "in-range"
        assert result.severity == "normal"
        assert result.range_source == "qualitative-rule"

    def test_hbsag_numeric_above_threshold(self):
        """HBsAg COI 2.5 through engine → high."""
        result = self._interpret("HBsAg", 2.5, loinc_code="5195-3", unit="COI")
        assert result.direction == "high"
        assert result.severity == "moderate"

    def test_hbsag_numeric_below_threshold(self):
        """HBsAg COI 0.3 through engine → in-range."""
        result = self._interpret("HBsAg", 0.3, loinc_code="5195-3", unit="COI")
        assert result.direction == "in-range"

    def test_hcv_numeric_through_engine(self):
        """HCV Ab COI 0.08 through engine → in-range."""
        result = self._interpret("HCV Ab", 0.08, loinc_code="16128-1", unit="COI")
        assert result.direction == "in-range"

    def test_non_titer_numeric_uses_quantitative(self):
        """Numeric value for non-titer LOINC still takes quantitative path."""
        result = self._interpret("Hemoglobin", 14.5, loinc_code="718-7", unit="g/dL")
        # Should NOT route through qualitative — no titer rule for 718-7
        assert result.range_source != "qualitative-rule"


class TestEvidenceTrace:
    """Evidence trace fields are populated correctly."""

    def test_loinc_mapped_has_method(self):
        r = interpret_qualitative("Positive", None, loinc_code="5195-3")
        assert r["evidence_trace"]["interpretation_method"] == "qualitative-loinc"

    def test_has_explanation_hint(self):
        r = interpret_qualitative("Positive", None, loinc_code="5195-3")
        assert "explanation_hint" in r["evidence_trace"]
        assert len(r["evidence_trace"]["explanation_hint"]) > 0

    def test_severity_source_is_qualitative_rule(self):
        r = interpret_qualitative("Positive", None, loinc_code="5195-3")
        assert r["evidence_trace"]["severity_source"] == "qualitative-rule"


# ── Tier 2: Integration tests through InterpretationEngine ────────


class TestEngineQualitativeIntegration:
    """Test qualitative values flowing through the full engine."""

    def _interpret(self, test_name, value, loinc_code=None, flag=None):
        from lablens.interpretation.engine import InterpretationEngine
        engine = InterpretationEngine()
        return engine._interpret_single(
            {
                "test_name": test_name,
                "value": value,
                "unit": "",
                "loinc_code": loinc_code,
                "flag": flag,
            },
            match_confidence="high",
        )

    def test_hbsag_positive_through_engine(self):
        result = self._interpret("HBsAg", "Positive", loinc_code="5195-3")
        assert result.direction == "high"
        assert result.severity == "moderate"
        assert result.actionability == "follow-up"
        assert result.range_source == "qualitative-rule"

    def test_hbsab_positive_through_engine(self):
        """HBsAb inversion must work at engine level."""
        result = self._interpret("HBsAb", "Positive", loinc_code="22322-2")
        assert result.direction == "in-range"
        assert result.severity == "normal"

    def test_blood_type_through_engine(self):
        result = self._interpret("Blood Type", "A+", loinc_code="883-9")
        assert result.direction == "in-range"
        assert result.severity == "normal"

    def test_ua_protein_through_engine(self):
        result = self._interpret("Urine Protein", "2+", loinc_code="20454-5")
        assert result.direction == "high"
        assert result.severity == "moderate"

    def test_unmapped_positive_through_engine(self):
        result = self._interpret("Unknown Test", "Positive", loinc_code=None)
        assert result.direction == "high"
        assert result.confidence == "medium"
        assert result.range_source == "no-range"

    def test_loinc_none_name_fallback_through_engine(self):
        """LOINC=None but test_name matches -> dispatches via name index."""
        result = self._interpret("HBsAg", "Positive", loinc_code=None)
        assert result.direction == "high"
        assert result.evidence_trace["interpretation_method"] == "qualitative-name-fallback"


class TestEngineFieldCompleteness:
    """Verify all InterpretedResult fields are set for qualitative results."""

    def _interpret(self, test_name, value, loinc_code=None):
        from lablens.interpretation.engine import InterpretationEngine
        engine = InterpretationEngine()
        return engine._interpret_single(
            {
                "test_name": test_name,
                "value": value,
                "unit": "",
                "loinc_code": loinc_code,
            },
            match_confidence="high",
        )

    def test_all_fields_set(self):
        """Qualitative result must have all core InterpretedResult fields."""
        result = self._interpret("HBsAg", "Positive", "5195-3")
        assert result.direction is not None
        assert result.confidence is not None
        assert result.severity is not None
        assert result.actionability is not None
        assert result.is_panic is not None
        assert result.range_source is not None
        assert result.evidence_trace is not None
        assert "raw" in result.evidence_trace

    def test_range_source_never_empty(self):
        """range_source must be set for qualitative results."""
        result = self._interpret("Unknown", "Positive")
        assert result.range_source in ("qualitative-rule", "no-range")
        assert result.range_source != ""
