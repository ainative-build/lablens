"""Integration tests for the extraction → interpretation pipeline.

Covers the hottest failure paths: OCR range parsing, range plausibility,
terminology normalization, OCR flag fallback, qualitative interpretation,
heuristic severity, and noise filtering.
"""

import pytest

from lablens.extraction.ocr_extractor import (
    _fix_range_fields,
    _validate_range_plausibility,
)
from lablens.extraction.response_parser import filter_noise_values
from lablens.extraction.terminology_mapper import TerminologyMapper, normalize_test_name
from lablens.interpretation.engine import InterpretationEngine
from lablens.models.lab_report import LabValue


# ── OCR range field fixing ──


class TestFixRangeFields:
    def test_simple_range_string(self):
        v = {"reference_range_low": "3.2 - 7.4", "reference_range_high": None}
        result = _fix_range_fields(v)
        assert result["reference_range_low"] == 3.2
        assert result["reference_range_high"] == 7.4

    def test_upper_bound_only(self):
        v = {"reference_range_low": "< 200", "reference_range_high": None}
        result = _fix_range_fields(v)
        assert result["reference_range_low"] is None
        assert result["reference_range_high"] == 200.0

    def test_lower_bound_only(self):
        v = {"reference_range_low": "> 60", "reference_range_high": None}
        result = _fix_range_fields(v)
        assert result["reference_range_low"] == 60.0
        assert result["reference_range_high"] is None

    def test_embedded_range_in_text(self):
        v = {"reference_range_low": "Normal: 3.2 - 7.4", "reference_range_high": None}
        result = _fix_range_fields(v)
        assert result["reference_range_low"] == 3.2
        assert result["reference_range_high"] == 7.4
        assert result["reference_range_text"] == "Normal: 3.2 - 7.4"

    def test_numeric_passthrough(self):
        v = {"reference_range_low": 4.0, "reference_range_high": 10.0}
        result = _fix_range_fields(v)
        assert result["reference_range_low"] == 4.0
        assert result["reference_range_high"] == 10.0

    def test_unparseable_saved_as_text(self):
        v = {"reference_range_low": "See footnote", "reference_range_high": None}
        result = _fix_range_fields(v)
        assert result["reference_range_low"] is None
        assert result["reference_range_text"] == "See footnote"


# ── Range plausibility validation ──


class TestRangePlausibility:
    def test_row_swap_detected(self):
        """Platelets=163 with range 9-12 (from adjacent MPV row)."""
        v = {
            "test_name": "Platelets",
            "value": 163,
            "reference_range_low": 9.04,
            "reference_range_high": 12.79,
        }
        result = _validate_range_plausibility(v)
        assert result["reference_range_low"] is None
        assert result["reference_range_high"] is None

    def test_valid_range_kept(self):
        v = {
            "test_name": "Platelets",
            "value": 163,
            "reference_range_low": 150,
            "reference_range_high": 400,
        }
        result = _validate_range_plausibility(v)
        assert result["reference_range_low"] == 150
        assert result["reference_range_high"] == 400

    def test_inverted_range_cleared(self):
        v = {
            "test_name": "WBC",
            "value": 7.5,
            "reference_range_low": 11.0,
            "reference_range_high": 4.0,
        }
        result = _validate_range_plausibility(v)
        assert result["reference_range_low"] is None
        assert result["reference_range_high"] is None


# ── Terminology normalization ──


class TestTerminologyNormalization:
    def test_strip_specimen_brackets(self):
        assert normalize_test_name("Testosterone [Serum]") == "testosterone"

    def test_strip_plasma_parens(self):
        assert normalize_test_name("Glucose (Plasma)") == "glucose"

    def test_abbreviation_expansion(self):
        assert normalize_test_name("Gamma GT") == "ggt"
        assert normalize_test_name("HbA1c") == "hba1c"
        assert normalize_test_name("HDL-C") == "hdl cholesterol"

    def test_trailing_junk_removed(self):
        assert normalize_test_name("Hemoglobin *") == "hemoglobin"

    def test_paren_abbrev_removed(self):
        assert normalize_test_name("ALT (GPT)") == "alt"


class TestTerminologyMapperMatch:
    @pytest.fixture
    def mapper(self):
        return TerminologyMapper()

    def test_exact_match(self, mapper):
        code, conf = mapper.match("glucose")
        assert code is not None
        assert conf in ("high", "medium")

    def test_normalized_match(self, mapper):
        code, conf = mapper.match("Hemoglobin [Whole blood]")
        assert code is not None

    def test_abbreviation_match(self, mapper):
        code, conf = mapper.match("HbA1c")
        assert code is not None


# ── Engine: OCR flag fallback ──


class TestOCRFlagFallback:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_flag_high_when_no_range(self, engine):
        values = [{
            "test_name": "Testosterone", "value": 642.56, "unit": "ng/dL",
            "loinc_code": None, "flag": "H",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "high"
        assert report.values[0].range_source == "ocr-flag"

    def test_flag_low_when_no_range(self, engine):
        values = [{
            "test_name": "Unknown Test", "value": 1.2, "unit": "mg/dL",
            "loinc_code": None, "flag": "L",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "low"

    def test_no_flag_stays_indeterminate(self, engine):
        values = [{
            "test_name": "Unknown Test", "value": 42, "unit": "mg/dL",
            "loinc_code": None,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "indeterminate"


# ── Engine: qualitative interpretation ──


class TestQualitativeInterpretation:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_negative_is_in_range(self, engine):
        values = [{
            "test_name": "HBsAg", "value": "Negative", "unit": None,
            "loinc_code": "5196-1",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "in-range"

    def test_positive_is_high(self, engine):
        values = [{
            "test_name": "HBsAg", "value": "Positive", "unit": None,
            "loinc_code": "5196-1",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "high"

    def test_semi_quantitative_plus(self, engine):
        values = [{
            "test_name": "Urobilinogen", "value": "++", "unit": None,
            "loinc_code": None,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "high"


# ── Engine: heuristic severity ──


class TestHeuristicSeverity:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_mild_deviation(self, engine):
        """Value just outside range (≤10% deviation) → mild severity."""
        values = [{
            "test_name": "Unknown Analyte", "value": 10.4, "unit": "mg/dL",
            "loinc_code": None, "ref_range_low": 5.0, "ref_range_high": 10.0,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "high"
        assert report.values[0].severity == "mild"

    def test_moderate_deviation(self, engine):
        """Value well outside range → moderate severity."""
        values = [{
            "test_name": "Unknown Analyte", "value": 15.0, "unit": "mg/dL",
            "loinc_code": None, "ref_range_low": 5.0, "ref_range_high": 10.0,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "high"
        assert report.values[0].severity == "moderate"

    def test_in_range_stays_normal(self, engine):
        """In-range value → normal severity regardless of missing rule."""
        values = [{
            "test_name": "Unknown Analyte", "value": 7.0, "unit": "mg/dL",
            "loinc_code": None, "ref_range_low": 5.0, "ref_range_high": 10.0,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].severity == "normal"


# ── Noise filtering ──


class TestNoiseFiltering:
    def test_methodology_text_filtered(self):
        values = [
            LabValue(test_name="WBC", value=7.5, unit="K/uL"),
            LabValue(
                test_name="Phương pháp xét nghiệm: Đo quang phổ hấp thụ",
                value="methodology",
                unit=None,
            ),
        ]
        filtered = filter_noise_values(values)
        assert len(filtered) == 1
        assert filtered[0].test_name == "WBC"

    def test_valid_values_kept(self):
        values = [
            LabValue(test_name="Glucose", value=90, unit="mg/dL"),
            LabValue(test_name="Hemoglobin", value=14.0, unit="g/dL"),
        ]
        filtered = filter_noise_values(values)
        assert len(filtered) == 2


# ── Explanation fallback ──


class TestExplanationFallback:
    def test_parse_explanations_returns_empty_on_bad_json(self):
        from lablens.retrieval.explanation_generator import ExplanationGenerator

        result = ExplanationGenerator._parse_explanations("not json at all", "en")
        assert result == []

    def test_parse_explanations_handles_markdown_fence(self):
        from lablens.retrieval.explanation_generator import ExplanationGenerator

        raw = '```json\n[{"test_name":"WBC","summary":"ok","what_it_means":"","next_steps":""}]\n```'
        result = ExplanationGenerator._parse_explanations(raw, "en")
        assert len(result) == 1
        assert result[0].test_name == "WBC"


# ── PDF validation ──


class TestPDFValidation:
    def test_rejects_non_pdf(self):
        from lablens.extraction.pdf_processor import PDFProcessor

        with pytest.raises(ValueError, match="not a valid PDF"):
            PDFProcessor.validate_pdf(b"not a pdf")

    def test_rejects_oversized(self):
        from lablens.extraction.pdf_processor import PDFProcessor

        # 25 MB of fake PDF
        fake = b"%PDF-" + b"\x00" * (25 * 1024 * 1024)
        with pytest.raises(ValueError, match="too large"):
            PDFProcessor.validate_pdf(fake)
