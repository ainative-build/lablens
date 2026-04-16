"""Tests for ctDNA screening parser: test type detection, keyword fallback, JSON parsing."""

import json

import pytest

from lablens.extraction.screening_parser import (
    detect_test_type,
    extract_from_keywords,
    parse_screening_json,
)
from lablens.models.screening_result import ScreeningResult, ScreeningStatus


# ── Test type detection ──


class TestDetectTestType:
    def test_spot_mas(self):
        assert detect_test_type("SPOT-MAS screening result") == "SPOT-MAS"

    def test_spot_mas_no_dash(self):
        assert detect_test_type("SPOT MAS analysis report") == "SPOT-MAS"

    def test_galleri(self):
        assert detect_test_type("Galleri multi-cancer test") == "Galleri"

    def test_mced(self):
        assert detect_test_type("MCED panel results") == "MCED"

    def test_ctdna(self):
        assert detect_test_type("ctDNA liquid biopsy") == "ctDNA"

    def test_cfdna(self):
        assert detect_test_type("cfDNA analysis") == "cfDNA"

    def test_cell_free_dna(self):
        assert detect_test_type("cell-free DNA screening") == "cfDNA"

    def test_unknown(self):
        assert detect_test_type("Complete Blood Count") == "Unknown"

    def test_from_rows(self):
        rows = [{"test_name": "SPOT-MAS Result", "reference_range_text": None}]
        assert detect_test_type("", rows) == "SPOT-MAS"

    def test_case_insensitive(self):
        assert detect_test_type("spot-mas SCREENING") == "SPOT-MAS"


# ── Keyword fallback extraction ──


class TestExtractFromKeywords:
    def test_not_detected(self):
        result = extract_from_keywords(
            "No signal detected. No abnormality found.", [], "SPOT-MAS"
        )
        assert result.result_status == ScreeningStatus.NOT_DETECTED
        assert result.test_type == "SPOT-MAS"
        assert result.confidence == 0.5

    def test_detected(self):
        result = extract_from_keywords(
            "Signal detected in colorectal region.", [], "Galleri"
        )
        assert result.result_status == ScreeningStatus.DETECTED
        assert result.test_type == "Galleri"

    def test_indeterminate_default(self):
        result = extract_from_keywords(
            "Sample quality insufficient for analysis.", [], "MCED"
        )
        assert result.result_status == ScreeningStatus.INDETERMINATE

    def test_vietnamese_not_detected(self):
        result = extract_from_keywords(
            "Kết quả: không phát hiện tín hiệu bất thường", [], "SPOT-MAS"
        )
        assert result.result_status == ScreeningStatus.NOT_DETECTED

    def test_negative_keyword(self):
        result = extract_from_keywords("Result: Negative", [], "ctDNA")
        assert result.result_status == ScreeningStatus.NOT_DETECTED

    def test_no_abnormality(self):
        result = extract_from_keywords(
            "no abnormality detected in screening", [], "SPOT-MAS"
        )
        assert result.result_status == ScreeningStatus.NOT_DETECTED

    def test_raw_text_truncated(self):
        long_text = "x" * 1000
        result = extract_from_keywords(long_text, [], "Unknown")
        assert len(result.raw_text) <= 500

    def test_rows_included_in_search(self):
        rows = [{"test_name": "Result", "value": "Not Detected"}]
        result = extract_from_keywords("screening report", rows, "SPOT-MAS")
        assert result.result_status == ScreeningStatus.NOT_DETECTED


# ── JSON response parsing ──


class TestParseScreeningJson:
    def test_valid_not_detected(self):
        data = {
            "test_type": "SPOT-MAS",
            "result_status": "not_detected",
            "signal_origin": None,
            "organs_screened": ["Lung", "Liver", "Breast"],
            "limitations": "Sensitivity is 72.4% for stage I cancers.",
            "followup_recommendation": "Continue routine screening.",
            "raw_summary": "No signal detected.",
        }
        result = parse_screening_json(json.dumps(data))
        assert result is not None
        assert result.test_type == "SPOT-MAS"
        assert result.result_status == ScreeningStatus.NOT_DETECTED
        assert result.signal_origin is None
        assert len(result.organs_screened) == 3
        assert result.limitations is not None
        assert result.confidence == 0.85

    def test_valid_detected(self):
        data = {
            "test_type": "Galleri",
            "result_status": "detected",
            "signal_origin": "Colorectal",
            "organs_screened": ["Lung", "Colon", "Ovary"],
            "limitations": None,
            "followup_recommendation": "Refer to oncologist.",
            "raw_summary": "Signal detected — colorectal origin.",
        }
        result = parse_screening_json(json.dumps(data))
        assert result.result_status == ScreeningStatus.DETECTED
        assert result.signal_origin == "Colorectal"

    def test_not_detected_with_space(self):
        """Handle 'not detected' (with space) as alias."""
        data = {"result_status": "not detected"}
        result = parse_screening_json(json.dumps(data))
        assert result is not None
        assert result.result_status == ScreeningStatus.NOT_DETECTED

    def test_markdown_fence_stripped(self):
        data = {"test_type": "MCED", "result_status": "indeterminate"}
        raw = f"```json\n{json.dumps(data)}\n```"
        result = parse_screening_json(raw)
        assert result is not None
        assert result.test_type == "MCED"

    def test_invalid_json_returns_none(self):
        result = parse_screening_json("not json at all")
        assert result is None

    def test_missing_fields_default(self):
        data = {"result_status": "detected"}
        result = parse_screening_json(json.dumps(data))
        assert result is not None
        assert result.test_type == "Unknown"
        assert result.organs_screened == []

    def test_unknown_status_defaults_indeterminate(self):
        data = {"result_status": "ambiguous"}
        result = parse_screening_json(json.dumps(data))
        assert result.result_status == ScreeningStatus.INDETERMINATE


# ── ScreeningResult dataclass ──


class TestScreeningResult:
    def test_default_values(self):
        sr = ScreeningResult(test_type="Test")
        assert sr.result_status == ScreeningStatus.INDETERMINATE
        assert sr.signal_origin is None
        assert sr.organs_screened == []
        assert sr.confidence == 0.0

    def test_screening_status_values(self):
        assert ScreeningStatus.DETECTED.value == "detected"
        assert ScreeningStatus.NOT_DETECTED.value == "not_detected"
        assert ScreeningStatus.INDETERMINATE.value == "indeterminate"
