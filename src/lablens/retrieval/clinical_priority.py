"""Clinical-priority loader — shared by summarizer + topic_grouper.

Loads `data/clinical-priority.yaml`. Tests in the `exclude_from_summary`
list are treated as low-clinical-impact:

  - Excluded from `summary.top_findings` hero (handled in report_summarizer)
  - Counted as `minor_count` instead of `abnormal_count` in topic groups
  - UI badge capped at "mild" (handled in frontend via display_severity)

Module-level cache: file is read once at import.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


_CLINICAL_PRIORITY_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "clinical-priority.yaml"
)


def _load() -> set[str]:
    if not _CLINICAL_PRIORITY_PATH.exists():
        return set()
    try:
        data = yaml.safe_load(_CLINICAL_PRIORITY_PATH.read_text()) or {}
    except yaml.YAMLError as e:
        logger.warning("Failed to parse clinical-priority.yaml: %s", e)
        return set()
    items = data.get("exclude_from_summary", []) or []
    return {str(s).lower() for s in items if isinstance(s, str)}


_TOKENS: set[str] = _load()


def is_low_clinical_priority(test_name: str) -> bool:
    """True if isolated abnormalities in this test are clinically minor.

    Match is case-insensitive substring. e.g. "Basophils" matches
    "Basophils (BA SO) %".
    """
    name = (test_name or "").lower()
    return any(token in name for token in _TOKENS)


def display_severity(test_name: str, raw_severity: str) -> str:
    """Cap severity for display — low-clinical-impact tests never show
    'moderate' or 'critical' in the UI; cap at 'mild'.

    Engine severity is unchanged for clinical correctness; only display
    cascades to a softer label so card badge matches the explanation tone.
    """
    if not raw_severity:
        return raw_severity
    if is_low_clinical_priority(test_name) and raw_severity in (
        "moderate",
        "critical",
    ):
        return "mild"
    return raw_severity
