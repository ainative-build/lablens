"""Map a lab value (LOINC or test name) → 1 of 11 health topics.

Phase 1a of the summary-first report UX. Topics drive the L2 grouping
in the report and the Q&A grounding context.

Lookup cascade:
  1. LOINC → topic (curated, from common-aliases.yaml `topic:` field)
  2. Test name → topic via alias map (curated, same source)
  3. LOINC → analyte family.category → topic (FAMILY_CATEGORY_TO_TOPIC table)
  4. fallback: ("other", inferred=True)

Loaded once at module import; thread-safe (read-only after load).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from lablens.extraction.range_plausibility_checker import (
    RangePlausibilityChecker,
)
from lablens.extraction.terminology_mapper import normalize_test_name

logger = logging.getLogger(__name__)

_ALIASES_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "data"
    / "aliases"
    / "common-aliases.yaml"
)

# 11-bucket taxonomy. Keep in sync with topic_grouper.TOPIC_ORDER and the
# locked frontend i18n keys (topic.<id>).
KNOWN_TOPICS: tuple[str, ...] = (
    "blood_sugar",
    "heart_lipids",
    "kidney",
    "liver",
    "blood_count",
    "thyroid_hormones",
    "vitamins_minerals",
    "electrolytes",
    "inflammation",
    "urinalysis_other",
    "other",
)

# Map from analyte-families.yaml `category` → topic id.
# Used as the fallback when LOINC-level curated topic is unknown.
FAMILY_CATEGORY_TO_TOPIC: dict[str, str] = {
    "cbc": "blood_count",
    "hematology": "blood_count",
    "electrolyte": "electrolytes",
    "lipid": "heart_lipids",
    "endocrine": "thyroid_hormones",
    "hormone": "thyroid_hormones",
    "tumor-marker": "urinalysis_other",
    "kidney": "kidney",
    "liver": "liver",
    "metabolic": "blood_sugar",
    "infectious": "urinalysis_other",
    "nutrition": "vitamins_minerals",
    "inflammatory": "inflammation",
}


def _load_topic_tables() -> tuple[dict[str, str], dict[str, str]]:
    """Build LOINC→topic and name→topic maps from aliases YAML.

    Two-pass load: canonicals first, then aliases. Canonical mappings always
    win over alias collisions (e.g. "glucose" canonical maps to blood_sugar
    even though "Glucose (Urine)" alias normalizes to the same key). Within
    aliases, first-wins (do not overwrite).
    """
    loinc_to_topic: dict[str, str] = {}
    name_to_topic: dict[str, str] = {}
    if not _ALIASES_PATH.exists():
        logger.warning("common-aliases.yaml not found at %s", _ALIASES_PATH)
        return loinc_to_topic, name_to_topic

    data = yaml.safe_load(_ALIASES_PATH.read_text()) or {}
    entries = data.get("aliases", [])

    # Pass 1: LOINC + canonicals (always authoritative)
    canonical_keys: set[str] = set()
    for entry in entries:
        topic = entry.get("topic")
        if not topic:
            continue
        loinc = entry.get("loinc")
        if loinc:
            loinc_to_topic[loinc] = topic
        canonical = entry.get("canonical", "")
        if canonical:
            for k in (canonical.lower().strip(), normalize_test_name(canonical)):
                if k:
                    name_to_topic[k] = topic
                    canonical_keys.add(k)

    # Pass 2: aliases (first-wins; never overwrite a canonical)
    for entry in entries:
        topic = entry.get("topic")
        if not topic:
            continue
        for _lang, names in (entry.get("aliases") or {}).items():
            for name in names:
                for k in (
                    (name or "").lower().strip(),
                    normalize_test_name(name or ""),
                ):
                    if not k or k in canonical_keys:
                        continue
                    name_to_topic.setdefault(k, topic)
    return loinc_to_topic, name_to_topic


# Module-level singletons. Loaded once at import time.
LOINC_TO_TOPIC, NAME_TO_TOPIC = _load_topic_tables()

# Family-checker singleton — provides LOINC → category lookup.
_FAMILY_CHECKER = RangePlausibilityChecker()


def get_health_topic(
    loinc: str | None, test_name: str | None
) -> tuple[str, bool]:
    """Resolve a lab value to a health topic.

    Returns:
        (topic_id, inferred) where inferred=False means the topic came from a
        curated source (LOINC or alias map) and inferred=True means we fell
        back to family.category or "other".
    """
    # 1) Curated LOINC lookup
    if loinc and loinc in LOINC_TO_TOPIC:
        return LOINC_TO_TOPIC[loinc], False

    # 2) Curated alias-name lookup (raw + normalized)
    if test_name:
        key = test_name.lower().strip()
        if key in NAME_TO_TOPIC:
            return NAME_TO_TOPIC[key], False
        norm = normalize_test_name(test_name)
        if norm and norm in NAME_TO_TOPIC:
            return NAME_TO_TOPIC[norm], False

    # 3) Family category fallback (inferred)
    if loinc:
        category = _FAMILY_CHECKER.get_category(loinc)
        if category and category in FAMILY_CATEGORY_TO_TOPIC:
            return FAMILY_CATEGORY_TO_TOPIC[category], True

    # 4) Final fallback
    return "other", True
