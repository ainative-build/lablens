"""Tests for the Phase 1a topic_grouper."""

from lablens.interpretation.models import InterpretedResult
from lablens.retrieval.topic_grouper import (
    TOPIC_ORDER,
    build_topic_groups,
    derive_group_status,
)


def _mk(
    name: str,
    topic: str,
    direction: str = "in-range",
    severity: str = "normal",
    is_panic: bool = False,
    value: float = 1.0,
    rl: float | None = None,
    rh: float | None = None,
) -> InterpretedResult:
    r = InterpretedResult(
        test_name=name,
        loinc_code=None,
        value=value,
        unit="",
        direction=direction,
        severity=severity,
        is_panic=is_panic,
        reference_range_low=rl,
        reference_range_high=rh,
    )
    r.health_topic = topic
    return r


class TestGrouping:
    def test_groups_by_topic(self):
        values = [
            _mk("Glucose", "blood_sugar"),
            _mk("HbA1c", "blood_sugar"),
            _mk("Creatinine", "kidney"),
        ]
        groups = build_topic_groups(values)
        topics = {g.topic for g in groups}
        assert topics == {"blood_sugar", "kidney"}

    def test_missing_topic_goes_to_other(self):
        v = InterpretedResult(test_name="X", loinc_code=None, value=1, unit="")
        # health_topic stays None
        groups = build_topic_groups([v])
        assert len(groups) == 1
        assert groups[0].topic == "other"

    def test_empty_input(self):
        assert build_topic_groups([]) == []


class TestWithinGroupSort:
    def test_abnormal_before_normal(self):
        values = [
            _mk("Normal1", "blood_sugar", severity="normal"),
            _mk("Mild", "blood_sugar", direction="high", severity="mild"),
            _mk("Critical", "blood_sugar", direction="high", severity="critical"),
            _mk("Moderate", "blood_sugar", direction="high", severity="moderate"),
        ]
        groups = build_topic_groups(values)
        names = [r["test_name"] for r in groups[0].results]
        # critical → moderate → mild → normal
        assert names == ["Critical", "Moderate", "Mild", "Normal1"]

    def test_panic_first(self):
        values = [
            _mk("Critical", "blood_sugar", direction="high", severity="critical"),
            _mk("Panic", "blood_sugar", direction="high", severity="mild", is_panic=True),
        ]
        groups = build_topic_groups(values)
        names = [r["test_name"] for r in groups[0].results]
        assert names[0] == "Panic"

    def test_indeterminate_between_abnormal_and_normal(self):
        values = [
            _mk("Normal", "kidney"),
            _mk("Indet", "kidney", direction="indeterminate"),
            _mk("Abn", "kidney", direction="high", severity="mild"),
        ]
        groups = build_topic_groups(values)
        names = [r["test_name"] for r in groups[0].results]
        assert names == ["Abn", "Indet", "Normal"]

    def test_deviation_tiebreak(self):
        # Two moderate-high values; bigger deviation should sort first.
        a = _mk(
            "FarHigh", "kidney", direction="high", severity="moderate",
            value=20.0, rl=0.0, rh=10.0,  # 100% over the range
        )
        b = _mk(
            "JustHigh", "kidney", direction="high", severity="moderate",
            value=11.0, rl=0.0, rh=10.0,  # 10% over the range
        )
        groups = build_topic_groups([b, a])
        names = [r["test_name"] for r in groups[0].results]
        assert names == ["FarHigh", "JustHigh"]


class TestStatus:
    def test_all_normal_green(self):
        v = [_mk("X", "kidney")]
        assert derive_group_status(v) == "green"

    def test_mild_yellow(self):
        v = [_mk("X", "kidney", direction="high", severity="mild")]
        assert derive_group_status(v) == "yellow"

    def test_moderate_orange(self):
        v = [_mk("X", "kidney", direction="high", severity="moderate")]
        assert derive_group_status(v) == "orange"

    def test_critical_red(self):
        v = [_mk("X", "kidney", direction="high", severity="critical")]
        assert derive_group_status(v) == "red"

    def test_panic_red_overrides_mild(self):
        v = [_mk("X", "kidney", direction="high", severity="mild", is_panic=True)]
        assert derive_group_status(v) == "red"

    def test_worst_of(self):
        v = [
            _mk("Normal", "kidney"),
            _mk("Mild", "kidney", direction="high", severity="mild"),
            _mk("Mod", "kidney", direction="high", severity="moderate"),
        ]
        assert derive_group_status(v) == "orange"


class TestSummaryString:
    def test_all_normal(self):
        groups = build_topic_groups([_mk("A", "kidney"), _mk("B", "kidney")])
        assert groups[0].summary == "All normal (2)"

    def test_some_abnormal(self):
        groups = build_topic_groups([
            _mk("A", "kidney"),
            _mk("B", "kidney", direction="high", severity="mild"),
            _mk("C", "kidney", direction="high", severity="moderate"),
            _mk("D", "kidney"),
        ])
        # PR #6 calibration: copy uses "worth follow-up" (less alarmist).
        assert groups[0].summary == "2 of 4 worth follow-up"

    def test_indeterminate_only_summary(self):
        groups = build_topic_groups([
            _mk("A", "kidney", direction="indeterminate"),
            _mk("B", "kidney"),
        ])
        # Calibrated: indeterminate-only group separates "unclear" from
        # follow-up so it doesn't blend with abnormal items.
        assert groups[0].summary == "1 unclear"

    def test_minor_findings_separated_from_followup(self):
        # Basophils is in clinical-priority exclude list → counts as minor,
        # not as "worth follow-up".
        groups = build_topic_groups([
            _mk("Basophils", "blood_count", direction="low", severity="moderate"),
            _mk("Hgb", "blood_count", direction="low", severity="mild"),
        ])
        g = groups[0]
        assert g.minor_count == 1
        assert g.abnormal_count == 1
        # Display severity capped for low-impact tests
        baso = next(r for r in g.results if r["test_name"] == "Basophils")
        assert baso["display_severity"] == "mild"
        assert baso["is_minor"] is True

    def test_summary_under_80_chars(self):
        groups = build_topic_groups([
            _mk(f"T{i}", "kidney", direction="high", severity="moderate")
            for i in range(99)
        ])
        assert len(groups[0].summary) <= 80


class TestOuterOrder:
    def test_worst_status_first(self):
        values = [
            _mk("Glucose", "blood_sugar"),  # all-green
            _mk("Cr", "kidney", direction="high", severity="critical"),  # red
            _mk("ALT", "liver", direction="high", severity="mild"),  # yellow
        ]
        groups = build_topic_groups(values)
        statuses = [g.status for g in groups]
        # red, yellow, green
        assert statuses == ["red", "yellow", "green"]

    def test_canonical_order_tiebreak(self):
        # Two green groups; should follow TOPIC_ORDER
        values = [
            _mk("Cr", "kidney"),
            _mk("Glucose", "blood_sugar"),
        ]
        groups = build_topic_groups(values)
        topics = [g.topic for g in groups]
        # blood_sugar comes before kidney in TOPIC_ORDER
        assert topics.index("blood_sugar") < topics.index("kidney")
        # sanity: TOPIC_ORDER agrees
        assert TOPIC_ORDER.index("blood_sugar") < TOPIC_ORDER.index("kidney")


class TestCounts:
    def test_counts(self):
        values = [
            _mk("A", "kidney", direction="high", severity="critical"),  # abnormal
            _mk("B", "kidney", direction="high", severity="moderate"),  # abnormal
            _mk("C", "kidney", direction="indeterminate"),  # indeterminate
            _mk("D", "kidney"),  # normal
        ]
        groups = build_topic_groups(values)
        g = groups[0]
        assert g.abnormal_count == 2
        assert g.indeterminate_count == 1
        assert g.total_count == 4
