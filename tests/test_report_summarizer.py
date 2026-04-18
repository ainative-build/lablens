"""Tests for report_summarizer (Phase 1b)."""

import asyncio

import pytest

from lablens.interpretation.models import InterpretedResult
from lablens.models.report_summary import ReportSummary
from lablens.retrieval.report_summarizer import (
    HeadlineGenerator,
    _validate_headline,
    build_summary,
    build_summary_sync,
    derive_status,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def make_value(
    name: str = "Test",
    value: float = 5.0,
    unit: str = "mg/dL",
    direction: str = "in-range",
    severity: str = "normal",
    is_panic: bool = False,
    health_topic: str = "other",
    ref_low: float | None = None,
    ref_high: float | None = None,
) -> InterpretedResult:
    return InterpretedResult(
        test_name=name,
        loinc_code=None,
        value=value,
        unit=unit,
        direction=direction,
        severity=severity,
        is_panic=is_panic,
        health_topic=health_topic,
        reference_range_low=ref_low,
        reference_range_high=ref_high,
    )


# ─────────────────────────────────────────────────────────────────────────────
# derive_status — traffic-light mapping
# ─────────────────────────────────────────────────────────────────────────────
class TestDeriveStatus:
    def test_all_normal_is_green(self):
        values = [make_value(severity="normal") for _ in range(5)]
        assert derive_status(values) == "green"

    def test_any_mild_is_yellow(self):
        values = [
            make_value(severity="normal"),
            make_value(severity="mild"),
        ]
        assert derive_status(values) == "yellow"

    def test_any_moderate_is_orange(self):
        values = [
            make_value(severity="mild"),
            make_value(severity="moderate"),
        ]
        assert derive_status(values) == "orange"

    def test_any_critical_is_red(self):
        values = [make_value(severity="critical")]
        assert derive_status(values) == "red"

    def test_panic_is_red_even_if_severity_normal(self):
        values = [make_value(severity="normal", is_panic=True)]
        assert derive_status(values) == "red"

    def test_empty_is_green(self):
        assert derive_status([]) == "green"


# ─────────────────────────────────────────────────────────────────────────────
# build_summary_sync — deterministic path
# ─────────────────────────────────────────────────────────────────────────────
class TestBuildSummarySync:
    def test_empty_yields_green(self):
        s = build_summary_sync([])
        assert isinstance(s, ReportSummary)
        assert s.overall_status == "green"
        assert s.top_findings == []
        assert s.next_steps_key == "green"
        assert s.indeterminate_count == 0
        assert s.uncertainty_note_key is None
        assert s.headline == "Most results are within expected range."

    def test_top_findings_capped_at_3(self):
        values = [
            make_value(name=f"Test{i}", severity="moderate", direction="high")
            for i in range(5)
        ]
        s = build_summary_sync(values)
        assert len(s.top_findings) == 3

    def test_top_findings_severity_sorted(self):
        values = [
            make_value(name="Mild1", severity="mild", direction="high"),
            make_value(name="Critical1", severity="critical", direction="high"),
            make_value(name="Moderate1", severity="moderate", direction="high"),
        ]
        s = build_summary_sync(values)
        # critical → moderate → mild
        names = [f.test_name for f in s.top_findings]
        assert names == ["Critical1", "Moderate1", "Mild1"]

    def test_panic_outranks_severity_within_same_tier(self):
        values = [
            make_value(name="Crit", severity="critical", direction="high"),
            make_value(
                name="CritPanic",
                severity="critical",
                direction="high",
                is_panic=True,
            ),
        ]
        s = build_summary_sync(values)
        # Panic float-up among critical-severity items
        assert s.top_findings[0].test_name == "CritPanic"

    def test_deviation_breaks_severity_tie(self):
        values = [
            make_value(
                name="Small",
                severity="mild",
                direction="high",
                value=11.0,
                ref_high=10.0,
            ),
            make_value(
                name="Big",
                severity="mild",
                direction="high",
                value=20.0,
                ref_high=10.0,
            ),
        ]
        s = build_summary_sync(values)
        assert s.top_findings[0].test_name == "Big"

    def test_indeterminate_counted_and_noted(self):
        values = [
            make_value(direction="indeterminate"),
            make_value(direction="indeterminate"),
            make_value(severity="moderate", direction="high"),
        ]
        s = build_summary_sync(values)
        assert s.indeterminate_count == 2
        assert s.uncertainty_note_key == "summary.indeterminate.note"

    def test_no_indeterminate_no_note(self):
        s = build_summary_sync([make_value(severity="mild", direction="high")])
        assert s.indeterminate_count == 0
        assert s.uncertainty_note_key is None

    def test_low_confidence_counted_as_unclear(self):
        """Round-2: low_confidence rows (suppressed severity, provenance-only)
        roll up into the unclear bucket so the hero summary count matches the
        per-topic UI tallies. eGFR with OCR-flag-only evidence is the canonical
        example — direction arrow suppressed but state still uncertain."""
        low_conf = make_value(
            name="eGFR", severity="normal", direction="indeterminate",
        )
        low_conf.classification_state = "low_confidence"
        # Also test a low_confidence row that still carries direction (engine
        # uncertainty gate path — range present but no curated bands).
        low_conf_with_dir = make_value(
            name="Basophils %", severity="normal", direction="high",
        )
        low_conf_with_dir.classification_state = "low_confidence"
        values = [
            low_conf,
            low_conf_with_dir,
            make_value(severity="moderate", direction="high"),
        ]
        s = build_summary_sync(values)
        assert s.indeterminate_count == 2
        assert s.uncertainty_note_key == "summary.indeterminate.note"

    def test_status_drives_next_steps_key(self):
        s = build_summary_sync([make_value(severity="critical")])
        assert s.next_steps_key == "red"

    def test_normal_values_excluded_from_top_findings(self):
        values = [
            make_value(name="N1", severity="normal"),
            make_value(name="A1", severity="mild", direction="high"),
        ]
        s = build_summary_sync(values)
        assert [f.test_name for f in s.top_findings] == ["A1"]


# ─────────────────────────────────────────────────────────────────────────────
# Headline guardrails — adversarial validation
# ─────────────────────────────────────────────────────────────────────────────
class TestHeadlineGuardrails:
    def _top(self, *names):
        return [
            type("F", (), {"test_name": n})()
            for n in names
        ]

    def test_accepts_clean_yellow_headline(self):
        text = "Most results look normal; a few items may need closer review soon."
        out = _validate_headline(text, "yellow", self._top("LDL"))
        assert out is None, out

    def test_accepts_clean_red_headline(self):
        # Calibrated wording: "follow up" satisfies red required word set.
        text = "A few results stand out and may need follow-up with your clinician promptly."
        out = _validate_headline(text, "red", self._top("LDL"))
        assert out is None, out

    def test_rejects_diagnostic_verb_you_have(self):
        text = "Your results show you have diabetes and need follow-up immediately."
        out = _validate_headline(text, "red", self._top("HbA1c"))
        assert out is not None
        assert "denied_verb" in out

    def test_rejects_diagnostic_verb_diagnosed(self):
        text = "Recent results suggest you are diagnosed with high cholesterol; review soon."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is not None

    def test_rejects_drug_mention(self):
        text = "Consider starting metformin for elevated readings; review with monitoring now."
        out = _validate_headline(text, "orange", self._top("HbA1c"))
        assert out is not None
        assert "drug:metformin" in out

    def test_rejects_dose_pattern(self):
        text = "Recommend 500 mg daily for elevated values; review with monitoring soon."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is not None
        assert "dose_pattern" in out or "drug" in out

    def test_rejects_too_short(self):
        text = "Looks fine."
        out = _validate_headline(text, "yellow", self._top("LDL"))
        assert out is not None
        assert "word_count" in out

    def test_rejects_too_long(self):
        text = " ".join(["word"] * 30) + " monitor."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is not None
        assert "word_count" in out

    def test_rejects_orange_without_status_word(self):
        # No status-aligned word → silent omission attack
        text = "All within typical reference; everything appears stable across panels."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is not None
        assert "missing_status_word" in out

    def test_rejects_red_with_only_neutral_phrasing(self):
        text = "Numbers appear stable across the listed analytes from this report."
        out = _validate_headline(text, "red", self._top("LDL"))
        assert out is not None
        assert "missing_status_word" in out

    def test_rejects_off_list_analyte(self):
        # "TSH" not in top_findings, headline mentions it
        text = "Your TSH appears elevated; please review the result with attention."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is not None
        assert "off_list_analyte" in out

    def test_accepts_off_list_when_substring_match(self):
        # Allowed substring tolerance: "Vitamin D" in top_findings should let
        # headline say "vit d" — handled at substring level via normalized name
        text = "LDL appears mildly elevated; review with your clinician for attention."
        out = _validate_headline(text, "orange", self._top("LDL Cholesterol"))
        assert out is None, out

    def test_rejects_multiline(self):
        text = "Results look fine.\nReview soon for attention."
        out = _validate_headline(text, "yellow", self._top("LDL"))
        assert out is not None
        assert out == "multiline"

    def test_rejects_empty(self):
        assert _validate_headline("", "red", self._top("LDL")) == "empty"
        assert _validate_headline("   ", "red", self._top("LDL")) == "empty"


# ─────────────────────────────────────────────────────────────────────────────
# build_summary (async, with HeadlineGenerator stub)
# ─────────────────────────────────────────────────────────────────────────────
class _StubHeadlineGenerator:
    """Lightweight stub — no real LLM call."""

    def __init__(self, headline: str | None):
        self._headline = headline

    async def generate(self, status, top, indeterminate_count):
        return self._headline


@pytest.mark.asyncio
async def test_build_summary_uses_llm_headline_when_valid():
    values = [make_value(severity="moderate", direction="high")]
    stub = _StubHeadlineGenerator(
        headline="A few results stand out and may need follow-up with your clinician."
    )
    s = await build_summary(values, headline_gen=stub)
    assert s.headline.startswith("A few results stand out")


@pytest.mark.asyncio
async def test_build_summary_falls_back_when_llm_returns_none():
    values = [make_value(severity="critical", direction="high")]
    stub = _StubHeadlineGenerator(headline=None)
    s = await build_summary(values, headline_gen=stub)
    # PR #6 calibrated tone: less alarmist than "need attention".
    assert s.headline == (
        "A few results stand out and may need follow-up with your clinician."
    )


@pytest.mark.asyncio
async def test_build_summary_skips_llm_for_green():
    values = [make_value(severity="normal")]
    stub = _StubHeadlineGenerator(
        headline="should-not-be-used; LLM is skipped on green."
    )
    s = await build_summary(values, headline_gen=stub)
    assert s.overall_status == "green"
    assert s.headline == "Most results are within expected range."


@pytest.mark.asyncio
async def test_build_summary_works_without_generator():
    values = [make_value(severity="moderate", direction="high")]
    s = await build_summary(values, headline_gen=None)
    # PR #6 calibrated tone: monitoring/follow-up framing for orange status.
    assert s.headline == (
        "Most results are normal; a few are worth follow-up or monitoring."
    )


# ─────────────────────────────────────────────────────────────────────────────
# PR #6 calibration: low-clinical-impact filter + alarmist denylist
# ─────────────────────────────────────────────────────────────────────────────
class TestClinicalPriorityFilter:
    def test_basophils_excluded_from_top_findings(self):
        values = [
            make_value(name="Basophils (BA SO) %", severity="moderate", direction="low"),
            make_value(name="LDL Cholesterol", severity="mild", direction="high"),
            make_value(name="25-OH Vitamin D", severity="mild", direction="low"),
        ]
        s = build_summary_sync(values)
        names = [f.test_name for f in s.top_findings]
        # Basophils filtered; LDL and Vit D survive
        assert "Basophils (BA SO) %" not in names
        assert "LDL Cholesterol" in names
        assert "25-OH Vitamin D" in names

    def test_pdw_pct_nrbc_excluded(self):
        values = [
            make_value(name="PDW", severity="moderate", direction="high"),
            make_value(name="Plateletcrit", severity="moderate", direction="low"),
            make_value(name="NRBC", severity="moderate", direction="high"),
            make_value(name="LDL", severity="mild", direction="high"),
        ]
        s = build_summary_sync(values)
        names = [f.test_name for f in s.top_findings]
        assert names == ["LDL"]

    def test_fallback_keeps_findings_when_filter_empties_list(self):
        # Only low-impact findings → can't leave hero empty
        values = [
            make_value(name="Basophils (BA SO) %", severity="moderate", direction="low"),
            make_value(name="MPV", severity="mild", direction="high"),
        ]
        s = build_summary_sync(values)
        # Both should survive because filter would leave empty list otherwise
        assert len(s.top_findings) == 2


class TestAlarmistDenylist:
    def _top(self, *names):
        return [type("F", (), {"test_name": n})() for n in names]

    def test_rejects_clinical_attention(self):
        text = "These results need clinical attention from your provider soon."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is not None
        assert "alarmist" in out

    def test_rejects_medically_concerning(self):
        text = "Several findings are medically concerning; review now and follow up."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is not None
        assert "alarmist" in out

    def test_rejects_urgent(self):
        text = "Urgent review needed for several lab results listed in this report monitor."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is not None
        assert "alarmist" in out

    def test_accepts_calm_phrasing(self):
        text = "A few results are worth follow-up with your clinician at a routine visit."
        out = _validate_headline(text, "orange", self._top("LDL"))
        assert out is None, out


class TestNextStepDetailed:
    """Phase 6 — templated next-step sentence naming top-finding tests."""

    def test_green_has_no_detailed_next_step(self):
        values = [make_value(severity="normal") for _ in range(3)]
        s = build_summary_sync(values)
        assert s.next_step_detailed is None

    def test_yellow_uses_routine_visit_copy_with_one_test(self):
        values = [make_value(name="LDL", severity="mild", direction="high")]
        s = build_summary_sync(values)
        assert s.next_step_detailed == "At your next routine visit, ask about LDL."

    def test_yellow_two_tests_uses_and_joiner(self):
        values = [
            make_value(name="LDL", severity="mild", direction="high"),
            make_value(name="Vitamin D", severity="mild", direction="low"),
        ]
        s = build_summary_sync(values)
        assert s.next_step_detailed == (
            "At your next routine visit, ask about LDL and Vitamin D."
        )

    def test_yellow_three_tests_uses_oxford_comma(self):
        values = [
            make_value(name="LDL", severity="mild", direction="high"),
            make_value(name="Vitamin D", severity="mild", direction="low"),
            make_value(name="eGFR", severity="mild", direction="low"),
        ]
        s = build_summary_sync(values)
        # All three mild → top_findings ranked by deviation; exact order is
        # implementation detail, but all three names must appear with
        # Oxford-comma join.
        assert s.next_step_detailed is not None
        assert s.next_step_detailed.startswith("At your next routine visit, ask about ")
        assert s.next_step_detailed.endswith(".")
        assert ", and " in s.next_step_detailed
        for name in ("LDL", "Vitamin D", "eGFR"):
            assert name in s.next_step_detailed

    def test_red_uses_doctor_copy(self):
        values = [make_value(name="Potassium", severity="critical", direction="high")]
        s = build_summary_sync(values)
        assert s.next_step_detailed == "Talk to a doctor about Potassium."

    def test_verbose_name_is_shortened(self):
        # Raw extracted names sometimes carry parentheticals / commas — we
        # strip those for prose so the sentence reads naturally.
        values = [
            make_value(
                name="Cholesterol, Low-Density Lipoprotein (LDL-C)",
                severity="mild",
                direction="high",
            )
        ]
        s = build_summary_sync(values)
        assert s.next_step_detailed == (
            "At your next routine visit, ask about Cholesterol."
        )
