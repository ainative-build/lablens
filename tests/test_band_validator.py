"""Tests for severity band contiguity validation."""

from lablens.interpretation.band_validator import validate_band_contiguity


def test_valid_contiguous_bands():
    rules = {
        "test-1": {
            "severity_bands": {
                "normal": {"low": 70, "high": 100},
                "mild_low": {"low": 54, "high": 69},
                "mild_high": {"low": 101, "high": 125},
                "moderate_low": {"low": 40, "high": 53},
                "moderate_high": {"low": 126, "high": 250},
                "critical_low": {"low": 0, "high": 39},
                "critical_high": {"low": 251, "high": 9999},
            }
        }
    }
    errors = validate_band_contiguity(rules)
    assert len(errors) == 0


def test_gap_detected():
    rules = {
        "test-1": {
            "severity_bands": {
                "normal": {"low": 70, "high": 100},
                # Gap: 101-124 not covered
                "mild_high": {"low": 126, "high": 200},
            }
        }
    }
    errors = validate_band_contiguity(rules)
    assert len(errors) >= 1


def test_empty_rules():
    errors = validate_band_contiguity({})
    assert len(errors) == 0


def test_single_band_no_error():
    rules = {
        "test-1": {
            "severity_bands": {
                "normal": {"low": 0, "high": 999},
            }
        }
    }
    errors = validate_band_contiguity(rules)
    assert len(errors) == 0


def test_real_rules_no_gaps():
    """Our curated rules should have no significant gaps."""
    from lablens.knowledge.rules_loader import load_all_rules
    from pathlib import Path

    rules_dir = Path(__file__).parent.parent / "data" / "rules"
    rules = load_all_rules(rules_dir)
    errors = validate_band_contiguity(rules)
    assert len(errors) == 0, f"Band gaps found in curated rules: {errors}"
