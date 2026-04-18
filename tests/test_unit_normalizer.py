"""Tests for unit normalizer — conversion and alias resolution."""

import pytest

from lablens.extraction.unit_normalizer import UnitNormalizer


@pytest.fixture
def normalizer():
    return UnitNormalizer()


def test_no_conversion_needed(normalizer):
    result = normalizer.normalize("2345-7", 100.0, "mg/dL")
    assert result.value == 100.0
    assert result.unit == "mg/dL"
    assert result.converted is False
    assert result.confidence == "high"


def test_mmol_to_mgdl_glucose(normalizer):
    result = normalizer.normalize("2345-7", 5.5, "mmol/L")
    assert result.converted is True
    assert result.unit == "mg/dL"
    assert abs(result.value - 99.1) < 0.5  # 5.5 * 18.0182 ≈ 99.1
    assert result.original_value == 5.5
    assert result.original_unit == "mmol/L"


def test_umol_to_mgdl_creatinine(normalizer):
    result = normalizer.normalize("2160-0", 88.4, "µmol/L")
    assert result.converted is True
    assert result.unit == "mg/dL"
    assert abs(result.value - 1.0) < 0.1  # 88.4 * 0.0113 ≈ 1.0


def test_gl_to_gdl_hemoglobin(normalizer):
    result = normalizer.normalize("718-7", 140.0, "g/L")
    assert result.converted is True
    assert result.unit == "g/dL"
    assert abs(result.value - 14.0) < 0.1


def test_mmol_to_mgdl_cholesterol(normalizer):
    result = normalizer.normalize("2093-3", 5.2, "mmol/L")
    assert result.converted is True
    assert abs(result.value - 201.1) < 1.0  # 5.2 * 38.67


def test_unit_alias_iul(normalizer):
    normalized = normalizer.normalize_unit("IU/L")
    assert normalized == "U/L"


def test_unit_alias_case(normalizer):
    normalized = normalizer.normalize_unit("mg/dl")
    assert normalized == "mg/dL"


def test_unit_alias_meql(normalizer):
    normalized = normalizer.normalize_unit("mEq/L")
    assert normalized == "mmol/L"


def test_unknown_unit_low_confidence(normalizer):
    result = normalizer.normalize("2345-7", 100.0, "weird_unit")
    assert result.confidence == "low"
    assert result.converted is False


def test_unknown_loinc_passthrough(normalizer):
    result = normalizer.normalize("99999-9", 42.0, "mg/dL")
    assert result.value == 42.0
    assert result.confidence == "high"
    assert result.converted is False


def test_french_report_loinc_keyed(normalizer):
    """French report: test name 'Glycémie' resolved to LOINC 2345-7 by mapper.
    Unit normalizer receives LOINC code, not French name."""
    result = normalizer.normalize("2345-7", 5.5, "mmol/L")
    assert result.converted is True
    assert result.unit == "mg/dL"


def test_greek_mu_folds_to_micro_sign_uric_acid(normalizer):
    """Real OCR/LLM output uses U+03BC (Greek mu 'μ') but conversions config
    keys off U+00B5 (micro sign 'µ'). Both must convert identically —
    otherwise LOINC gets cleared downstream and the row drops to
    ocr-flag-fallback. Regression for real PDF upload bug.
    """
    greek_mu = normalizer.normalize("3084-1", 649.6, "\u03bcmol/L")
    micro_sign = normalizer.normalize("3084-1", 649.6, "\u00b5mol/L")
    assert greek_mu.converted is True
    assert greek_mu.confidence == "high"
    assert greek_mu.unit == "mg/dL"
    assert abs(greek_mu.value - 10.92) < 0.01  # 649.6 * 0.01681
    # Both codepoints must produce identical output
    assert greek_mu.value == micro_sign.value
    assert greek_mu.unit == micro_sign.unit


def test_greek_mu_normalize_unit_direct(normalizer):
    """normalize_unit() must fold Greek mu to micro sign before alias lookup."""
    assert normalizer.normalize_unit("\u03bcmol/L") == "\u00b5mol/L"
    assert normalizer.normalize_unit("\u03bcg/dL") == "ug/dL"


def test_superscript_folds_to_ascii_egfr(normalizer):
    """Real OCR/LLM output uses U+00B2 (superscript '²') in units like
    'mL/min/1.73m²', but alias tables and curated rules key off ASCII
    'mL/min/1.73m2'. Without this fold, engine.py's unit-mismatch guard
    wipes curated-fallback → eGFR falls through to OCR-flag-fallback →
    direction gets suppressed → a real CKD-stage-2 finding disappears
    from "main items to discuss". Regression for Vietnamese-report bug.
    """
    assert normalizer.normalize_unit("mL/min/1.73m\u00b2") == "mL/min/1.73m2"
    assert normalizer.normalize_unit("mL/min/1.73 m\u00b2") == "mL/min/1.73m2"
    # Bare superscripts fold too (defensive for other units).
    assert normalizer.normalize_unit("g/m\u00b3") == "g/m3"
