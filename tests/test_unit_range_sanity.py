"""Tests for unit/range sanity enforcement.

Covers: expanded unit bounds, expanded LOINC bounds, range edge cases,
case-insensitive unit aliases, post-conversion plausibility guard,
cross-unit mismatch detection.
"""

from lablens.extraction.semantic_verifier import check_unit_value_plausibility
from lablens.extraction.plausibility_validator import (
    HUMAN_POSSIBLE_BOUNDS,
    check_value_plausibility,
)
from lablens.extraction.ocr_range_preprocessor import (
    fix_range_fields,
    validate_range_plausibility,
)
from lablens.extraction.unit_normalizer import UnitNormalizer


# ── Expanded unit bounds (_UNIT_BOUNDS) ──


class TestExpandedUnitBounds:
    """Verify new units added to _UNIT_BOUNDS in semantic verifier."""

    def test_k_ul_in_range(self):
        assert check_unit_value_plausibility(6.5, "K/uL") is True

    def test_k_ul_extreme(self):
        assert check_unit_value_plausibility(99999.0, "K/uL") is False

    def test_miu_l_in_range(self):
        """TSH=2.5 mIU/L is normal."""
        assert check_unit_value_plausibility(2.5, "mIU/L") is True

    def test_miu_l_extreme(self):
        """TSH=5000 mIU/L is impossible."""
        assert check_unit_value_plausibility(5000.0, "mIU/L") is False

    def test_ng_ml_in_range(self):
        """Vitamin D=35 ng/mL is normal."""
        assert check_unit_value_plausibility(35.0, "ng/mL") is True

    def test_ng_ml_extreme(self):
        """ng/mL=999999 is OCR garble."""
        assert check_unit_value_plausibility(999999.0, "ng/mL") is False

    def test_pmol_l_in_range(self):
        """Free T4=15 pmol/L is normal."""
        assert check_unit_value_plausibility(15.0, "pmol/L") is True

    def test_pmol_l_extreme(self):
        """pmol/L=1000 is impossible for any thyroid hormone."""
        assert check_unit_value_plausibility(1000.0, "pmol/L") is False

    def test_mm_hr_in_range(self):
        """ESR=25 mm/hr is normal."""
        assert check_unit_value_plausibility(25.0, "mm/hr") is True

    def test_mm_hr_extreme(self):
        """ESR=500 mm/hr is impossible."""
        assert check_unit_value_plausibility(500.0, "mm/hr") is False

    def test_ng_dl_in_range(self):
        """Testosterone=500 ng/dL is normal."""
        assert check_unit_value_plausibility(500.0, "ng/dL") is True

    def test_mg_l_in_range(self):
        """CRP=5.0 mg/L is mildly elevated."""
        assert check_unit_value_plausibility(5.0, "mg/L") is True

    def test_meq_l_in_range(self):
        assert check_unit_value_plausibility(140.0, "mEq/L") is True

    def test_unknown_unit_still_passes(self):
        """Unknown units pass by default (no false rejections)."""
        assert check_unit_value_plausibility(999.0, "widgets/mL") is True


# ── Expanded LOINC bounds (HUMAN_POSSIBLE_BOUNDS) ──


class TestExpandedLoincBounds:
    """Verify new LOINC entries in HUMAN_POSSIBLE_BOUNDS."""

    def test_alt_in_bounds(self):
        assert "1742-6" in HUMAN_POSSIBLE_BOUNDS
        lo, hi = HUMAN_POSSIBLE_BOUNDS["1742-6"]
        assert lo <= 45.0 <= hi

    def test_alt_extreme_flagged(self):
        """ALT=99999 should trigger plausibility warning."""
        from lablens.models.lab_report import LabValue
        v = LabValue(test_name="ALT", value=99999.0, unit="U/L", loinc_code="1742-6")
        warnings = check_value_plausibility(v)
        assert len(warnings) >= 1

    def test_egfr_in_bounds(self):
        assert "33914-3" in HUMAN_POSSIBLE_BOUNDS
        lo, hi = HUMAN_POSSIBLE_BOUNDS["33914-3"]
        assert lo <= 90.0 <= hi

    def test_egfr_extreme_flagged(self):
        from lablens.models.lab_report import LabValue
        v = LabValue(test_name="eGFR", value=500.0, unit="mL/min/1.73m2", loinc_code="33914-3")
        warnings = check_value_plausibility(v)
        assert len(warnings) >= 1

    def test_vitamin_d_in_bounds(self):
        assert "1989-3" in HUMAN_POSSIBLE_BOUNDS
        lo, hi = HUMAN_POSSIBLE_BOUNDS["1989-3"]
        assert lo <= 35.0 <= hi

    def test_vitamin_d_extreme_flagged(self):
        from lablens.models.lab_report import LabValue
        v = LabValue(test_name="Vitamin D", value=9999.0, unit="ng/mL", loinc_code="1989-3")
        warnings = check_value_plausibility(v)
        assert len(warnings) >= 1

    def test_hba1c_in_bounds(self):
        assert "4548-4" in HUMAN_POSSIBLE_BOUNDS
        lo, hi = HUMAN_POSSIBLE_BOUNDS["4548-4"]
        assert lo <= 5.7 <= hi

    def test_uric_acid_in_bounds(self):
        assert "3084-1" in HUMAN_POSSIBLE_BOUNDS
        lo, hi = HUMAN_POSSIBLE_BOUNDS["3084-1"]
        assert lo <= 6.0 <= hi

    def test_calcium_tight_bound(self):
        """Calcium has tighter bound than generic mg/dL."""
        lo, hi = HUMAN_POSSIBLE_BOUNDS["17861-6"]
        assert hi <= 30.0  # Much tighter than mg/dL ceiling of 10000

    def test_crp_in_bounds(self):
        assert "1988-5" in HUMAN_POSSIBLE_BOUNDS


# ── Range edge cases ──


class TestRangeEdgeCases:
    """Verify range parsing and validation edge cases."""

    def test_zero_width_range_cleared(self):
        """[0, 0] should be cleared as zero-width."""
        v = {"test_name": "X", "value": 5.0,
             "reference_range_low": 0, "reference_range_high": 0}
        validate_range_plausibility(v)
        assert v["reference_range_low"] is None
        assert v["reference_range_high"] is None

    def test_nonzero_zero_width_cleared(self):
        """[5, 5] should be cleared as zero-width."""
        v = {"test_name": "X", "value": 5.0,
             "reference_range_low": 5, "reference_range_high": 5}
        validate_range_plausibility(v)
        assert v["reference_range_low"] is None
        assert v["reference_range_high"] is None

    def test_string_zero_width_cleared(self):
        """String [0, 0] should be coerced and cleared."""
        v = {"test_name": "X", "value": 5.0,
             "reference_range_low": "0", "reference_range_high": "0"}
        validate_range_plausibility(v)
        assert v["reference_range_low"] is None
        assert v["reference_range_high"] is None

    def test_inverted_range_still_cleared(self):
        """[10, 5] should be cleared."""
        v = {"test_name": "X", "value": 7.0,
             "reference_range_low": 10, "reference_range_high": 5}
        validate_range_plausibility(v)
        assert v["reference_range_low"] is None
        assert v["reference_range_high"] is None

    def test_valid_range_preserved(self):
        """Normal range [3.5, 5.0] should be kept."""
        v = {"test_name": "Glucose", "value": 4.5,
             "reference_range_low": 3.5, "reference_range_high": 5.0}
        validate_range_plausibility(v)
        assert v["reference_range_low"] == 3.5
        assert v["reference_range_high"] == 5.0


# ── Comma-decimal parsing ──


class TestCommaDecimalParsing:
    """Verify comma-as-decimal-separator support."""

    def test_comma_range_parsed(self):
        """'3,2 - 7,4' should parse as [3.2, 7.4]."""
        v = {"reference_range_low": "3,2 - 7,4", "reference_range_high": None}
        fix_range_fields(v)
        assert v["reference_range_low"] == 3.2
        assert v["reference_range_high"] == 7.4

    def test_pure_numeric_with_comma_decimal_parsed(self):
        """European labs emit bounds as pure numeric fields with comma decimals
        (French TSH range_low='0,3500', range_high='4,9400'). These must be
        coerced to floats even when multiple digits follow the comma — lab
        values don't use comma as a thousands separator in practice, so any
        isolated comma in a whole-number-only string is a decimal."""
        v = {
            "reference_range_low": "0,3500",
            "reference_range_high": "4,9400",
        }
        fix_range_fields(v)
        assert v["reference_range_low"] == 0.35
        assert v["reference_range_high"] == 4.94

    def test_value_with_european_comma_decimal_coerced(self):
        """TSH 0,1697 mUI/L regression: value must be normalized to float so
        the noise filter doesn't reject it as an unparseable string."""
        v = {"test_name": "TSH", "value": "0,1697", "unit": "mUI/L"}
        fix_range_fields(v)
        assert v["value"] == 0.1697
        assert isinstance(v["value"], float)

    def test_mixed_comma_and_dash(self):
        """'1,5 - 4,5' should parse correctly."""
        v = {"reference_range_low": "1,5 - 4,5", "reference_range_high": None}
        fix_range_fields(v)
        assert v["reference_range_low"] == 1.5
        assert v["reference_range_high"] == 4.5


# ── Case-insensitive unit aliases ──


class TestCaseInsensitiveUnit:
    """Verify case-insensitive unit alias matching."""

    def test_lowercase_mg_dl(self):
        normalizer = UnitNormalizer()
        result = normalizer.normalize_unit("mg/dl")
        assert result == "mg/dL"

    def test_uppercase_mg_dl(self):
        normalizer = UnitNormalizer()
        result = normalizer.normalize_unit("MG/DL")
        assert result == "mg/dL"

    def test_mixed_case(self):
        normalizer = UnitNormalizer()
        result = normalizer.normalize_unit("Mg/dL")
        assert result == "mg/dL"

    def test_exact_match_preferred(self):
        """Exact match should take priority over case-insensitive."""
        normalizer = UnitNormalizer()
        # mg/dL is in the alias table with exact case
        result = normalizer.normalize_unit("mg/dL")
        assert result == "mg/dL"

    def test_unknown_unit_unchanged(self):
        """Unknown unit should be returned as-is."""
        normalizer = UnitNormalizer()
        result = normalizer.normalize_unit("widgets/mL")
        assert result == "widgets/mL"

    def test_g_dl_case_insensitive(self):
        normalizer = UnitNormalizer()
        result = normalizer.normalize_unit("G/DL")
        # Should normalize to canonical form
        assert result.lower() == "g/dl"
