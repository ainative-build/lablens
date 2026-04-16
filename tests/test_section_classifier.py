"""Tests for deterministic section classifier."""

import pytest

from lablens.extraction.section_classifier import SectionClassifier, _score_row
from lablens.models.section_types import ClassifiedBlock, SectionType


@pytest.fixture
def classifier():
    return SectionClassifier()


# --- Page-level classification (Pass 1) ---


class TestPageLevelClassification:
    """Pass 1: raw text scan for screening and appendix pages."""

    def test_screening_page_detected(self, classifier):
        raw_text = (
            "SPOT-MAS ctDNA Screening Report\n"
            "Multi-cancer early detection test\n"
            "Result: Not Detected"
        )
        blocks = classifier.classify_page(raw_text, [])
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.SCREENING_ATTACHMENT
        assert blocks[0].confidence >= 0.90
        assert any("spot-mas" in kw for kw in blocks[0].trigger_keywords)

    def test_screening_page_vietnamese(self, classifier):
        raw_text = (
            "Kết quả tầm soát ung thư bằng ctDNA\n"
            "Chưa phát hiện bất thường"
        )
        blocks = classifier.classify_page(raw_text, [])
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.SCREENING_ATTACHMENT

    def test_screening_needs_2_keywords(self, classifier):
        """Single screening keyword should NOT trigger page-level classification."""
        raw_text = "Some normal text with screening word in it"
        rows = [{"test_name": "WBC", "value": 7.2, "unit": "10^9/L"}]
        blocks = classifier.classify_page(raw_text, rows)
        # Should fall through to row-level (Pass 2), not screening
        assert blocks[0].section_type != SectionType.SCREENING_ATTACHMENT

    def test_appendix_page_detected(self, classifier):
        raw_text = (
            "Methodology and Procedure Notes\n"
            "Specimen requirement: 5 mL whole blood\n"
            "Certification: ISO 15189 accreditation\n"
            "Note: Results should be interpreted in context"
        )
        blocks = classifier.classify_page(raw_text, [])
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.APPENDIX_TEXT

    def test_standard_page_no_special_keywords(self, classifier):
        raw_text = "Complete Blood Count results page 1"
        rows = [
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L"},
            {"test_name": "RBC", "value": 4.5, "unit": "10^12/L"},
        ]
        blocks = classifier.classify_page(raw_text, rows)
        assert blocks[0].section_type == SectionType.STANDARD_LAB_TABLE


# --- Row-level classification (Pass 2) ---


class TestRowLevelClassification:
    """Pass 2: sub-block detection within parsed rows."""

    def test_pure_standard_page(self, classifier):
        rows = [
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L"},
            {"test_name": "RBC", "value": 4.5, "unit": "10^12/L"},
            {"test_name": "Hemoglobin", "value": 14.0, "unit": "g/dL"},
        ]
        blocks = classifier.classify_page("standard page", rows)
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.STANDARD_LAB_TABLE
        assert blocks[0].confidence == 1.0

    def test_pure_hplc_block(self, classifier):
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 6.0, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 42, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": 126, "unit": "mg/dL"},
        ]
        blocks = classifier.classify_page("lab results", rows)
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.HPLC_DIABETES_BLOCK
        assert len(blocks[0].rows) == 3

    def test_mixed_page_standard_then_hplc(self, classifier):
        """Standard rows followed by HPLC block → 2 sub-blocks."""
        rows = [
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L"},
            {"test_name": "RBC", "value": 4.5, "unit": "10^12/L"},
            {"test_name": "Hemoglobin", "value": 14.0, "unit": "g/dL"},
            # Transition to HPLC
            {"test_name": "HbA1c (NGSP)", "value": 6.0, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 42, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": 126, "unit": "mg/dL"},
        ]
        blocks = classifier.classify_page("mixed page", rows)
        assert len(blocks) == 2
        assert blocks[0].section_type == SectionType.STANDARD_LAB_TABLE
        assert blocks[1].section_type == SectionType.HPLC_DIABETES_BLOCK
        assert len(blocks[0].rows) == 3
        assert len(blocks[1].rows) == 3

    def test_single_hplc_row_absorbed_by_standard(self, classifier):
        """Single HPLC-keyword row among standard rows → absorbed (noise tolerance)."""
        rows = [
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L"},
            {"test_name": "HbA1c", "value": 6.0, "unit": "%"},
            {"test_name": "RBC", "value": 4.5, "unit": "10^12/L"},
            {"test_name": "Hemoglobin", "value": 14.0, "unit": "g/dL"},
        ]
        blocks = classifier.classify_page("standard page", rows)
        # Single HbA1c row should be absorbed into the standard block
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.STANDARD_LAB_TABLE
        assert len(blocks[0].rows) == 4

    def test_empty_rows_returns_standard(self, classifier):
        blocks = classifier.classify_page("empty page", [])
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.STANDARD_LAB_TABLE

    def test_hormone_block_detected(self, classifier):
        rows = [
            {"test_name": "TSH", "value": 2.5, "unit": "mIU/L"},
            {"test_name": "Free T4", "value": 1.2, "unit": "ng/dL"},
            {"test_name": "Free T3", "value": 3.1, "unit": "pg/mL"},
        ]
        blocks = classifier.classify_page("thyroid panel", rows)
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.HORMONE_IMMUNOLOGY_BLOCK


# --- Row scoring ---


class TestRowScoring:
    """Unit tests for individual row scoring."""

    def test_hba1c_ngsp_is_hplc(self):
        stype, conf, kws = _score_row(
            {"test_name": "HbA1c (NGSP)", "value": 6.0, "unit": "%"}
        )
        assert stype == SectionType.HPLC_DIABETES_BLOCK
        assert len(kws) > 0

    def test_plain_wbc_is_standard(self):
        stype, conf, kws = _score_row(
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L"}
        )
        assert stype == SectionType.STANDARD_LAB_TABLE
        assert conf == 1.0
        assert kws == []

    def test_tsh_is_hormone(self):
        stype, _, kws = _score_row(
            {"test_name": "TSH", "value": 2.5, "unit": "mIU/L"}
        )
        assert stype == SectionType.HORMONE_IMMUNOLOGY_BLOCK
        assert "tsh" in kws

    def test_eag_is_hplc(self):
        stype, _, kws = _score_row(
            {"test_name": "Estimated Average Glucose", "value": 126, "unit": "mg/dL"}
        )
        assert stype == SectionType.HPLC_DIABETES_BLOCK


# --- Confidence scoring ---


class TestConfidenceScoring:
    """Verify confidence scales with keyword count."""

    def test_3_plus_keywords_high_confidence(self, classifier):
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 6.0, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 42, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": 126, "unit": "mg/dL"},
        ]
        blocks = classifier.classify_page("page", rows)
        assert blocks[0].confidence >= 0.90

    def test_default_standard_is_1_0(self, classifier):
        rows = [{"test_name": "WBC", "value": 7.2, "unit": "10^9/L"}]
        blocks = classifier.classify_page("page", rows)
        assert blocks[0].confidence == 1.0


# --- Word-boundary matching (false-positive prevention) ---


class TestKeywordBoundaryMatching:
    """Verify _find_keywords uses word boundaries, not substring matching."""

    def test_eag_not_in_reagent(self):
        """'eag' must NOT match inside 'reagent'."""
        stype, _, kws = _score_row(
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L",
             "reference_range_text": "See reagent insert"}
        )
        assert stype == SectionType.STANDARD_LAB_TABLE
        assert kws == []

    def test_amh_not_in_amherst(self):
        """'amh' must NOT match inside 'amherst'."""
        stype, _, kws = _score_row(
            {"test_name": "Glucose [Amherst Lab]", "value": 90, "unit": "mg/dL"}
        )
        assert stype == SectionType.STANDARD_LAB_TABLE

    def test_hplc_not_in_methodology(self):
        """'hplc' in methodology text should still match at row level
        (it IS a valid HPLC keyword when standalone)."""
        stype, _, kws = _score_row(
            {"test_name": "HbA1c", "value": 6.0, "unit": "%",
             "reference_range_text": "method: hplc"}
        )
        assert stype == SectionType.HPLC_DIABETES_BLOCK

    def test_screening_not_in_prescreening(self, classifier):
        """'screening' must NOT match inside 'prescreening' at page level."""
        raw_text = "This is a prescreening form for the prescreening process"
        blocks = classifier.classify_page(raw_text, [])
        assert blocks[0].section_type != SectionType.SCREENING_ATTACHMENT

    def test_multi_word_keyword_matches(self):
        """Multi-word keywords like 'cell-free dna' still work."""
        stype, _, kws = _score_row(
            {"test_name": "cell-free dna analysis", "value": "0.03", "unit": ""}
        )
        assert stype == SectionType.SCREENING_ATTACHMENT
        assert "cell-free dna" in kws

    def test_eag_standalone_matches(self):
        """'eag' as standalone word should still match."""
        stype, _, kws = _score_row(
            {"test_name": "eAG", "value": 126, "unit": "mg/dL"}
        )
        assert stype == SectionType.HPLC_DIABETES_BLOCK


# --- Multi-block transitions ---


class TestMultiBlockTransitions:
    """Edge cases for block splitting and transitions."""

    def test_hplc_then_standard(self, classifier):
        """HPLC rows followed by standard rows → 2 blocks."""
        rows = [
            {"test_name": "HbA1c (NGSP)", "value": 6.0, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 42, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": 126, "unit": "mg/dL"},
            # Transition to standard
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L"},
            {"test_name": "RBC", "value": 4.5, "unit": "10^12/L"},
        ]
        blocks = classifier.classify_page("page", rows)
        assert len(blocks) == 2
        assert blocks[0].section_type == SectionType.HPLC_DIABETES_BLOCK
        assert blocks[1].section_type == SectionType.STANDARD_LAB_TABLE

    def test_three_block_page(self, classifier):
        """Standard → HPLC → standard → 3 blocks."""
        rows = [
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L"},
            {"test_name": "RBC", "value": 4.5, "unit": "10^12/L"},
            # HPLC block
            {"test_name": "HbA1c (NGSP)", "value": 6.0, "unit": "%"},
            {"test_name": "HbA1c (IFCC)", "value": 42, "unit": "mmol/mol"},
            {"test_name": "eAG", "value": 126, "unit": "mg/dL"},
            # Back to standard
            {"test_name": "Creatinine", "value": 0.9, "unit": "mg/dL"},
            {"test_name": "BUN", "value": 15, "unit": "mg/dL"},
        ]
        blocks = classifier.classify_page("page", rows)
        assert len(blocks) == 3
        assert blocks[0].section_type == SectionType.STANDARD_LAB_TABLE
        assert blocks[1].section_type == SectionType.HPLC_DIABETES_BLOCK
        assert blocks[2].section_type == SectionType.STANDARD_LAB_TABLE

    def test_hormone_then_standard(self, classifier):
        """Hormone rows followed by standard rows → 2 blocks."""
        rows = [
            {"test_name": "TSH", "value": 2.5, "unit": "mIU/L"},
            {"test_name": "Free T4", "value": 1.2, "unit": "ng/dL"},
            {"test_name": "Free T3", "value": 3.1, "unit": "pg/mL"},
            # Standard rows
            {"test_name": "WBC", "value": 7.2, "unit": "10^9/L"},
            {"test_name": "RBC", "value": 4.5, "unit": "10^12/L"},
        ]
        blocks = classifier.classify_page("page", rows)
        assert len(blocks) == 2
        assert blocks[0].section_type == SectionType.HORMONE_IMMUNOLOGY_BLOCK
        assert blocks[1].section_type == SectionType.STANDARD_LAB_TABLE

    def test_missing_test_name_treated_as_standard(self):
        """Row with no test_name should score as standard."""
        stype, conf, kws = _score_row({"value": 7.2, "unit": "10^9/L"})
        assert stype == SectionType.STANDARD_LAB_TABLE

    def test_empty_raw_text_with_valid_rows(self, classifier):
        """Empty raw_text with valid rows should classify by rows."""
        rows = [
            {"test_name": "TSH", "value": 2.5, "unit": "mIU/L"},
            {"test_name": "Free T4", "value": 1.2, "unit": "ng/dL"},
        ]
        blocks = classifier.classify_page("", rows)
        assert len(blocks) == 1
        assert blocks[0].section_type == SectionType.HORMONE_IMMUNOLOGY_BLOCK
