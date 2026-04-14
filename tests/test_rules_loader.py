"""Tests for the rules loader module."""

from pathlib import Path

from lablens.knowledge.rules_loader import get_rule, load_all_rules

RULES_DIR = Path(__file__).parent.parent / "data" / "rules"


def test_load_all_rules_returns_dict():
    rules = load_all_rules(RULES_DIR)
    assert isinstance(rules, dict)
    assert len(rules) > 0


def test_load_all_rules_count():
    """We expect ~50 rules across all YAML files."""
    rules = load_all_rules(RULES_DIR)
    assert len(rules) >= 40, f"Expected >=40 rules, got {len(rules)}"


def test_each_rule_has_required_fields():
    rules = load_all_rules(RULES_DIR)
    for loinc_code, rule in rules.items():
        assert "loinc_code" in rule, f"Missing loinc_code in rule"
        assert rule["loinc_code"] == loinc_code
        assert "test_name" in rule, f"Missing test_name for {loinc_code}"
        assert "unit" in rule, f"Missing unit for {loinc_code}"
        assert "reference_ranges" in rule, f"Missing reference_ranges for {loinc_code}"
        assert "severity_bands" in rule, f"Missing severity_bands for {loinc_code}"
        assert "actionability" in rule, f"Missing actionability for {loinc_code}"


def test_reference_ranges_have_source():
    """Every range must cite a published guideline."""
    rules = load_all_rules(RULES_DIR)
    for loinc_code, rule in rules.items():
        for rr in rule["reference_ranges"]:
            assert "source" in rr, f"Missing source in reference_range for {loinc_code}"
            assert len(rr["source"]) > 5, f"Source too short for {loinc_code}: {rr['source']}"


def test_severity_bands_have_low_high():
    rules = load_all_rules(RULES_DIR)
    for loinc_code, rule in rules.items():
        for band_name, band in rule["severity_bands"].items():
            assert "low" in band, f"Missing low in {band_name} for {loinc_code}"
            assert "high" in band, f"Missing high in {band_name} for {loinc_code}"


def test_get_rule_existing():
    rules = load_all_rules(RULES_DIR)
    glucose = get_rule("2345-7", rules)
    assert glucose is not None
    assert glucose["test_name"] == "Glucose"


def test_get_rule_missing():
    rules = load_all_rules(RULES_DIR)
    result = get_rule("NONEXISTENT", rules)
    assert result is None


def test_load_empty_directory(tmp_path):
    rules = load_all_rules(tmp_path)
    assert rules == {}


def test_cbc_panel_has_10_tests():
    rules = load_all_rules(RULES_DIR)
    cbc_codes = {"6690-2", "789-8", "718-7", "4544-3", "777-3", "787-2", "785-6", "786-4", "788-0", "32623-1"}
    loaded_cbc = cbc_codes & set(rules.keys())
    assert len(loaded_cbc) == 10, f"Expected 10 CBC tests, got {len(loaded_cbc)}"


def test_bmp_panel_has_8_tests():
    rules = load_all_rules(RULES_DIR)
    bmp_codes = {"2345-7", "3094-0", "2160-0", "2951-2", "2823-3", "2075-0", "2028-9", "17861-6"}
    loaded_bmp = bmp_codes & set(rules.keys())
    assert len(loaded_bmp) == 8, f"Expected 8 BMP tests, got {len(loaded_bmp)}"
