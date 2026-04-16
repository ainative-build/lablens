"""Tests for evaluation scoring logic (Phase 6).

Validates normalization, field-level comparison, archetype scoring,
and regression detection — all offline, no API calls.
"""

import json
import pytest
from pathlib import Path

# scoring.py lives in evaluation/ at project root — add to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))

from scoring import (
    ArchetypeScore,
    ValueMetrics,
    check_regression,
    match_value,
    normalize_test_name,
    score_archetype,
)


# --- normalize_test_name ---


class TestNormalizeTestName:
    def test_lowercase_strip(self):
        assert normalize_test_name("  White Blood Cells  ") == "white blood cells"

    def test_remove_brackets(self):
        assert normalize_test_name("HbA1c [Whole blood]") == "hba1c"

    def test_remove_parens(self):
        assert normalize_test_name("HbA1c (NGSP)") == "hba1c"

    def test_remove_footnote_markers(self):
        assert normalize_test_name("Glucose*") == "glucose"

    def test_collapse_whitespace(self):
        assert normalize_test_name("Red   Blood   Cells") == "red blood cells"

    def test_mixed_decorations(self):
        assert normalize_test_name("  AST (SGOT) [Serum]*  ") == "ast"

    def test_empty_string(self):
        assert normalize_test_name("") == ""

    def test_dagger_marker(self):
        assert normalize_test_name("WBC\u2020") == "wbc"


# --- match_value ---


class TestMatchValue:
    def test_exact_numeric_match(self):
        expected = {
            "test_name": "WBC", "value": 7.2, "unit": "10^9/L",
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "WBC", "value": 7.2, "unit": "10^9/L",
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted)
        assert m.test_name_match
        assert m.value_match
        assert m.unit_match
        assert m.section_match

    def test_value_within_tolerance(self):
        expected = {
            "test_name": "Glucose", "value": 100.0, "unit": "mg/dL",
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "Glucose", "value": 103.0, "unit": "mg/dL",
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted, tolerance=0.05)
        assert m.value_match  # 3% < 5%

    def test_value_outside_tolerance(self):
        expected = {
            "test_name": "Glucose", "value": 100.0, "unit": "mg/dL",
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "Glucose", "value": 120.0, "unit": "mg/dL",
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted, tolerance=0.05)
        assert not m.value_match  # 20% > 5%

    def test_section_type_mismatch(self):
        expected = {
            "test_name": "HbA1c", "value": 6.5, "unit": "%",
            "section_type": "hplc_diabetes_block",
        }
        extracted = {
            "test_name": "HbA1c", "value": 6.5, "unit": "%",
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted)
        assert not m.section_match

    def test_qualitative_value(self):
        expected = {
            "test_name": "HIV Ab", "value": "Negative",
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "HIV Ab", "value": "negative",
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted)
        assert m.value_match

    def test_zero_value(self):
        expected = {
            "test_name": "Test", "value": 0, "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "Test", "value": 0, "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted)
        assert m.value_match

    def test_range_match_within_tolerance(self):
        expected = {
            "test_name": "WBC", "value": 7.0,
            "reference_range_low": 4.0, "reference_range_high": 10.0,
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "WBC", "value": 7.0,
            "reference_range_low": 4.1, "reference_range_high": 10.3,
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted, tolerance=0.05)
        assert m.range_match  # both within 5%

    def test_range_mismatch(self):
        expected = {
            "test_name": "WBC", "value": 7.0,
            "reference_range_low": 4.0, "reference_range_high": 10.0,
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "WBC", "value": 7.0,
            "reference_range_low": 4.0, "reference_range_high": 12.0,
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted, tolerance=0.05)
        assert not m.range_match  # high bound 20% off

    def test_flag_match(self):
        expected = {
            "test_name": "X", "value": 1, "flag": "H",
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "X", "value": 1, "flag": "h",
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted)
        assert m.flag_match  # case-insensitive

    def test_flag_mismatch(self):
        expected = {
            "test_name": "X", "value": 1, "flag": "H",
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "X", "value": 1, "flag": "L",
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted)
        assert not m.flag_match

    def test_unit_both_empty(self):
        expected = {
            "test_name": "X", "value": 1, "unit": None,
            "section_type": "standard_lab_table",
        }
        extracted = {
            "test_name": "X", "value": 1,
            "section_type": "standard_lab_table",
        }
        m = match_value(expected, extracted)
        assert m.unit_match


# --- ArchetypeScore properties ---


class TestArchetypeScore:
    def test_recall(self):
        s = ArchetypeScore(archetype="test", total_expected=10, matched=7)
        assert s.recall == pytest.approx(0.7)

    def test_precision(self):
        s = ArchetypeScore(archetype="test", total_extracted=10, matched=8)
        assert s.precision == pytest.approx(0.8)

    def test_empty_metrics(self):
        s = ArchetypeScore(archetype="test")
        assert s.recall == 0
        assert s.precision == 0
        assert s.section_accuracy == 0
        assert s.value_accuracy == 0
        assert s.unit_accuracy == 0

    def test_section_accuracy(self):
        s = ArchetypeScore(
            archetype="test",
            value_metrics=[
                ValueMetrics(section_match=True),
                ValueMetrics(section_match=True),
                ValueMetrics(section_match=False),
            ],
        )
        assert s.section_accuracy == pytest.approx(2 / 3)


# --- score_archetype ---


class TestScoreArchetype:
    def test_perfect_match(self, tmp_path):
        gt = {
            "archetype": "test",
            "expected_values": [
                {"test_name": "WBC", "value": 7.2, "unit": "10^9/L",
                 "section_type": "standard_lab_table"},
            ],
            "expected_sections": [],
            "expected_screening": [],
            "expected_hplc": [],
        }
        output = {
            "values": [
                {"test_name": "WBC", "value": 7.2, "unit": "10^9/L",
                 "section_type": "standard_lab_table"},
            ],
        }
        gt_file = tmp_path / "test.json"
        out_file = tmp_path / "test_out.json"
        gt_file.write_text(json.dumps(gt))
        out_file.write_text(json.dumps(output))

        score = score_archetype(gt_file, out_file)
        assert score.recall == 1.0
        assert score.precision == 1.0
        assert score.value_accuracy == 1.0

    def test_missing_extraction(self, tmp_path):
        gt = {
            "archetype": "test",
            "expected_values": [
                {"test_name": "WBC", "value": 7.2, "section_type": "standard_lab_table"},
                {"test_name": "RBC", "value": 5.0, "section_type": "standard_lab_table"},
            ],
            "expected_sections": [],
            "expected_screening": [],
            "expected_hplc": [],
        }
        output = {
            "values": [
                {"test_name": "WBC", "value": 7.2, "section_type": "standard_lab_table"},
            ],
        }
        gt_file = tmp_path / "test.json"
        out_file = tmp_path / "test_out.json"
        gt_file.write_text(json.dumps(gt))
        out_file.write_text(json.dumps(output))

        score = score_archetype(gt_file, out_file)
        assert score.recall == pytest.approx(0.5)

    def test_screening_sub_score(self, tmp_path):
        gt = {
            "archetype": "test",
            "expected_values": [],
            "expected_sections": [],
            "expected_screening": [
                {"test_type": "SPOT-MAS ctDNA", "result_status": "not_detected"},
            ],
            "expected_hplc": [],
        }
        output = {
            "values": [],
            "screening_results": [
                {"test_type": "SPOT-MAS ctDNA", "result_status": "not_detected"},
            ],
        }
        gt_file = tmp_path / "test.json"
        out_file = tmp_path / "test_out.json"
        gt_file.write_text(json.dumps(gt))
        out_file.write_text(json.dumps(output))

        score = score_archetype(gt_file, out_file)
        assert score.screening_expected == 1
        assert score.screening_matched == 1

    def test_hplc_sub_score(self, tmp_path):
        gt = {
            "archetype": "test",
            "expected_values": [],
            "expected_sections": [],
            "expected_screening": [],
            "expected_hplc": [
                {"ngsp_value": 5.6, "ifcc_value": 38,
                 "eag_value": 114, "diabetes_category": "normal"},
            ],
        }
        output = {
            "values": [],
            "audit": {
                "hplc_blocks": [
                    {"diabetes_category": "normal", "cross_check_passed": True},
                ],
            },
        }
        gt_file = tmp_path / "test.json"
        out_file = tmp_path / "test_out.json"
        gt_file.write_text(json.dumps(gt))
        out_file.write_text(json.dumps(output))

        score = score_archetype(gt_file, out_file)
        assert score.hplc_expected == 1
        assert score.hplc_category_matched == 1


# --- check_regression ---


class TestRegression:
    def test_missing_value_regression(self, tmp_path):
        golden = {"values": [{"test_name": "WBC", "value": 7.2}]}
        current = {"values": []}
        golden_file = tmp_path / "golden.json"
        golden_file.write_text(json.dumps(golden))
        diffs = check_regression(current, golden_file)
        assert any("REGRESSION" in d for d in diffs)

    def test_value_change_regression(self, tmp_path):
        golden = {"values": [{"test_name": "WBC", "value": 7.2}]}
        current = {"values": [{"test_name": "WBC", "value": 8.0}]}
        golden_file = tmp_path / "golden.json"
        golden_file.write_text(json.dumps(golden))
        diffs = check_regression(current, golden_file)
        assert any("VALUE CHANGE" in d for d in diffs)

    def test_no_regression(self, tmp_path):
        golden = {"values": [{"test_name": "WBC", "value": 7.2}]}
        current = {"values": [{"test_name": "WBC", "value": 7.2}]}
        golden_file = tmp_path / "golden.json"
        golden_file.write_text(json.dumps(golden))
        diffs = check_regression(current, golden_file)
        assert len(diffs) == 0

    def test_no_golden_file(self, tmp_path):
        current = {"values": [{"test_name": "WBC", "value": 7.2}]}
        golden_file = tmp_path / "nonexistent.json"
        diffs = check_regression(current, golden_file)
        assert len(diffs) == 0
