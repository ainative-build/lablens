"""Tests for the Phase 1a health-topic mapper."""

from pathlib import Path

import yaml

from lablens.extraction.health_topic_mapper import (
    FAMILY_CATEGORY_TO_TOPIC,
    KNOWN_TOPICS,
    LOINC_TO_TOPIC,
    NAME_TO_TOPIC,
    get_health_topic,
)


_ALIASES_PATH = (
    Path(__file__).parent.parent
    / "data"
    / "aliases"
    / "common-aliases.yaml"
)


class TestCuratedCoverage:
    """Every canonical in common-aliases.yaml maps to a known topic."""

    def test_every_canonical_has_topic(self):
        data = yaml.safe_load(_ALIASES_PATH.read_text())
        missing = [
            e["canonical"] for e in data.get("aliases", [])
            if "topic" not in e
        ]
        assert missing == [], (
            f"{len(missing)} canonicals lack topic: {missing[:5]}..."
        )

    def test_every_topic_is_known(self):
        data = yaml.safe_load(_ALIASES_PATH.read_text())
        for entry in data.get("aliases", []):
            assert entry["topic"] in KNOWN_TOPICS, (
                f"{entry['canonical']} has unknown topic={entry['topic']}"
            )

    def test_loinc_table_loaded(self):
        # 90 canonicals × 1 loinc each = 90 entries
        assert len(LOINC_TO_TOPIC) >= 80

    def test_name_table_loaded(self):
        # 90 canonicals × ~5 aliases each → many hundred entries
        assert len(NAME_TO_TOPIC) >= 100

    def test_family_categories_all_known_topics(self):
        for cat, topic in FAMILY_CATEGORY_TO_TOPIC.items():
            assert topic in KNOWN_TOPICS, f"{cat} → {topic} unknown"


class TestLOINCLookup:
    def test_hba1c(self):
        topic, inferred = get_health_topic("4548-4", "HbA1c")
        assert topic == "blood_sugar"
        assert inferred is False

    def test_creatinine(self):
        topic, inferred = get_health_topic("2160-0", "Creatinine")
        assert topic == "kidney"
        assert inferred is False

    def test_alt(self):
        topic, inferred = get_health_topic("1742-6", "ALT")
        assert topic == "liver"
        assert inferred is False

    def test_hdl(self):
        topic, inferred = get_health_topic("2085-9", "HDL Cholesterol")
        assert topic == "heart_lipids"
        assert inferred is False

    def test_tsh(self):
        topic, inferred = get_health_topic("3016-3", "TSH")
        assert topic == "thyroid_hormones"
        assert inferred is False

    def test_vitamin_d(self):
        topic, inferred = get_health_topic("1989-3", "25-OH Vitamin D")
        assert topic == "vitamins_minerals"
        assert inferred is False


class TestNameFallback:
    """LOINC missing → name lookup still finds curated topic."""

    def test_alias_match(self):
        topic, inferred = get_health_topic(None, "WBC")
        assert topic == "blood_count"
        assert inferred is False

    def test_canonical_match(self):
        topic, inferred = get_health_topic(None, "Glucose")
        assert topic == "blood_sugar"
        assert inferred is False

    def test_normalized_match(self):
        # "HbA1c" normalizes through abbreviation map
        topic, inferred = get_health_topic(None, "HBA1C")
        assert topic == "blood_sugar"
        assert inferred is False


class TestFamilyFallback:
    """Unknown LOINC but mapped via family category → inferred=True."""

    def test_tumor_marker_family(self):
        # PSA loinc 2857-1 is in tumor_markers family but not in
        # common-aliases.yaml curated list.
        topic, inferred = get_health_topic("2857-1", "PSA")
        assert topic == "urinalysis_other"
        assert inferred is True


class TestUnknownFallback:
    def test_blank(self):
        topic, inferred = get_health_topic(None, "")
        assert topic == "other"
        assert inferred is True

    def test_unknown_loinc_unknown_name(self):
        topic, inferred = get_health_topic("99999-9", "Some Unknown Test")
        assert topic == "other"
        assert inferred is True

    def test_none_loinc_none_name(self):
        topic, inferred = get_health_topic(None, None)
        assert topic == "other"
        assert inferred is True
