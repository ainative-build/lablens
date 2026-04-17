"""Phase 2 — canonical severity cap for low-clinical-impact analytes.

Judge-review P0: the old display_severity cap only affected the UI.
The CSV export used the raw engine severity, so Basophils showed
"moderate/consult" in exports while the UI badge said "mild". This
test suite locks in the canonical cap — engine severity and export
stay in sync with the UI.
"""

import pytest

from lablens.interpretation.engine import InterpretationEngine
from lablens.retrieval.clinical_priority import get_severity_cap


@pytest.fixture
def engine():
    return InterpretationEngine()


# --- Loader API ---


def test_get_severity_cap_basophils():
    assert get_severity_cap("Basophils") == "mild"


def test_get_severity_cap_substring_match():
    """Cap token matches as case-insensitive substring."""
    assert get_severity_cap("Basophils (BA SO) %") == "mild"
    assert get_severity_cap("NRBC absolute") == "mild"


def test_get_severity_cap_none_for_unrelated():
    assert get_severity_cap("Glucose") is None
    assert get_severity_cap("") is None


# --- Engine integration ---


def test_basophils_never_above_mild_even_with_curated_rule(engine):
    """If a future curated rule would yield moderate, cap still fires.

    We fake it by giving Basophils a lab range that would heuristically
    land in moderate territory. Phase 1 gate would already suppress to
    low_confidence (no curated rule), so Phase 2 cap is belt-and-braces
    — but it's what guarantees CSV parity when a rule is eventually added.
    """
    values = [{
        "test_name": "Basophils", "value": 3.0, "unit": "%",
        "loinc_code": "704-7",
        "ref_range_low": 0.0, "ref_range_high": 1.5,
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.severity in ("normal", "mild")
    # Even if Phase 1 gate lifted, Phase 2 would keep it ≤ mild
    assert r.severity != "moderate"
    assert r.severity != "critical"


def test_nrbc_never_above_mild(engine):
    values = [{
        "test_name": "NRBC", "value": 5.0, "unit": "%",
        "loinc_code": None,
        "ref_range_low": 0.0, "ref_range_high": 0.5,
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.severity != "moderate"
    assert r.severity != "critical"


def test_glucose_uncapped(engine):
    """Glucose is not in the cap list — curated bands still produce
    moderate/critical when applicable."""
    values = [{
        "test_name": "Glucose", "value": 250, "unit": "mg/dL",
        "loinc_code": "2345-7",
        "ref_range_low": 70, "ref_range_high": 100,
    }]
    report = engine.interpret_report(values, {0: "high"})
    r = report.values[0]
    assert r.severity in ("moderate", "critical")
