"""Data models for retrieval and explanation output."""

from dataclasses import dataclass, field


@dataclass
class GraphContext:
    """Context retrieved from GDB graph."""

    related_analytes: list[dict] = field(default_factory=list)
    condition_associations: list[dict] = field(default_factory=list)
    follow_up_tests: list[str] = field(default_factory=list)


@dataclass
class VectorContext:
    """Context retrieved from DashVector."""

    education_snippets: list[dict] = field(default_factory=list)


@dataclass
class EnrichedContext:
    """Combined graph + vector context for a single analyte."""

    graph: GraphContext
    vector: VectorContext


@dataclass
class ExplanationResult:
    """Patient-friendly explanation for a single analyte."""

    test_name: str
    summary: str
    what_it_means: str
    next_steps: str
    language: str
    sources: list[str] = field(default_factory=list)
    is_fallback: bool = False  # True when LLM failed and template was used


@dataclass
class FinalReport:
    """Complete analysis report with explanations."""

    interpreted_values: list
    explanations: list[ExplanationResult]
    panels: list
    coverage_score: str
    disclaimer: str
    language: str

    @property
    def explanation_quality(self) -> dict:
        """Breakdown of explanation quality — real LLM vs fallback."""
        total = len(self.explanations)
        fallback = sum(1 for e in self.explanations if e.is_fallback)
        return {
            "total": total,
            "llm_generated": total - fallback,
            "fallback_used": fallback,
        }
