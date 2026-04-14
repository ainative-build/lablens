"""Tests for terminology mapper — LOINC matching."""

import pytest

from lablens.extraction.alias_registry import AliasRegistry
from lablens.extraction.terminology_mapper import TerminologyMapper


@pytest.fixture
def mapper():
    return TerminologyMapper()


def test_exact_match(mapper):
    code, conf = mapper.match("Glucose")
    assert code == "2345-7"
    assert conf == "high"


def test_exact_match_case_insensitive(mapper):
    code, conf = mapper.match("glucose")
    assert code == "2345-7"
    assert conf == "high"


def test_alias_match_en(mapper):
    code, conf = mapper.match("WBC")
    assert code == "6690-2"
    assert conf == "medium"


def test_alias_match_en_full(mapper):
    code, conf = mapper.match("White Blood Cells")
    assert code == "6690-2"
    assert conf == "medium"


def test_alias_match_fr(mapper):
    code, conf = mapper.match("Glycémie")
    assert code == "2345-7"
    assert conf == "medium"


def test_alias_match_ar(mapper):
    code, conf = mapper.match("الكرياتينين")
    assert code == "2160-0"
    assert conf == "medium"


def test_alias_match_vn(mapper):
    code, conf = mapper.match("Đường huyết")
    assert code == "2345-7"
    assert conf == "medium"


def test_alias_sgpt_alt(mapper):
    code, conf = mapper.match("SGPT")
    assert code == "1742-6"
    assert conf == "medium"


def test_alias_sgot_ast(mapper):
    code, conf = mapper.match("SGOT")
    assert code == "1920-8"
    assert conf == "medium"


def test_fuzzy_match(mapper):
    # "White Blood Cell" should fuzzy-match "White Blood Cells"
    code, conf = mapper.match("White Blood Cell")
    assert code is not None
    assert conf == "low"


def test_unknown_test(mapper):
    code, conf = mapper.match("XYZ-Unknown-Test-12345")
    assert code is None
    assert conf == "low"


def test_all_50_canonical_names_match(mapper):
    """Every canonical name in our alias registry should exact-match."""
    registry = mapper.registry
    for key in registry._exact:
        code, conf = mapper.match(key)
        assert code is not None, f"Canonical name '{key}' did not match"
        assert conf == "high"
