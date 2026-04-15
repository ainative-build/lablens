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
        assert report.values[0].range_source == "ocr-flag-fallback"

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


# ── Bug 1: Direction guard — in-range must be normal ──


class TestDirectionGuard:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_in_range_always_normal_severity(self, engine):
        """Even with curated severity bands, in-range → normal."""
        values = [{
            "test_name": "Albumin", "value": 4.0, "unit": "g/dL",
            "loinc_code": "1751-7", "ref_range_low": 3.5, "ref_range_high": 5.0,
        }]
        report = engine.interpret_report(values, {0: "high"})
        assert report.values[0].direction == "in-range"
        assert report.values[0].severity == "normal"
        assert report.values[0].actionability == "routine"

    def test_in_range_never_escalates(self, engine):
        """In-range value with mismatched-unit severity bands must stay normal."""
        # Simulates: value=2.26 mmol/L (in-range per lab [2.25-2.55])
        # but curated bands in mg/dL would flag this as critical
        values = [{
            "test_name": "Total Bilirubin", "value": 0.5, "unit": "mg/dL",
            "loinc_code": "1975-2", "ref_range_low": 0.1, "ref_range_high": 1.2,
        }]
        report = engine.interpret_report(values, {0: "high"})
        assert report.values[0].direction == "in-range"
        assert report.values[0].severity == "normal"
        assert report.values[0].actionability == "routine"


# ── Bug 2: Threshold-style range detection ──


class TestThresholdRangeDetection:
    def test_desirable_threshold_cleared(self):
        v = {
            "test_name": "Triglycerides",
            "value": 0.93,
            "reference_range_low": 1.7,
            "reference_range_high": 2.25,
            "reference_range_text": "Desirable: < 1.7",
        }
        result = _validate_range_plausibility(v)
        assert result["reference_range_low"] is None
        assert result["reference_range_high"] is None

    def test_borderline_threshold_cleared(self):
        v = {
            "test_name": "Total Cholesterol",
            "value": 4.47,
            "reference_range_low": 5.18,
            "reference_range_high": 6.21,
            "reference_range_text": "Borderline High: 5.18-6.21",
        }
        result = _validate_range_plausibility(v)
        assert result["reference_range_low"] is None

    def test_normal_range_text_kept(self):
        v = {
            "test_name": "WBC",
            "value": 7.5,
            "reference_range_low": 4.0,
            "reference_range_high": 11.0,
            "reference_range_text": "4.0 - 11.0",
        }
        result = _validate_range_plausibility(v)
        assert result["reference_range_low"] == 4.0
        assert result["reference_range_high"] == 11.0


# ─�� Bug 4: Direction from reference text ──


class TestDirectionFromText:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_upper_bound_high(self, engine):
        """CA 19-9=42 with ref '≤ 39' → high."""
        values = [{
            "test_name": "CA 19-9", "value": 42.0, "unit": "U/mL",
            "loinc_code": None, "reference_range_text": "≤ 39",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "high"
        assert report.values[0].range_source == "range-text"

    def test_upper_bound_in_range(self, engine):
        """CRP=1.11 with ref '< 5' → in-range."""
        values = [{
            "test_name": "CRP", "value": 1.11, "unit": "mg/L",
            "loinc_code": None, "reference_range_text": "< 5",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "in-range"

    def test_lower_bound(self, engine):
        """Value below lower threshold → low."""
        values = [{
            "test_name": "HDL", "value": 0.8, "unit": "mmol/L",
            "loinc_code": None, "reference_range_text": "> 1.0",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "low"


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


# ── Fix A: Curated range cross-validation ──


class TestCuratedCrossValidation:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_ocr_row_swap_corrected_by_curated(self, engine):
        """MCHC=33.3 with OCR range [11.6-14.0] but curated [32-36] → prefer curated."""
        values = [{
            "test_name": "MCHC", "value": 33.3, "unit": "g/dL",
            "loinc_code": "786-4",
            "ref_range_low": 11.6, "ref_range_high": 14.0,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "in-range"
        assert report.values[0].range_source == "curated-fallback"
        assert report.values[0].severity == "normal"

    def test_valid_lab_range_not_overridden(self, engine):
        """Lab range agrees with curated → keep lab-provided."""
        values = [{
            "test_name": "MCHC", "value": 30.0, "unit": "g/dL",
            "loinc_code": "786-4",
            "ref_range_low": 32.0, "ref_range_high": 36.0,
        }]
        report = engine.interpret_report(values)
        # Lab says low, curated also says low → lab-provided kept
        assert report.values[0].direction == "low"
        assert report.values[0].range_source == "lab-provided-validated"

    def test_both_agree_abnormal_keeps_lab(self, engine):
        """Value abnormal per both lab and curated → lab-provided retained."""
        values = [{
            "test_name": "MCHC", "value": 28.0, "unit": "g/dL",
            "loinc_code": "786-4",
            "ref_range_low": 32.0, "ref_range_high": 36.0,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "low"
        assert report.values[0].range_source == "lab-provided-validated"


# ── Fix B+C: Empty unit guards ──


class TestEmptyUnitGuards:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_no_unit_no_range_ignores_ocr_flag(self, engine):
        """Testosterone=642.56 with no unit, no range, flag=H → indeterminate."""
        values = [{
            "test_name": "Testosterone", "value": 642.56, "unit": "",
            "loinc_code": None, "flag": "H",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "indeterminate"

    def test_unit_present_still_uses_flag(self, engine):
        """With unit present, OCR flag is still used."""
        values = [{
            "test_name": "Testosterone", "value": 642.56, "unit": "ng/dL",
            "loinc_code": None, "flag": "H",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "high"
        assert report.values[0].range_source == "ocr-flag-fallback"

    def test_low_unit_confidence_blocks_curated_fallback(self, engine):
        """unit_confidence=low with curated fallback → don't trust curated range."""
        values = [{
            "test_name": "HDL Cholesterol", "value": 0.92, "unit": "mg/dL",
            "loinc_code": "2085-9", "unit_confidence": "low",
        }]
        report = engine.interpret_report(values)
        # Should NOT get critical severity from curated [40-999]
        assert report.values[0].direction == "indeterminate"
        assert report.values[0].severity != "critical"

    def test_empty_unit_blocks_curated_fallback(self, engine):
        """Free T4=13.59 with empty unit → don't trust curated [0.8-1.8] ng/dL."""
        values = [{
            "test_name": "Free T4", "value": 13.59, "unit": "",
            "loinc_code": "3024-7",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "indeterminate"
        assert report.values[0].severity != "critical"


# ── Fix D: Unit misreport detection ──


class TestUnitMisreportDetection:
    def test_implausibly_low_value_flags_low_confidence(self):
        """HDL-C=0.92 'mg/dL' is implausible for curated [40-999] mg/dL."""
        from lablens.extraction.unit_normalizer import UnitNormalizer
        from lablens.orchestration.pipeline import PlainPipeline

        normalizer = UnitNormalizer()
        vdict = {
            "test_name": "HDL Cholesterol",
            "value": 0.92,
            "unit": "mg/dL",
            "unit_confidence": "high",
        }
        result = PlainPipeline._check_unit_misreport(vdict, "2085-9", normalizer)
        assert result["unit_confidence"] == "low"

    def test_plausible_value_keeps_high_confidence(self):
        """HDL-C=45 mg/dL is plausible for curated [40-999] → keep high confidence."""
        from lablens.extraction.unit_normalizer import UnitNormalizer
        from lablens.orchestration.pipeline import PlainPipeline

        normalizer = UnitNormalizer()
        vdict = {
            "test_name": "HDL Cholesterol",
            "value": 45.0,
            "unit": "mg/dL",
            "unit_confidence": "high",
        }
        result = PlainPipeline._check_unit_misreport(vdict, "2085-9", normalizer)
        assert result["unit_confidence"] == "high"

    def test_no_loinc_code_passthrough(self):
        """No LOINC code → no misreport check."""
        from lablens.extraction.unit_normalizer import UnitNormalizer
        from lablens.orchestration.pipeline import PlainPipeline

        normalizer = UnitNormalizer()
        vdict = {
            "test_name": "Unknown", "value": 0.5, "unit": "mg/dL",
            "unit_confidence": "high",
        }
        result = PlainPipeline._check_unit_misreport(vdict, None, normalizer)
        assert result["unit_confidence"] == "high"


# ── Round 4: Range trust + plausibility ──


class TestRangeTrust:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_low_trust_unit_mismatch_degrades_to_indeterminate(self, engine):
        """Low-trust lab range with unit mismatch → indeterminate, not curated override."""
        values = [{
            "test_name": "Calcium", "value": 2.26, "unit": "mmol/L",
            "loinc_code": "17861-6",
            "ref_range_low": 0.81, "ref_range_high": 1.45,
            "range_trust": "low",
        }]
        report = engine.interpret_report(values)
        # Curated is mg/dL, value is mmol/L — can't reconcile, degrade
        assert report.values[0].direction == "indeterminate"
        assert report.values[0].range_source == "no-range"
        assert report.values[0].severity == "normal"
        assert report.values[0].confidence == "low"

    def test_low_trust_unit_compatible_uses_curated(self, engine):
        """Low-trust lab range with matching unit → use curated fallback."""
        values = [{
            "test_name": "Glucose", "value": 90, "unit": "mg/dL",
            "loinc_code": "2345-7",
            "ref_range_low": 5.0, "ref_range_high": 10.0,
            "range_trust": "low",
        }]
        report = engine.interpret_report(values)
        # Curated is mg/dL, value is mg/dL — compatible, use curated [70-100]
        assert report.values[0].range_source == "curated-fallback"
        assert report.values[0].direction == "in-range"

    def test_low_trust_caps_severity_when_no_curated(self, engine):
        """Low-trust lab range without curated → keep but cap severity at mild."""
        values = [{
            "test_name": "Unknown Test", "value": 50.0, "unit": "mg/dL",
            "loinc_code": None,
            "ref_range_low": 10.0, "ref_range_high": 20.0,
            "range_trust": "low",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].severity in ("mild", "normal")
        assert report.values[0].range_source == "lab-provided-suspicious"

    def test_high_trust_range_allows_moderate(self, engine):
        """High-trust lab range allows normal severity escalation."""
        values = [{
            "test_name": "WBC", "value": 15.0, "unit": "K/uL",
            "loinc_code": None,
            "ref_range_low": 4.0, "ref_range_high": 11.0,
            "range_trust": "high",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].severity == "moderate"


class TestExpandedRangeSource:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_lab_provided_validated(self, engine):
        """Normal lab range → lab-provided-validated."""
        values = [{
            "test_name": "Glucose", "value": 90, "unit": "mg/dL",
            "loinc_code": "2345-7",
            "ref_range_low": 70, "ref_range_high": 100,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].range_source == "lab-provided-validated"

    def test_lab_provided_suspicious_no_curated(self, engine):
        """Low-trust lab range without curated → lab-provided-suspicious."""
        values = [{
            "test_name": "Unknown Test", "value": 50.0, "unit": "mg/dL",
            "loinc_code": None,
            "ref_range_low": 10.0, "ref_range_high": 20.0,
            "range_trust": "low",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].range_source == "lab-provided-suspicious"

    def test_ocr_flag_fallback_source(self, engine):
        """OCR flag → ocr-flag-fallback."""
        values = [{
            "test_name": "Unknown Test", "value": 7.5, "unit": "mg/dL",
            "loinc_code": None, "flag": "H",
        }]
        report = engine.interpret_report(values)
        assert report.values[0].range_source == "ocr-flag-fallback"

    def test_no_range_source(self, engine):
        """No range, no flag → no-range."""
        values = [{
            "test_name": "Unknown", "value": 42, "unit": "",
            "loinc_code": None,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].range_source == "no-range"


class TestCategoryGating:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_hormone_flag_produces_indeterminate(self, engine):
        """Testosterone with flag=H but restricted category → indeterminate."""
        values = [{
            "test_name": "Testosterone", "value": 642.56, "unit": "ng/dL",
            "loinc_code": "2986-8", "flag": "H",
            "restricted_flag": True,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "indeterminate"

    def test_non_restricted_flag_still_works(self, engine):
        """Non-restricted test with flag=H → high direction."""
        values = [{
            "test_name": "WBC", "value": 15.0, "unit": "K/uL",
            "loinc_code": None, "flag": "H",
            "restricted_flag": False,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].direction == "high"


class TestSeverityCap:
    @pytest.fixture
    def engine(self):
        return InterpretationEngine()

    def test_never_critical_without_curated(self, engine):
        """Heuristic severity cannot reach critical — capped at moderate."""
        values = [{
            "test_name": "Unknown", "value": 100.0, "unit": "mg/dL",
            "loinc_code": None,
            "ref_range_low": 5.0, "ref_range_high": 10.0,
        }]
        report = engine.interpret_report(values)
        assert report.values[0].severity != "critical"
        assert report.values[0].severity == "moderate"


class TestPlausibilityChecker:
    def test_checker_loads(self):
        from lablens.extraction.range_plausibility_checker import (
            RangePlausibilityChecker,
        )
        checker = RangePlausibilityChecker()
        assert checker.get_category("2085-9") == "lipid"
        assert checker.get_category("2986-8") == "hormone"
        assert checker.is_restricted_flag_category("2986-8") is True
        assert checker.is_restricted_flag_category("6690-2") is False
        assert checker.is_decision_threshold("2093-3") is True
        assert checker.is_decision_threshold("6690-2") is False

    def test_plausible_range_returns_high(self):
        from lablens.extraction.range_plausibility_checker import (
            RangePlausibilityChecker,
        )
        checker = RangePlausibilityChecker()
        trust = checker.validate_range("718-7", 14.0, 12.0, 17.0, "g/dL")
        assert trust == "high"

    def test_implausible_range_returns_low(self):
        from lablens.extraction.range_plausibility_checker import (
            RangePlausibilityChecker,
        )
        checker = RangePlausibilityChecker()
        # Platelet value=163 with range [9-12] (from adjacent MPV row)
        # range midpoint=10.5, platelet family ref midpoint is ~325
        # ratio = 10.5/325 = 0.032 → well outside [0.2, 5.0]
        trust = checker.validate_range("777-3", 163.0, 9.0, 12.0, "K/uL")
        assert trust == "low"

    def test_curated_crosscheck_detects_unit_mismatch(self):
        """Lab range in mmol/L vs curated in mg/dL → >5x midpoint diff → low trust."""
        from lablens.extraction.range_plausibility_checker import (
            RangePlausibilityChecker,
        )
        checker = RangePlausibilityChecker()
        # Calcium: lab range [0.81-1.45] mmol/L, curated [8.5-10.5] mg/dL
        trust = checker.validate_range(
            "17861-6", 2.26, 0.81, 1.45, "mmol/L",
            curated_ref_low=8.5, curated_ref_high=10.5,
        )
        assert trust == "low"

    def test_curated_crosscheck_passes_same_scale(self):
        """Lab range same scale as curated → not flagged."""
        from lablens.extraction.range_plausibility_checker import (
            RangePlausibilityChecker,
        )
        checker = RangePlausibilityChecker()
        # Glucose: lab [70-100], curated [70-100] — same scale
        trust = checker.validate_range(
            "2345-7", 90.0, 70.0, 100.0, "mg/dL",
            curated_ref_low=70.0, curated_ref_high=100.0,
        )
        assert trust == "high"
