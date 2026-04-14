"""Tests for composite confidence scoring."""

from lablens.interpretation.confidence import calculate_confidence


def test_all_high():
    assert calculate_confidence("high", "lab-provided", "high") == "high"


def test_curated_range_caps_at_medium():
    assert calculate_confidence("high", "curated-fallback", "high") == "medium"


def test_low_match_drops_to_low():
    assert calculate_confidence("low", "lab-provided", "high") == "low"


def test_no_range_is_low():
    assert calculate_confidence("high", "none", "high") == "low"


def test_medium_match_medium_range():
    assert calculate_confidence("medium", "curated-fallback", "high") == "medium"


def test_low_unit_confidence():
    assert calculate_confidence("high", "lab-provided", "low") == "low"


def test_all_low():
    assert calculate_confidence("low", "none", "low") == "low"
