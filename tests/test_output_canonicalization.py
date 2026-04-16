"""Tests for output canonicalization fixes (PR review round).

Covers: explanation quality tracking, screening dedup,
duplicate analyte consolidation, and InterpretedResult field carry-through.
"""

import pytest
from unittest.mock import MagicMock

from lablens.interpretation.models import InterpretedReport, InterpretedResult
from lablens.retrieval.models import ExplanationResult, FinalReport


# --- InterpretedResult new fields ---


class TestInterpretedResultFields:
    def test_has_section_type(self):
        r = InterpretedResult(
            test_name="HbA1c", loinc_code="4548-4", value=5.1, unit="%",
            section_type="hplc_diabetes_block",
        )
        assert r.section_type == "hplc_diabetes_block"

    def test_has_verification_verdict(self):
        r = InterpretedResult(
            test_name="WBC", loinc_code="6690-2", value=7.0, unit="10^9/L",
            verification_verdict="downgraded",
        )
        assert r.verification_verdict == "downgraded"

    def test_has_unit_confidence(self):
        r = InterpretedResult(
            test_name="Glucose", loinc_code="2345-7", value=100, unit="mg/dL",
            unit_confidence="low",
        )
        assert r.unit_confidence == "low"

    def test_has_flag(self):
        r = InterpretedResult(
            test_name="WBC", loinc_code="6690-2", value=12.0, unit="10^9/L",
            flag="H",
        )
        assert r.flag == "H"

    def test_defaults(self):
        r = InterpretedResult(
            test_name="X", loinc_code=None, value=1, unit="",
        )
        assert r.section_type is None
        assert r.verification_verdict == "accepted"
        assert r.unit_confidence == "high"
        assert r.flag is None

    def test_fields_in_vars(self):
        """New fields must appear in vars() for JSON serialization."""
        r = InterpretedResult(
            test_name="X", loinc_code=None, value=1, unit="",
            section_type="standard_lab_table",
            verification_verdict="accepted",
            unit_confidence="medium",
            flag="L",
        )
        d = vars(r)
        assert d["section_type"] == "standard_lab_table"
        assert d["verification_verdict"] == "accepted"
        assert d["unit_confidence"] == "medium"
        assert d["flag"] == "L"


# --- Coverage score ---


class TestCoverageScore:
    def test_no_longer_claims_explained(self):
        """coverage_score should not claim N/N abnormal explained."""
        report = InterpretedReport(
            values=[], panels=[], total_parsed=10, total_abnormal=3,
        )
        assert "explained" not in report.coverage_score
        assert "3 abnormal detected" in report.coverage_score

    def test_zero_abnormal(self):
        report = InterpretedReport(
            values=[], panels=[], total_parsed=5, total_abnormal=0,
        )
        assert "0 abnormal detected" in report.coverage_score


# --- Explanation quality ---


class TestExplanationQuality:
    def test_is_fallback_flag(self):
        e = ExplanationResult(
            test_name="X", summary="", what_it_means="", next_steps="",
            language="en", is_fallback=True,
        )
        assert e.is_fallback is True

    def test_default_not_fallback(self):
        e = ExplanationResult(
            test_name="X", summary="", what_it_means="", next_steps="",
            language="en",
        )
        assert e.is_fallback is False

    def test_final_report_quality_all_real(self):
        explanations = [
            ExplanationResult(
                test_name="A", summary="", what_it_means="", next_steps="",
                language="en", is_fallback=False,
            ),
            ExplanationResult(
                test_name="B", summary="", what_it_means="", next_steps="",
                language="en", is_fallback=False,
            ),
        ]
        report = FinalReport(
            interpreted_values=[], explanations=explanations, panels=[],
            coverage_score="", disclaimer="", language="en",
        )
        q = report.explanation_quality
        assert q["total"] == 2
        assert q["llm_generated"] == 2
        assert q["fallback_used"] == 0

    def test_final_report_quality_mixed(self):
        explanations = [
            ExplanationResult(
                test_name="A", summary="", what_it_means="", next_steps="",
                language="en", is_fallback=False,
            ),
            ExplanationResult(
                test_name="B", summary="", what_it_means="", next_steps="",
                language="en", is_fallback=True,
            ),
            ExplanationResult(
                test_name="C", summary="", what_it_means="", next_steps="",
                language="en", is_fallback=True,
            ),
        ]
        report = FinalReport(
            interpreted_values=[], explanations=explanations, panels=[],
            coverage_score="", disclaimer="", language="en",
        )
        q = report.explanation_quality
        assert q["total"] == 3
        assert q["llm_generated"] == 1
        assert q["fallback_used"] == 2


# --- Duplicate analyte consolidation ---


class TestDedupeAnalytes:
    def _make_result(self, name, unit, confidence="medium",
                     range_source="curated-fallback", loinc=None):
        return InterpretedResult(
            test_name=name, loinc_code=loinc, value=1.0, unit=unit,
            confidence=confidence, range_source=range_source,
        )

    def test_no_dupes_unchanged(self):
        from lablens.orchestration.pipeline import PlainPipeline
        values = [
            self._make_result("WBC", "10^9/L", loinc="6690-2"),
            self._make_result("RBC", "10^12/L", loinc="789-8"),
        ]
        canonical, alternates = PlainPipeline._dedupe_analytes(values)
        assert len(canonical) == 2
        assert len(alternates) == 0

    def test_same_name_different_unit_deduped(self):
        from lablens.orchestration.pipeline import PlainPipeline
        values = [
            self._make_result("Free T4 [Serum]*", "pmol/L",
                              confidence="low", loinc="3024-7",
                              range_source="lab-provided-suspicious"),
            self._make_result("Free T4 [Serum]*", "ng/dL",
                              confidence="medium", loinc="3024-7",
                              range_source="lab-provided-validated"),
        ]
        canonical, alternates = PlainPipeline._dedupe_analytes(values)
        assert len(canonical) == 1
        assert len(alternates) == 1
        # Higher confidence + validated wins
        assert canonical[0].unit == "ng/dL"
        assert alternates[0].unit == "pmol/L"

    def test_micro_symbol_normalized(self):
        from lablens.orchestration.pipeline import PlainPipeline
        values = [
            self._make_result("TSH [Serum]*", "\u03bcIU/mL",
                              confidence="medium", loinc="3016-3",
                              range_source="lab-provided-validated"),
            self._make_result("TSH [Serum]*", "\u00b5IU/mL",
                              confidence="medium", loinc="3016-3",
                              range_source="lab-provided-validated"),
        ]
        canonical, alternates = PlainPipeline._dedupe_analytes(values)
        assert len(canonical) == 1
        assert len(alternates) == 1

    def test_hplc_values_exempt_from_dedup(self):
        """HPLC NGSP/IFCC/eAG must never be deduplicated even with same LOINC."""
        from lablens.orchestration.pipeline import PlainPipeline
        values = [
            InterpretedResult(
                test_name="HbA1c (NGSP)", loinc_code="4548-4", value=5.1,
                unit="%", confidence="high", range_source="hplc-cross-check",
                section_type="hplc_diabetes_block",
            ),
            InterpretedResult(
                test_name="HbA1c (IFCC)", loinc_code="4548-4", value=33.0,
                unit="mmol/mol", confidence="high",
                range_source="hplc-cross-check",
                section_type="hplc_diabetes_block",
            ),
            InterpretedResult(
                test_name="Estimated Average Glucose (eAG)",
                loinc_code="53553-4", value=5.53, unit="mmol/L",
                confidence="high", range_source="hplc-cross-check",
                section_type="hplc_diabetes_block",
            ),
        ]
        canonical, alternates = PlainPipeline._dedupe_analytes(values)
        # ALL 3 HPLC values must survive — no deduplication
        assert len(canonical) == 3
        assert len(alternates) == 0

    def test_different_loinc_not_deduped(self):
        from lablens.orchestration.pipeline import PlainPipeline
        values = [
            self._make_result("Glucose", "mmol/L", loinc="2345-7"),
            self._make_result("Glucose", "mg/dL", loinc="2340-8"),
        ]
        canonical, alternates = PlainPipeline._dedupe_analytes(values)
        # Different LOINC → different analytes
        assert len(canonical) == 2
        assert len(alternates) == 0


# --- Screening dedup ---


class TestScreeningDedup:
    def _make_screening(self, test_type, confidence=0.85,
                        organs=None, limitations=None, followup=None):
        from lablens.models.screening_result import (
            ScreeningResult,
            ScreeningStatus,
        )
        return ScreeningResult(
            test_type=test_type,
            result_status=ScreeningStatus.NOT_DETECTED,
            confidence=confidence,
            organs_screened=organs or [],
            limitations=limitations,
            followup_recommendation=followup,
        )

    def test_single_result_unchanged(self):
        from lablens.extraction.ocr_extractor import OCRExtractor
        results = [self._make_screening("SPOT-MAS")]
        deduped = OCRExtractor._dedupe_screening(results)
        assert len(deduped) == 1

    def test_multiple_same_type_deduped(self):
        from lablens.extraction.ocr_extractor import OCRExtractor
        results = [
            self._make_screening("SPOT-MAS", confidence=0.80,
                                 organs=["Breast", "Lung"]),
            self._make_screening("SPOT-MAS", confidence=0.85,
                                 organs=["Lung", "Liver"]),
            self._make_screening("SPOT-MAS", confidence=0.75,
                                 organs=["Colon"]),
        ]
        deduped = OCRExtractor._dedupe_screening(results)
        assert len(deduped) == 1
        # Highest confidence wins (0.85)
        assert deduped[0].confidence == 0.85
        # Organs merged from all
        assert "Breast" in deduped[0].organs_screened
        assert "Liver" in deduped[0].organs_screened
        assert "Colon" in deduped[0].organs_screened

    def test_different_types_kept(self):
        from lablens.extraction.ocr_extractor import OCRExtractor
        results = [
            self._make_screening("SPOT-MAS"),
            self._make_screening("Galleri"),
        ]
        deduped = OCRExtractor._dedupe_screening(results)
        assert len(deduped) == 2

    def test_longer_text_preserved(self):
        from lablens.extraction.ocr_extractor import OCRExtractor
        results = [
            self._make_screening("SPOT-MAS", confidence=0.90,
                                 limitations="Short"),
            self._make_screening("SPOT-MAS", confidence=0.80,
                                 limitations="This is a much longer limitations text"),
        ]
        deduped = OCRExtractor._dedupe_screening(results)
        assert len(deduped) == 1
        # Winner (0.90) gets longer text from loser
        assert "longer" in deduped[0].limitations

    def test_empty_list(self):
        from lablens.extraction.ocr_extractor import OCRExtractor
        assert OCRExtractor._dedupe_screening([]) == []
