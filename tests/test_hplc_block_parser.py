"""Tests for HPLC block parser: analyte identification, cross-check, categorization."""

import pytest

from lablens.extraction.hplc_block_parser import (
    ADA_NORMAL_MAX,
    ADA_PREDIABETES_MAX,
    EAG_MGDL_SLOPE,
    EAG_MGDL_INTERCEPT,
    EAG_MGDL_TOLERANCE,
    EAG_MMOL_TOLERANCE,
    HPLCBlockParser,
    IFCC_INTERCEPT,
    IFCC_SLOPE,
    IFCC_TOLERANCE,
    MMOL_TO_MGDL,
)
from lablens.models.hplc_block import DiabetesCategory


@pytest.fixture
def parser():
    return HPLCBlockParser()


# ── Analyte identification ──


class TestIdentifyAnalyte:
    def test_ngsp_by_name_and_percent(self, parser):
        row = {"test_name": "HbA1c (NGSP)", "unit": "%"}
        assert parser._identify_analyte(row) == "ngsp"

    def test_ifcc_by_name(self, parser):
        row = {"test_name": "HbA1c (IFCC)", "unit": "mmol/mol"}
        assert parser._identify_analyte(row) == "ifcc"

    def test_ifcc_by_unit_only(self, parser):
        """mmol/mol unit should identify IFCC even without keyword."""
        row = {"test_name": "Hemoglobin A1c", "unit": "mmol/mol"}
        assert parser._identify_analyte(row) == "ifcc"

    def test_eag_by_name(self, parser):
        row = {"test_name": "eAG", "unit": "mg/dL"}
        assert parser._identify_analyte(row) == "eag"

    def test_eag_full_name(self, parser):
        row = {"test_name": "Estimated Average Glucose", "unit": "mmol/L"}
        assert parser._identify_analyte(row) == "eag"

    def test_bare_hba1c_without_unit_returns_none(self, parser):
        """Red-team #13: bare HbA1c without identifiable unit must NOT default to NGSP."""
        row = {"test_name": "HbA1c", "unit": ""}
        assert parser._identify_analyte(row) is None

    def test_bare_hba1c_with_unknown_unit_returns_none(self, parser):
        row = {"test_name": "HbA1c", "unit": "unknown"}
        assert parser._identify_analyte(row) is None

    def test_unrelated_row_returns_none(self, parser):
        row = {"test_name": "Glucose", "unit": "mg/dL"}
        assert parser._identify_analyte(row) is None

    def test_a1c_with_percent_is_ngsp(self, parser):
        row = {"test_name": "A1C", "unit": "%"}
        assert parser._identify_analyte(row) == "ngsp"


# ── Cross-check validation ──


class TestCrossCheck:
    def _make_rows(self, ngsp_val, ifcc_val, eag_val, eag_unit="mg/dL"):
        rows = []
        if ngsp_val is not None:
            rows.append({"test_name": "HbA1c (NGSP)", "value": ngsp_val, "unit": "%"})
        if ifcc_val is not None:
            rows.append({"test_name": "HbA1c (IFCC)", "value": ifcc_val, "unit": "mmol/mol"})
        if eag_val is not None:
            rows.append({"test_name": "eAG", "value": eag_val, "unit": eag_unit})
        return rows

    def test_consistent_ngsp_ifcc(self, parser):
        """NGSP 6.0% → expected IFCC = 10.93*6.0 - 23.5 = 42.08."""
        expected_ifcc = (IFCC_SLOPE * 6.0) + IFCC_INTERCEPT
        block = parser.parse_rows(self._make_rows(6.0, round(expected_ifcc, 1), None))
        assert block.cross_check_passed is True
        assert len(block.consistency_flags) == 0

    def test_inconsistent_ngsp_ifcc(self, parser):
        """NGSP 6.0% with IFCC 20 (expected ~42) should fail."""
        block = parser.parse_rows(self._make_rows(6.0, 20.0, None))
        assert block.cross_check_passed is False
        assert len(block.consistency_flags) == 1
        assert "NGSP-IFCC mismatch" in block.consistency_flags[0]

    def test_consistent_ngsp_eag_mgdl(self, parser):
        """NGSP 6.0% → expected eAG = 28.7*6.0 - 46.7 = 125.5 mg/dL."""
        expected_eag = (EAG_MGDL_SLOPE * 6.0) + EAG_MGDL_INTERCEPT
        block = parser.parse_rows(self._make_rows(6.0, None, round(expected_eag, 1)))
        assert block.cross_check_passed is True

    def test_inconsistent_ngsp_eag(self, parser):
        """NGSP 6.0% with eAG 200 mg/dL (expected ~125.5) should fail."""
        block = parser.parse_rows(self._make_rows(6.0, None, 200.0))
        assert block.cross_check_passed is False
        assert "NGSP-eAG mismatch" in block.consistency_flags[0]

    def test_eag_mmol_tolerance(self, parser):
        """eAG in mmol/L uses different tolerance."""
        ngsp = 6.0
        expected_eag_mgdl = (EAG_MGDL_SLOPE * ngsp) + EAG_MGDL_INTERCEPT
        expected_eag_mmol = expected_eag_mgdl / MMOL_TO_MGDL
        block = parser.parse_rows(
            self._make_rows(ngsp, None, round(expected_eag_mmol, 2), "mmol/L")
        )
        assert block.cross_check_passed is True

    def test_ifcc_within_tolerance(self, parser):
        """IFCC within +/-2 mmol/mol of expected should pass."""
        expected_ifcc = (IFCC_SLOPE * 5.5) + IFCC_INTERCEPT
        # Just inside tolerance
        block = parser.parse_rows(
            self._make_rows(5.5, expected_ifcc + IFCC_TOLERANCE - 0.1, None)
        )
        assert block.cross_check_passed is True

    def test_ifcc_outside_tolerance(self, parser):
        """IFCC beyond +/-2 mmol/mol of expected should fail."""
        expected_ifcc = (IFCC_SLOPE * 5.5) + IFCC_INTERCEPT
        block = parser.parse_rows(
            self._make_rows(5.5, expected_ifcc + IFCC_TOLERANCE + 1.0, None)
        )
        assert block.cross_check_passed is False

    def test_single_analyte_vacuously_passes(self, parser):
        """Only 1 analyte → nothing to cross-check → passes vacuously."""
        block = parser.parse_rows(self._make_rows(6.0, None, None))
        assert block.cross_check_passed is True

    def test_all_three_consistent(self, parser):
        """Full triple: NGSP 6.0, IFCC 42.1, eAG 125.5."""
        ngsp = 6.0
        ifcc = round((IFCC_SLOPE * ngsp) + IFCC_INTERCEPT, 1)
        eag = round((EAG_MGDL_SLOPE * ngsp) + EAG_MGDL_INTERCEPT, 1)
        block = parser.parse_rows(self._make_rows(ngsp, ifcc, eag))
        assert block.cross_check_passed is True
        assert block.completeness == 3


# ── ADA diabetes categorization ──


class TestCategorize:
    def _make_consistent_rows(self, ngsp_val):
        """Build consistent NGSP+IFCC rows for categorization test."""
        ifcc = round((IFCC_SLOPE * ngsp_val) + IFCC_INTERCEPT, 1)
        return [
            {"test_name": "HbA1c (NGSP)", "value": ngsp_val, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": ifcc, "unit": "mmol/mol"},
        ]

    def test_normal(self, parser):
        block = parser.parse_rows(self._make_consistent_rows(5.5))
        assert block.diabetes_category == DiabetesCategory.NORMAL

    def test_prediabetes(self, parser):
        block = parser.parse_rows(self._make_consistent_rows(6.0))
        assert block.diabetes_category == DiabetesCategory.PREDIABETES

    def test_diabetes(self, parser):
        block = parser.parse_rows(self._make_consistent_rows(7.0))
        assert block.diabetes_category == DiabetesCategory.DIABETES

    def test_boundary_normal_prediabetes(self, parser):
        """5.7% is the boundary — at exactly 5.7 should be prediabetes."""
        block = parser.parse_rows(self._make_consistent_rows(5.7))
        assert block.diabetes_category == DiabetesCategory.PREDIABETES

    def test_boundary_prediabetes_diabetes(self, parser):
        """6.5% is the boundary — at exactly 6.5 should be diabetes."""
        block = parser.parse_rows(self._make_consistent_rows(6.5))
        assert block.diabetes_category == DiabetesCategory.DIABETES

    def test_ifcc_only_derives_ngsp_and_categorizes(self, parser):
        """IFCC=42.0 alone → NGSP derived (6.0) → prediabetes."""
        rows = [{"test_name": "HbA1c (IFCC)", "value": 42.0, "unit": "mmol/mol"}]
        block = parser.parse_rows(rows)
        assert block.ngsp is not None
        assert block.ngsp.source == "derived-from-ifcc"
        assert block.diabetes_category == DiabetesCategory.PREDIABETES

    def test_cross_check_failure_forces_indeterminate(self, parser):
        """Even with valid NGSP, failed cross-check → indeterminate."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 6.0, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 20.0, "unit": "mmol/mol"},  # Way off
        ]
        block = parser.parse_rows(rows)
        assert block.cross_check_passed is False
        assert block.diabetes_category == DiabetesCategory.INDETERMINATE

    def test_single_ngsp_derives_full_block(self, parser):
        """Single NGSP derives IFCC+eAG → completeness=3, category assigned."""
        rows = [{"test_name": "HbA1c (NGSP)", "value": 7.2, "unit": "%"}]
        block = parser.parse_rows(rows)
        assert block.completeness == 3
        assert block.ifcc is not None
        assert block.ifcc.source == "derived-from-ngsp"
        assert block.eag is not None
        assert block.eag.source == "derived-from-ngsp"
        assert block.cross_check_passed is True
        assert block.diabetes_category == DiabetesCategory.DIABETES


# ── Completeness tracking ──


class TestCompleteness:
    def test_empty(self, parser):
        block = parser.parse_rows([])
        assert block.completeness == 0

    def test_one_ocr_analyte_derives_full_block(self, parser):
        """Single OCR analyte → derivation fills rest → completeness=3."""
        rows = [{"test_name": "HbA1c (NGSP)", "value": 5.5, "unit": "%"}]
        block = parser.parse_rows(rows)
        assert block.completeness == 3
        assert block.ngsp.source == "ocr"
        assert block.ifcc.source == "derived-from-ngsp"
        assert block.eag.source == "derived-from-ngsp"

    def test_two_ocr_analytes_derive_third(self, parser):
        """Two OCR analytes → derivation fills eAG → completeness=3."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 5.5, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 36.6, "unit": "mmol/mol"},
        ]
        block = parser.parse_rows(rows)
        assert block.completeness == 3
        assert block.eag.source == "derived-from-ngsp"

    def test_three_analytes(self, parser):
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 5.5, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 36.6, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": 111.2, "unit": "mg/dL"},
        ]
        block = parser.parse_rows(rows)
        assert block.completeness == 3

    def test_none_value_ocr_row_replaced_by_derivation(self, parser):
        """OCR row with None value ignored; eAG derives NGSP+IFCC → completeness=3."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": None, "unit": "%"},
            {"test_name": "eAG", "value": 125.0, "unit": "mg/dL"},
        ]
        block = parser.parse_rows(rows)
        assert block.completeness == 3
        assert block.ngsp.source == "derived-from-eag"
        assert block.ifcc.source == "derived-from-ngsp"

    def test_string_value_converted(self, parser):
        """String numeric values should be converted to float."""
        rows = [{"test_name": "HbA1c (NGSP)", "value": "5.8", "unit": "%"}]
        block = parser.parse_rows(rows)
        assert block.ngsp.value == 5.8
        assert block.completeness == 3  # derivation fills IFCC + eAG


# ── Value-range plausibility reclassification ──


class TestPlausibilityReclassification:
    """Verify _fix_misidentified_analytes corrects OCR misclassification."""

    def test_ifcc_slot_with_ngsp_value_reclassified(self, parser):
        """IFCC=5.1 (clearly NGSP %) → reclassified to NGSP, IFCC derived."""
        rows = [
            {"test_name": "HbA1c (IFCC)", "value": 5.1, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": 100.0, "unit": "mg/dL"},
        ]
        block = parser.parse_rows(rows)
        # Value should have been reclassified to NGSP
        assert block.ngsp is not None
        assert block.ngsp.value == 5.1
        assert block.ngsp.unit == "%"
        # IFCC derived from corrected NGSP
        assert block.ifcc is not None
        assert block.ifcc.source == "derived-from-ngsp"
        # Should still categorize correctly as normal (<5.7%)
        assert block.diabetes_category == DiabetesCategory.NORMAL

    def test_ifcc_slot_with_5_53_reclassified(self, parser):
        """IFCC=5.53 is actually NGSP → reclassified, missing values derived.

        Without eAG, no recovery needed. IFCC/eAG derived from NGSP.
        """
        rows = [
            {"test_name": "HbA1c (IFCC)", "value": 5.53, "unit": "mmol/mol"},
        ]
        block = parser.parse_rows(rows)
        assert block.ngsp is not None
        assert block.ngsp.value == 5.53
        # IFCC and eAG derived from reclassified NGSP
        assert block.ifcc is not None
        assert block.ifcc.source == "derived-from-ngsp"
        assert block.eag is not None
        assert block.eag.source == "derived-from-ngsp"
        assert block.completeness == 3
        assert block.diabetes_category == DiabetesCategory.NORMAL

    def test_ifcc_reclassified_with_consistent_eag(self, parser):
        """Reclassified NGSP=5.53 with consistent eAG → cross-check passes."""
        from lablens.extraction.hplc_block_parser import (
            EAG_MGDL_INTERCEPT,
            EAG_MGDL_SLOPE,
        )
        expected_eag = round(EAG_MGDL_SLOPE * 5.53 + EAG_MGDL_INTERCEPT, 1)
        rows = [
            {"test_name": "HbA1c (IFCC)", "value": 5.53, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": expected_eag, "unit": "mg/dL"},
        ]
        block = parser.parse_rows(rows)
        assert block.ngsp is not None
        assert block.ngsp.value == 5.53
        assert block.cross_check_passed is True
        assert block.diabetes_category == DiabetesCategory.NORMAL

    def test_valid_ifcc_not_reclassified(self, parser):
        """Real IFCC value (33.0 mmol/mol) should NOT be reclassified.
        NGSP is derived from IFCC instead.
        """
        rows = [
            {"test_name": "HbA1c (IFCC)", "value": 33.0, "unit": "mmol/mol"},
        ]
        block = parser.parse_rows(rows)
        assert block.ifcc is not None
        assert block.ifcc.value == 33.0
        assert block.ifcc.source == "ocr"
        # NGSP derived from IFCC (not reclassified)
        assert block.ngsp is not None
        assert block.ngsp.source == "derived-from-ifcc"

    def test_ngsp_slot_with_ifcc_value_reclassified(self, parser):
        """NGSP=42.0 (clearly IFCC mmol/mol) → reclassified, NGSP derived."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 42.0, "unit": "%"},
        ]
        block = parser.parse_rows(rows)
        assert block.ifcc is not None
        assert block.ifcc.value == 42.0
        assert block.ifcc.unit == "mmol/mol"
        # NGSP derived from reclassified IFCC
        assert block.ngsp is not None
        assert block.ngsp.source == "derived-from-ifcc"

    def test_eag_low_mgdl_corrected_to_mmol(self, parser):
        """eAG=5.53 in mg/dL is implausible → correct to mmol/L."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 5.1, "unit": "%"},
            {"test_name": "eAG", "value": 5.53, "unit": "mg/dL"},
        ]
        block = parser.parse_rows(rows)
        assert block.eag_unit == "mmol/L"
        assert block.eag.unit == "mmol/L"  # analyte unit must stay in sync

    def test_eag_unit_synced_to_analyte_on_parse(self, parser):
        """eag.unit must reflect eag_unit default when OCR provides no unit."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 5.1, "unit": "%"},
            {"test_name": "eAG", "value": 115.0, "unit": ""},
        ]
        block = parser.parse_rows(rows)
        assert block.eag_unit == "mg/dL"
        assert block.eag.unit == "mg/dL"

    def test_reclassified_ngsp_recovered_from_eag(self, parser):
        """THE regression fix: IFCC=5.53 + eAG=100 mg/dL.

        LLM puts eAG-mmol/L (5.53) into IFCC slot. Reclassifier moves
        to NGSP but it's the wrong value. Recovery re-derives NGSP from
        eAG=100 → NGSP=5.1, then derives IFCC. All three values present,
        cross-check passes, category=normal.
        """
        rows = [
            {"test_name": "HbA1c (IFCC)", "value": 5.53, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": 100.0, "unit": "mg/dL"},
        ]
        block = parser.parse_rows(rows)
        # NGSP re-derived from eAG (not the reclassified 5.53)
        assert block.ngsp is not None
        assert block.ngsp.source == "derived-from-eag"
        assert 5.0 <= block.ngsp.value <= 5.2  # should be ~5.1
        # IFCC derived from corrected NGSP
        assert block.ifcc is not None
        assert block.ifcc.source == "derived-from-ngsp"
        assert 30 <= block.ifcc.value <= 35  # should be ~32
        # eAG preserved from OCR
        assert block.eag is not None
        assert block.eag.value == 100.0
        # Full completeness, cross-check passes, category normal
        assert block.completeness == 3
        assert block.cross_check_passed is True
        assert block.diabetes_category == DiabetesCategory.NORMAL

    def test_derivation_with_eag_mmol(self, parser):
        """eAG in mmol/L (5.53) + NGSP=5.1 → IFCC derived, eAG unit corrected."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 5.1, "unit": "%"},
            {"test_name": "eAG", "value": 5.53, "unit": "mg/dL"},
        ]
        block = parser.parse_rows(rows)
        # eAG unit corrected to mmol/L
        assert block.eag_unit == "mmol/L"
        # IFCC derived from NGSP
        assert block.ifcc is not None
        assert block.ifcc.source == "derived-from-ngsp"
        assert block.completeness == 3
        assert block.diabetes_category == DiabetesCategory.NORMAL

    def test_both_ngsp_and_ifcc_present_no_reclassification(self, parser):
        """When both slots are filled, no reclassification should occur."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 5.1, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 33.0, "unit": "mmol/mol"},
        ]
        block = parser.parse_rows(rows)
        assert block.ngsp.value == 5.1
        assert block.ifcc.value == 33.0


# ── Integration: HPLC interpretation routing ──


class TestHPLCInterpretation:
    """Test engine early-return for HPLC values with diabetes category."""

    def test_hplc_normal_in_range(self):
        from lablens.interpretation.engine import InterpretationEngine

        engine = InterpretationEngine()
        v = {
            "test_name": "HbA1c (NGSP)",
            "value": 5.2,
            "unit": "%",
            "hplc_diabetes_category": "normal",
        }
        result = engine._interpret_single(v, "high")
        assert result.direction == "in-range"
        assert result.severity == "normal"
        assert result.range_source == "hplc-cross-check"
        assert result.confidence == "high"

    def test_hplc_prediabetes_high_mild(self):
        from lablens.interpretation.engine import InterpretationEngine

        engine = InterpretationEngine()
        v = {
            "test_name": "HbA1c (NGSP)",
            "value": 6.0,
            "unit": "%",
            "hplc_diabetes_category": "prediabetes",
        }
        result = engine._interpret_single(v, "high")
        assert result.direction == "high"
        assert result.severity == "mild"
        assert result.actionability == "monitor"

    def test_hplc_diabetes_high_moderate(self):
        from lablens.interpretation.engine import InterpretationEngine

        engine = InterpretationEngine()
        v = {
            "test_name": "HbA1c (NGSP)",
            "value": 7.5,
            "unit": "%",
            "hplc_diabetes_category": "diabetes",
        }
        result = engine._interpret_single(v, "high")
        assert result.direction == "high"
        assert result.severity == "moderate"
        assert result.actionability == "consult"

    def test_hplc_indeterminate_low_confidence(self):
        from lablens.interpretation.engine import InterpretationEngine

        engine = InterpretationEngine()
        v = {
            "test_name": "HbA1c (NGSP)",
            "value": 6.0,
            "unit": "%",
            "hplc_diabetes_category": "indeterminate",
        }
        result = engine._interpret_single(v, "high")
        assert result.direction == "indeterminate"
        assert result.confidence == "low"

    def test_hplc_evidence_trace_has_category(self):
        from lablens.interpretation.engine import InterpretationEngine

        engine = InterpretationEngine()
        v = {
            "test_name": "HbA1c (NGSP)",
            "value": 6.0,
            "unit": "%",
            "hplc_diabetes_category": "prediabetes",
        }
        result = engine._interpret_single(v, "high")
        assert result.evidence_trace["hplc_diabetes_category"] == "prediabetes"
