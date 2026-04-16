"""Tests for section-aware enrichment (Phase 5).

Validates context assembler routing, explanation generator dispatch,
and prompt templates for HPLC, screening, and standard sections.
"""

import json
import pytest

from lablens.retrieval.context_assembler import (
    ContextAssembler,
    _VECTOR_QUERY_OVERRIDES,
)
from lablens.retrieval.explanation_generator import ExplanationGenerator
from lablens.retrieval.explanation_prompts import (
    DISCLAIMER,
    EXPLANATION_SYSTEM_PROMPT,
    HPLC_EXPLANATION_SYSTEM_PROMPT,
    HPLC_USER_TEMPLATE,
    SCREENING_EXPLANATION_SYSTEM_PROMPT,
    SCREENING_USER_TEMPLATE,
)
from lablens.retrieval.graph_retriever import NullGraphRetriever
from lablens.retrieval.models import (
    EnrichedContext,
    ExplanationResult,
    FinalReport,
    GraphContext,
    VectorContext,
)
from lablens.retrieval.vector_retriever import NullVectorRetriever


# --- Section-aware null retrievers ---


@pytest.mark.asyncio
async def test_null_graph_glycemic_context():
    r = NullGraphRetriever()
    ctx = await r.get_glycemic_context("4548-4")
    assert isinstance(ctx, GraphContext)
    assert ctx.related_analytes == []


@pytest.mark.asyncio
async def test_null_graph_screening_context():
    r = NullGraphRetriever()
    ctx = await r.get_screening_context("ctdna-1")
    assert isinstance(ctx, GraphContext)
    assert ctx.follow_up_tests == []


@pytest.mark.asyncio
async def test_null_vector_with_query_override():
    r = NullVectorRetriever()
    ctx = await r.get_education("HbA1c", None, query_override="diabetes monitoring")
    assert isinstance(ctx, VectorContext)
    assert ctx.education_snippets == []


# --- Vector query overrides ---


def test_vector_query_overrides_hplc():
    q = _VECTOR_QUERY_OVERRIDES.get("hplc_diabetes_block")
    assert q is not None
    assert "HbA1c" in q
    assert "diabetes" in q


def test_vector_query_overrides_screening():
    q = _VECTOR_QUERY_OVERRIDES.get("screening_attachment")
    assert q is not None
    assert "ctDNA" in q
    assert "screening" in q


def test_vector_query_overrides_standard_absent():
    assert "standard_lab_table" not in _VECTOR_QUERY_OVERRIDES


# --- Context assembler section routing ---


@pytest.mark.asyncio
async def test_assembler_standard_section():
    a = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    ctx = await a.enrich("Glucose", "2345-7", section_type="standard_lab_table")
    assert isinstance(ctx, EnrichedContext)
    assert isinstance(ctx.graph, GraphContext)
    assert isinstance(ctx.vector, VectorContext)


@pytest.mark.asyncio
async def test_assembler_hplc_section():
    a = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    ctx = await a.enrich("HbA1c", None, section_type="hplc_diabetes_block")
    assert isinstance(ctx, EnrichedContext)


@pytest.mark.asyncio
async def test_assembler_screening_section():
    a = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    ctx = await a.enrich("ctDNA", None, section_type="screening_attachment")
    assert isinstance(ctx, EnrichedContext)


@pytest.mark.asyncio
async def test_assembler_no_loinc_returns_empty_graph():
    """When loinc_code is None, graph should be empty regardless of section."""
    a = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    ctx = await a.enrich("Unknown", None, section_type="hplc_diabetes_block")
    assert ctx.graph.related_analytes == []


# --- Explanation prompts ---


def test_hplc_prompt_contains_ada_categories():
    assert "5.7%" in HPLC_EXPLANATION_SYSTEM_PROMPT
    assert "6.5%" in HPLC_EXPLANATION_SYSTEM_PROMPT
    assert "ADA" in HPLC_EXPLANATION_SYSTEM_PROMPT


def test_hplc_user_template_placeholders():
    placeholders = ["language", "results_json", "diabetes_category",
                     "context_json", "education_snippets"]
    for p in placeholders:
        assert f"{{{p}}}" in HPLC_USER_TEMPLATE


def test_screening_prompt_contains_key_rules():
    assert "screening" in SCREENING_EXPLANATION_SYSTEM_PROMPT.lower()
    assert "Not Detected" in SCREENING_EXPLANATION_SYSTEM_PROMPT


def test_screening_user_template_placeholders():
    placeholders = ["language", "screening_json", "context_json",
                     "education_snippets"]
    for p in placeholders:
        assert f"{{{p}}}" in SCREENING_USER_TEMPLATE


# --- ExplanationGenerator parse ---


def test_parse_hplc_explanation():
    raw = json.dumps([{
        "test_name": "HbA1c",
        "summary": "HbA1c is 6.0%",
        "what_it_means": "Pre-diabetic range.",
        "next_steps": "Follow up in 3 months.",
        "sources": ["ADA"],
    }])
    results = ExplanationGenerator._parse_explanations(raw, "en")
    assert len(results) == 1
    assert results[0].test_name == "HbA1c"
    assert "6.0%" in results[0].summary


def test_parse_screening_explanation():
    raw = json.dumps([{
        "test_name": "ctDNA Screening",
        "summary": "Not detected",
        "what_it_means": "No cancer signal found but does not guarantee absence.",
        "next_steps": "Continue routine screening.",
        "sources": [],
    }])
    results = ExplanationGenerator._parse_explanations(raw, "en")
    assert len(results) == 1
    assert results[0].test_name == "ctDNA Screening"


# --- Explanation fallback for HPLC/screening ---


def test_hplc_fallback_structure():
    """Verify HPLC fallback explanation has correct fields."""
    result = ExplanationResult(
        test_name="HbA1c",
        summary="HbA1c result: prediabetes",
        what_it_means=(
            "Your HbA1c measures average blood sugar over 2-3 months. "
            "Please discuss the result with your healthcare provider."
        ),
        next_steps="Follow up with your doctor for guidance.",
        language="en",
    )
    assert result.test_name == "HbA1c"
    assert "blood sugar" in result.what_it_means


def test_screening_fallback_structure():
    """Verify screening fallback explanation has correct fields."""
    result = ExplanationResult(
        test_name="SPOT-MAS ctDNA",
        summary="SPOT-MAS ctDNA screening: not detected",
        what_it_means=(
            "This screening test looks for early signs of cancer. "
            "Please discuss the full results with your doctor."
        ),
        next_steps="Continue routine screening as recommended.",
        language="en",
    )
    assert result.test_name == "SPOT-MAS ctDNA"
    assert "screening" in result.what_it_means


# --- FinalReport with screening ---


def test_final_report_with_screening_disclaimer():
    report = FinalReport(
        interpreted_values=[],
        explanations=[],
        panels=[],
        coverage_score="0/0",
        disclaimer=DISCLAIMER["en"],
        language="en",
    )
    assert "educational" in report.disclaimer.lower()


# --- generate_report section dispatch (dry run with null LLM) ---


@pytest.mark.asyncio
async def test_generate_report_no_abnormals_no_blocks():
    """Empty inputs should return a report with no explanations."""
    from unittest.mock import MagicMock

    from lablens.interpretation.models import InterpretedReport

    settings = MagicMock()
    settings.dashscope_api_key = "test"
    settings.dashscope_chat_model = "qwen3.5-plus"
    assembler = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    gen = ExplanationGenerator(settings, assembler)

    interpreted = InterpretedReport(
        values=[], panels=[], total_parsed=0, total_abnormal=0,
    )
    final = await gen.generate_report(interpreted, "en")
    assert isinstance(final, FinalReport)
    assert final.explanations == []


@pytest.mark.asyncio
async def test_generate_report_calls_hplc_path():
    """HPLC blocks trigger _explain_hplc without crashing on null LLM."""
    from dataclasses import dataclass
    from enum import Enum
    from unittest.mock import MagicMock

    from lablens.interpretation.models import InterpretedReport

    class _Cat(Enum):
        normal = "normal"

    @dataclass
    class _Analyte:
        test_name: str = "HbA1c (NGSP)"
        value: float = 5.2
        unit: str = "%"

    @dataclass
    class _HPLCBlock:
        ngsp: _Analyte = None
        ifcc: _Analyte = None
        eag: _Analyte = None
        diabetes_category: _Cat = _Cat.normal
        cross_check_passed: bool = True

    settings = MagicMock()
    settings.dashscope_api_key = "test"
    settings.dashscope_chat_model = "qwen3.5-plus"
    assembler = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    gen = ExplanationGenerator(settings, assembler)

    interpreted = InterpretedReport(
        values=[], panels=[], total_parsed=0, total_abnormal=0,
    )
    block = _HPLCBlock(ngsp=_Analyte())
    # LLM call will fail → fallback path
    final = await gen.generate_report(
        interpreted, "en", hplc_blocks=[block]
    )
    assert isinstance(final, FinalReport)
    # Should have fallback explanation for HbA1c
    assert len(final.explanations) >= 1
    assert any("HbA1c" in e.test_name for e in final.explanations)


@pytest.mark.asyncio
async def test_generate_report_calls_screening_path():
    """Screening results trigger _explain_screening with fallback."""
    from dataclasses import dataclass
    from enum import Enum
    from unittest.mock import MagicMock

    from lablens.interpretation.models import InterpretedReport

    class _Status(Enum):
        not_detected = "not_detected"

    @dataclass
    class _Screening:
        test_type: str = "SPOT-MAS ctDNA"
        result_status: _Status = _Status.not_detected
        signal_origin: str = "cfDNA methylation"
        organs_screened: list = None
        limitations: list = None
        followup_recommendation: str = "Continue routine screening"

        def __post_init__(self):
            self.organs_screened = self.organs_screened or []
            self.limitations = self.limitations or []

    settings = MagicMock()
    settings.dashscope_api_key = "test"
    settings.dashscope_chat_model = "qwen3.5-plus"
    assembler = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    gen = ExplanationGenerator(settings, assembler)

    interpreted = InterpretedReport(
        values=[], panels=[], total_parsed=0, total_abnormal=0,
    )
    sr = _Screening()
    final = await gen.generate_report(
        interpreted, "en", screening_results=[sr]
    )
    assert isinstance(final, FinalReport)
    assert len(final.explanations) >= 1
    assert any("ctDNA" in e.test_name or "SPOT" in e.test_name
               for e in final.explanations)
