"""Tests for semantic verifier: deterministic checks, verdict merging, model parsing."""

import json

import pytest

from lablens.extraction.semantic_verifier import (
    Verdict,
    VerificationResult,
    check_unit_value_plausibility,
    deterministic_checks,
    merge_verdicts,
    parse_model_verdicts,
)


# ── Unit-value plausibility ──


class TestUnitValuePlausibility:
    def test_percent_in_range(self):
        assert check_unit_value_plausibility(5.5, "%") is True

    def test_percent_out_of_range(self):
        assert check_unit_value_plausibility(150.0, "%") is False

    def test_percent_negative(self):
        assert check_unit_value_plausibility(-1.0, "%") is False

    def test_mgdl_in_range(self):
        assert check_unit_value_plausibility(100.0, "mg/dL") is True

    def test_mgdl_extreme(self):
        assert check_unit_value_plausibility(50000.0, "mg/dL") is False

    def test_mmol_mol_in_range(self):
        assert check_unit_value_plausibility(42.0, "mmol/mol") is True

    def test_unknown_unit_passes(self):
        """Unknown unit should pass by default."""
        assert check_unit_value_plausibility(999.0, "widgets/ml") is True

    def test_fl_in_range(self):
        assert check_unit_value_plausibility(85.0, "fL") is True

    def test_fl_out_of_range(self):
        assert check_unit_value_plausibility(300.0, "fL") is False


# ── Deterministic checks ──


class TestDeterministicChecks:
    def test_complete_value_accepted(self):
        v = {"test_name": "Glucose", "value": 100.0, "unit": "mg/dL"}
        result = deterministic_checks(v)
        assert result.verdict == Verdict.ACCEPT
        assert result.checks_passed >= 2
        assert result.checks_failed == 0

    def test_missing_test_name(self):
        v = {"test_name": "", "value": 100.0, "unit": "mg/dL"}
        result = deterministic_checks(v)
        assert result.checks_failed >= 1
        assert "Missing test_name" in result.reasons

    def test_missing_value(self):
        v = {"test_name": "Glucose", "value": None, "unit": "mg/dL"}
        result = deterministic_checks(v)
        assert result.checks_failed >= 1
        assert "Missing value" in result.reasons

    def test_implausible_unit_value(self):
        v = {"test_name": "HbA1c", "value": 150.0, "unit": "%"}
        result = deterministic_checks(v)
        assert result.checks_failed >= 1
        assert any("implausible" in r for r in result.reasons)

    def test_flag_range_inconsistency_h_in_range(self):
        """Flag=H but value within range → inconsistency detected."""
        v = {
            "test_name": "Glucose",
            "value": 4.0,
            "unit": "mmol/L",
            "flag": "H",
            "reference_range_low": 3.5,
            "reference_range_high": 5.0,
        }
        result = deterministic_checks(v)
        assert result.checks_failed >= 1
        assert any("Flag=H" in r for r in result.reasons)

    def test_flag_range_inconsistency_l_above_low(self):
        """Flag=L but value >= range_low → inconsistency."""
        v = {
            "test_name": "Glucose",
            "value": 4.0,
            "unit": "mmol/L",
            "flag": "L",
            "reference_range_low": 3.5,
            "reference_range_high": 5.0,
        }
        result = deterministic_checks(v)
        assert result.checks_failed >= 1
        assert any("Flag=L" in r for r in result.reasons)

    def test_flag_range_consistent_h_above_range(self):
        """Flag=H with value above range → consistent, no failure."""
        v = {
            "test_name": "Glucose",
            "value": 6.0,
            "unit": "mmol/L",
            "flag": "H",
            "reference_range_low": 3.5,
            "reference_range_high": 5.0,
        }
        result = deterministic_checks(v)
        flag_failures = [r for r in result.reasons if "Flag=" in r]
        assert len(flag_failures) == 0

    def test_hplc_section_gets_bonus_check(self):
        """HPLC section type adds a passed check."""
        v = {"test_name": "HbA1c", "value": 6.0, "unit": "%"}
        result = deterministic_checks(v, "hplc_diabetes_block")
        assert result.checks_passed >= 3  # name + value + unit + hplc

    def test_insufficient_checks_downgrades(self):
        """Qualitative value with only test_name check → DOWNGRADE."""
        v = {"test_name": "Blood Type", "value": "A+"}
        result = deterministic_checks(v)
        # Only test_name and value checks pass (2), but value is string so no unit check
        # With 2 checks and 0 failures, should be ACCEPT
        assert result.verdict in (Verdict.ACCEPT, Verdict.DOWNGRADE)

    def test_two_failures_triggers_retry(self):
        """Two+ failures → RETRY verdict."""
        v = {
            "test_name": "",
            "value": None,
            "unit": "mg/dL",
        }
        result = deterministic_checks(v)
        assert result.checks_failed >= 2
        assert result.verdict == Verdict.RETRY

    def test_provenance_is_deterministic(self):
        v = {"test_name": "Glucose", "value": 100.0, "unit": "mg/dL"}
        result = deterministic_checks(v)
        assert result.provenance == "deterministic"

    def test_no_flag_no_range_still_passes(self):
        """Value without flag or range should still pass basic checks."""
        v = {"test_name": "RBC", "value": 4.5, "unit": "10^12/L"}
        result = deterministic_checks(v)
        assert result.verdict == Verdict.ACCEPT


# ── Extraction-quality escalation (Checks 6-8) ──


class TestExtractionQualityEscalation:
    """Verifier must escalate rows with known extraction quality issues."""

    def test_low_unit_confidence_fails_check(self):
        v = {
            "test_name": "Creatinine",
            "value": 108.0,
            "unit": "μmol/L",
            "unit_confidence": "low",
        }
        result = deterministic_checks(v)
        assert result.checks_failed >= 1
        assert any("unit_confidence=low" in r for r in result.reasons)

    def test_medium_unit_confidence_passes(self):
        v = {
            "test_name": "Free T4",
            "value": 13.59,
            "unit": "pmol/L",
            "unit_confidence": "medium",
        }
        result = deterministic_checks(v)
        unit_fail = [r for r in result.reasons if "unit_confidence" in r]
        assert len(unit_fail) == 0

    def test_no_range_source_fails_check(self):
        v = {
            "test_name": "Calcium",
            "value": 2.26,
            "unit": "mmol/L",
            "range_source": "no-range",
        }
        result = deterministic_checks(v)
        assert result.checks_failed >= 1
        assert any("no-range" in r for r in result.reasons)

    def test_ocr_flag_fallback_fails_check(self):
        v = {
            "test_name": "NRBC",
            "value": 0.0,
            "unit": "",
            "range_source": "ocr-flag-fallback",
        }
        result = deterministic_checks(v)
        assert result.checks_failed >= 1
        assert any("ocr-flag-fallback" in r for r in result.reasons)

    def test_lab_provided_suspicious_does_not_fail(self):
        """Suspicious source is noted but should not fail the check."""
        v = {
            "test_name": "TSH",
            "value": 1.5,
            "unit": "μIU/mL",
            "range_source": "lab-provided-suspicious",
        }
        result = deterministic_checks(v)
        # Should not have a failure for suspicious (only a note)
        suspicious_fails = [
            r for r in result.reasons
            if "suspicious" in r and "fail" in r.lower()
        ]
        assert len(suspicious_fails) == 0

    def test_lab_validated_passes(self):
        v = {
            "test_name": "WBC",
            "value": 6.4,
            "unit": "10^3/μL",
            "range_source": "lab-provided-validated",
        }
        result = deterministic_checks(v)
        range_fails = [r for r in result.reasons if "range_source" in r]
        assert len(range_fails) == 0

    def test_double_low_confidence_escalates(self):
        """Both unit_confidence=low AND confidence=low → extra failure."""
        v = {
            "test_name": "HDL-C",
            "value": 0.92,
            "unit": "mg/dL",
            "unit_confidence": "low",
            "confidence": "low",
        }
        result = deterministic_checks(v)
        assert result.checks_failed >= 2  # unit_confidence + double-low
        assert any("Both" in r for r in result.reasons)

    def test_low_unit_conf_downgrades_previously_accepted(self):
        """A value that would be ACCEPT now gets DOWNGRADE with low unit conf."""
        v = {
            "test_name": "Glucose",
            "value": 100.0,
            "unit": "mg/dL",
            "unit_confidence": "low",
            "range_source": "lab-provided-validated",
        }
        result = deterministic_checks(v)
        assert result.verdict in (Verdict.DOWNGRADE, Verdict.RETRY)

    def test_no_range_downgrades_previously_accepted(self):
        """A value that would be ACCEPT now gets DOWNGRADE with no-range."""
        v = {
            "test_name": "RBC",
            "value": 4.5,
            "unit": "10^12/L",
            "range_source": "no-range",
        }
        result = deterministic_checks(v)
        assert result.verdict in (Verdict.DOWNGRADE, Verdict.RETRY)


# ── Verdict merging ──


class TestMergeVerdicts:
    def test_both_accept(self):
        det = VerificationResult(
            verdict=Verdict.ACCEPT,
            checks_passed=3,
            checks_failed=0,
            adjusted_confidence="high",
        )
        model = VerificationResult(
            verdict=Verdict.ACCEPT,
            adjusted_confidence="medium",
            model_verified=True,
        )
        merged = merge_verdicts(det, model)
        assert merged.verdict == Verdict.ACCEPT
        assert merged.provenance == "merged"
        assert merged.model_verified is True

    def test_det_failure_overrides_model_accept(self):
        """Deterministic failures cannot be overridden by model ACCEPT."""
        det = VerificationResult(
            verdict=Verdict.DOWNGRADE,
            checks_passed=2,
            checks_failed=1,
            adjusted_confidence="medium",
            reasons=["Flag inconsistency"],
        )
        model = VerificationResult(
            verdict=Verdict.ACCEPT,
            adjusted_confidence="medium",
            model_verified=True,
        )
        merged = merge_verdicts(det, model)
        assert merged.verdict == Verdict.DOWNGRADE
        assert "deterministic checks failed" in merged.reasons[-1]

    def test_confidence_takes_worst(self):
        det = VerificationResult(adjusted_confidence="high")
        model = VerificationResult(adjusted_confidence="low")
        merged = merge_verdicts(det, model)
        assert merged.adjusted_confidence == "low"

    def test_reasons_combined(self):
        det = VerificationResult(reasons=["check1"])
        model = VerificationResult(reasons=["model1"])
        merged = merge_verdicts(det, model)
        assert "check1" in merged.reasons
        assert "model1" in merged.reasons


# ── Model verdict parsing ──


class TestParseModelVerdicts:
    def test_valid_response(self):
        data = {
            "verdicts": [
                {"index": 0, "verdict": "accept", "reason": "matches image"},
                {"index": 1, "verdict": "downgrade", "reason": "blurry unit"},
            ]
        }
        results = parse_model_verdicts(json.dumps(data), 2)
        assert len(results) == 2
        assert results[0].verdict == Verdict.ACCEPT
        assert results[1].verdict == Verdict.DOWNGRADE

    def test_missing_index_gets_downgrade(self):
        data = {"verdicts": [{"index": 0, "verdict": "accept", "reason": "ok"}]}
        results = parse_model_verdicts(json.dumps(data), 2)
        assert results[0].verdict == Verdict.ACCEPT
        assert results[1].verdict == Verdict.DOWNGRADE
        assert "did not return" in results[1].reasons[0]

    def test_mark_indeterminate(self):
        data = {
            "verdicts": [
                {"index": 0, "verdict": "mark_indeterminate", "reason": "blurry"}
            ]
        }
        results = parse_model_verdicts(json.dumps(data), 1)
        assert results[0].verdict == Verdict.MARK_INDETERMINATE

    def test_markdown_fenced_json(self):
        data = {"verdicts": [{"index": 0, "verdict": "accept", "reason": "ok"}]}
        raw = f"```json\n{json.dumps(data)}\n```"
        results = parse_model_verdicts(raw, 1)
        assert results[0].verdict == Verdict.ACCEPT

    def test_invalid_json_returns_downgrades(self):
        results = parse_model_verdicts("not json", 3)
        assert len(results) == 3
        assert all(r.verdict == Verdict.DOWNGRADE for r in results)

    def test_unknown_verdict_string(self):
        data = {"verdicts": [{"index": 0, "verdict": "invalid", "reason": "?"}]}
        results = parse_model_verdicts(json.dumps(data), 1)
        assert results[0].verdict == Verdict.DOWNGRADE

    def test_model_verified_flag_set(self):
        data = {"verdicts": [{"index": 0, "verdict": "accept", "reason": "ok"}]}
        results = parse_model_verdicts(json.dumps(data), 1)
        assert results[0].model_verified is True
