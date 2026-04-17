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

import yaml

from lablens._data_paths import data_path

logger = logging.getLogger(__name__)


_CLINICAL_PRIORITY_PATH = data_path("clinical-priority.yaml")

_SEVERITY_ORDER = {"normal": 0, "mild": 1, "moderate": 2, "critical": 3}


def _load() -> tuple[set[str], dict[str, str]]:
    if not _CLINICAL_PRIORITY_PATH.exists():
        return set(), {}
    try:
        data = yaml.safe_load(_CLINICAL_PRIORITY_PATH.read_text()) or {}
    except yaml.YAMLError as e:
        logger.warning("Failed to parse clinical-priority.yaml: %s", e)
        return set(), {}
    items = data.get("exclude_from_summary", []) or []
    tokens = {str(s).lower() for s in items if isinstance(s, str)}
    raw_caps = data.get("severity_cap", {}) or {}
    caps = {
        str(k).lower(): str(v).lower()
        for k, v in raw_caps.items()
        if isinstance(k, str) and str(v).lower() in _SEVERITY_ORDER
    }
    return tokens, caps


_TOKENS, _SEVERITY_CAPS = _load()


def is_low_clinical_priority(test_name: str) -> bool:
    """True if isolated abnormalities in this test are clinically minor.

    Match is case-insensitive substring. e.g. "Basophils" matches
    "Basophils (BA SO) %".
    """
    name = (test_name or "").lower()
    return any(token in name for token in _TOKENS)


def get_severity_cap(test_name: str) -> str | None:
    """Return the canonical severity cap for this test, or None if uncapped.

    Case-insensitive substring match, same as `is_low_clinical_priority`.
    The engine applies this cap so the stored (and exported) severity
    matches what the UI shows.
    """
    name = (test_name or "").lower()
    if not name:
        return None
    for token, cap in _SEVERITY_CAPS.items():
        if token in name:
            return cap
    return None


def display_severity(test_name: str, raw_severity: str) -> str:
    """Defensive display-side cap, kept as a safety net.

    As of Phase 2, the engine already applies the canonical cap to
    InterpretedResult.severity, so CSV export and UI agree. This
    function is retained so any legacy path that skips the engine
    (e.g., reconstructed results) still surfaces a capped badge.
    """
    if not raw_severity:
        return raw_severity
    cap = get_severity_cap(test_name)
    if cap and _SEVERITY_ORDER.get(
        raw_severity, 0
    ) > _SEVERITY_ORDER.get(cap, 0):
        return cap
    return raw_severity
