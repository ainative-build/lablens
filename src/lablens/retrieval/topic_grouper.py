"""Group interpreted lab values by health topic.

Phase 1a of the summary-first report UX. Backend pre-groups results so the
frontend just renders. See plans/260417-0010-summary-first-report-ux/plan.md
for the locked TopicGroup contract.

Within each group:  abnormal → indeterminate → normal
                    (severity desc, then deviation magnitude desc)
Across groups:      worst severity first; ties broken by abnormal-count desc
                    then by canonical topic order.
"""

from __future__ import annotations

import logging
from typing import Iterable

from lablens.interpretation.models import InterpretedResult
from lablens.models.report_summary import TopicGroup

logger = logging.getLogger(__name__)

# Canonical display order (used as the final tie-break across groups).
TOPIC_ORDER: tuple[str, ...] = (
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

_STATUS_RANK = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
_SEVERITY_RANK = {"normal": 0, "mild": 1, "moderate": 2, "critical": 3}


def _needs_attention(v: InterpretedResult) -> bool:
    return v.severity in ("moderate", "critical") or v.is_panic


def _is_abnormal(v: InterpretedResult) -> bool:
    return _needs_attention(v) or v.severity == "mild"


def _is_indeterminate(v: InterpretedResult) -> bool:
    return v.direction == "indeterminate"


def _deviation_magnitude(v: InterpretedResult) -> float:
    """Distance outside reference range, normalized to range width.

    Returns 0 when the value is in-range or unranked. Larger = more deviant.
    """
    try:
        val = float(v.value)
    except (TypeError, ValueError):
        return 0.0
    lo = v.reference_range_low
    hi = v.reference_range_high
    if lo is None or hi is None or hi <= lo:
        return 0.0
    width = hi - lo
    if val < lo:
        return (lo - val) / width
    if val > hi:
        return (val - hi) / width
    return 0.0


def _value_status(v: InterpretedResult) -> str:
    """Map one value's severity → traffic-light status."""
    if v.is_panic or v.severity == "critical":
        return "red"
    if v.severity == "moderate":
        return "orange"
    if v.severity == "mild":
        return "yellow"
    return "green"


def derive_group_status(values: Iterable[InterpretedResult]) -> str:
    """Worst-of traffic light across a group of values."""
    worst = "green"
    worst_rank = 0
    for v in values:
        s = _value_status(v)
        r = _STATUS_RANK[s]
        if r > worst_rank:
            worst_rank = r
            worst = s
    return worst


def _within_group_sort_key(v: InterpretedResult) -> tuple:
    """Sort within a topic group: abnormal → indeterminate → normal,
    severity desc, deviation desc."""
    # Tier: 0 = abnormal (mild/moderate/critical/panic), 1 = indeterminate, 2 = normal
    if _is_abnormal(v):
        tier = 0
    elif _is_indeterminate(v):
        tier = 1
    else:
        tier = 2
    sev_rank = _SEVERITY_RANK.get(v.severity, 0)
    dev = _deviation_magnitude(v)
    panic_rank = 1 if v.is_panic else 0
    # Higher severity / panic / deviation should come first → negate.
    return (tier, -panic_rank, -sev_rank, -dev, (v.test_name or "").lower())


def _summary_string(abnormal_count: int, indeterminate_count: int, total: int) -> str:
    """Short ≤80-char human summary."""
    needs = abnormal_count + indeterminate_count
    if needs == 0:
        return f"All normal ({total})"
    return f"{needs} of {total} need attention"


def build_topic_groups(values: list[InterpretedResult]) -> list[TopicGroup]:
    """Bucket interpreted values by `health_topic` and emit ordered groups.

    Values without `health_topic` are bucketed into "other".
    Returns groups sorted: worst-severity first, ties broken by abnormal-count
    desc, then by TOPIC_ORDER.
    """
    buckets: dict[str, list[InterpretedResult]] = {}
    for v in values:
        topic = getattr(v, "health_topic", None) or "other"
        buckets.setdefault(topic, []).append(v)

    topic_index = {t: i for i, t in enumerate(TOPIC_ORDER)}
    groups: list[TopicGroup] = []
    for topic, items in buckets.items():
        items_sorted = sorted(items, key=_within_group_sort_key)
        abnormal_count = sum(1 for v in items_sorted if _is_abnormal(v))
        indeterminate_count = sum(
            1 for v in items_sorted
            if _is_indeterminate(v) and not _is_abnormal(v)
        )
        total = len(items_sorted)
        status = derive_group_status(items_sorted)
        groups.append(
            TopicGroup(
                topic=topic,
                topic_label_key=f"topic.{topic}",
                status=status,
                summary=_summary_string(abnormal_count, indeterminate_count, total),
                abnormal_count=abnormal_count,
                indeterminate_count=indeterminate_count,
                total_count=total,
                results=[vars(v) for v in items_sorted],
            )
        )

    def _outer_key(g: TopicGroup) -> tuple:
        # worst severity desc, then abnormal_count desc, then TOPIC_ORDER asc
        return (
            -_STATUS_RANK[g.status],
            -g.abnormal_count,
            topic_index.get(g.topic, len(TOPIC_ORDER)),
        )

    groups.sort(key=_outer_key)
    return groups
