"""Report summary + topic-grouping Pydantic models.

LOCKED contract — frontend (Phase 2) and Q&A (Phase 3) both consume this.
See plans/260417-0010-summary-first-report-ux/plan.md for the contract.

Phase 1a delivers TopicGroup, TopFinding, ReportSummary, AnalysisResultPayload.
ReportSummary is included for the locked shape; it is populated in Phase 1b.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Severity domain — backend only emits {normal, mild, moderate, critical}.
# "high" is a direction, never a severity.
Status = Literal["green", "yellow", "orange", "red"]


class TopFinding(BaseModel):
    """One row in the summary's top-3 abnormal callouts."""

    test_name: str
    value: float | str
    unit: str | None = None
    direction: Literal["high", "low", "indeterminate"]
    severity: Literal["mild", "moderate", "critical"]
    is_panic: bool = False
    health_topic: str
    plain_language_key: str  # e.g. "direction.high" | "direction.low" | "direction.needs_review"


class ReportSummary(BaseModel):
    """Executive summary block (L1). Populated in Phase 1b."""

    overall_status: Status
    headline: str  # ≤25 words
    top_findings: list[TopFinding] = Field(default_factory=list)
    next_steps_key: Status
    indeterminate_count: int = 0
    uncertainty_note_key: str | None = None


class TopicGroup(BaseModel):
    """A health-topic bucket of results (L2)."""

    topic: str  # e.g. "blood_sugar"
    topic_label_key: str  # e.g. "topic.blood_sugar"
    status: Status
    summary: str  # ≤80 chars, e.g. "1 of 4 need attention" or "All normal (4)"
    abnormal_count: int = 0
    indeterminate_count: int = 0
    # PR #6 calibration v2: minor_count tracks low-clinical-impact tests
    # (Basophils, NRBC, PDW, etc.) that are technically abnormal but should
    # not inflate "worth follow-up" count. Card UI shows them as "Minor".
    minor_count: int = 0
    total_count: int = 0
    # results carry InterpretedResult dicts (vars(v)) — kept loose to avoid
    # round-tripping the dataclass through Pydantic.
    results: list[dict] = Field(default_factory=list)


class AnalysisResultPayload(BaseModel):
    """LOCKED top-level contract for /analyze response."""

    language: Literal["en", "vn", "fr", "ar"]
    summary: ReportSummary | None = None  # Populated in Phase 1b
    topic_groups: list[TopicGroup] = Field(default_factory=list)
    values: list[dict] = Field(default_factory=list)
    screening_results: list[dict] = Field(default_factory=list)
    explanations: list[dict] = Field(default_factory=list)
    panels: list[dict] = Field(default_factory=list)
    audit: dict = Field(default_factory=dict)
