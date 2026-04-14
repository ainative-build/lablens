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
