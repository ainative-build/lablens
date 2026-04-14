"""Tests for panel completeness checker."""

from lablens.interpretation.panel_checker import check_panels


def test_full_cbc_panel():
    codes = ["6690-2", "789-8", "718-7", "4544-3", "777-3"]
    panels = check_panels(codes, {})
    assert len(panels) == 1
    assert panels[0].panel_name == "CBC"
    assert len(panels[0].missing) == 0


def test_partial_cbc_panel():
    codes = ["6690-2", "718-7"]  # WBC + Hemoglobin only
    panels = check_panels(codes, {})
    cbc = [p for p in panels if p.panel_name == "CBC"]
    assert len(cbc) == 1
    assert len(cbc[0].missing) == 3


def test_no_panel_detected():
    codes = ["6690-2"]  # Only one test, not enough for panel
    panels = check_panels(codes, {})
    assert len(panels) == 0


def test_multiple_panels():
    codes = [
        "6690-2", "789-8", "718-7", "4544-3", "777-3",  # CBC
        "2345-7", "3094-0", "2160-0", "2951-2", "2823-3",  # BMP partial
    ]
    panels = check_panels(codes, {})
    panel_names = {p.panel_name for p in panels}
    assert "CBC" in panel_names
    assert "BMP" in panel_names
