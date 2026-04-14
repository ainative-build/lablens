"""Tests for retrieval and explanation modules."""

import pytest

from lablens.retrieval.context_assembler import ContextAssembler
from lablens.retrieval.explanation_generator import ExplanationGenerator
from lablens.retrieval.graph_retriever import NullGraphRetriever
from lablens.retrieval.models import (
    EnrichedContext,
    ExplanationResult,
    FinalReport,
    GraphContext,
    VectorContext,
)
from lablens.retrieval.vector_retriever import NullVectorRetriever
from lablens.retrieval.explanation_prompts import DISCLAIMER


# --- Null retrievers ---


@pytest.mark.asyncio
async def test_null_graph_retriever():
    retriever = NullGraphRetriever()
    ctx = await retriever.get_context("2345-7")
    assert isinstance(ctx, GraphContext)
    assert len(ctx.related_analytes) == 0


@pytest.mark.asyncio
async def test_null_vector_retriever():
    retriever = NullVectorRetriever()
    ctx = await retriever.get_education("Glucose", "2345-7")
    assert isinstance(ctx, VectorContext)
    assert len(ctx.education_snippets) == 0


# --- Context assembler ---


@pytest.mark.asyncio
async def test_context_assembler_with_null_retrievers():
    assembler = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    ctx = await assembler.enrich("Glucose", "2345-7")
    assert isinstance(ctx, EnrichedContext)
    assert isinstance(ctx.graph, GraphContext)
    assert isinstance(ctx.vector, VectorContext)


@pytest.mark.asyncio
async def test_context_assembler_no_loinc():
    assembler = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
    ctx = await assembler.enrich("Unknown Test", None)
    assert isinstance(ctx, EnrichedContext)


# --- Explanation parsing ---


def test_parse_explanations_valid():
    raw = """```json
[{"test_name": "Glucose", "summary": "High blood sugar", "what_it_means": "Your glucose is elevated.", "next_steps": "Consult your doctor.", "sources": ["medlineplus"]}]
```"""
    results = ExplanationGenerator._parse_explanations(raw, "en")
    assert len(results) == 1
    assert results[0].test_name == "Glucose"
    assert results[0].summary == "High blood sugar"


def test_parse_explanations_invalid():
    raw = "This is not JSON"
    results = ExplanationGenerator._parse_explanations(raw, "en")
    assert len(results) == 0


def test_parse_explanations_plain_json():
    raw = '[{"test_name": "WBC", "summary": "Low WBC", "what_it_means": "Details", "next_steps": "Steps", "sources": []}]'
    results = ExplanationGenerator._parse_explanations(raw, "en")
    assert len(results) == 1
    assert results[0].test_name == "WBC"


# --- Fallback explanations ---


def test_fallback_explanations():
    from lablens.interpretation.models import InterpretedResult

    abnormal = [
        InterpretedResult(
            test_name="Glucose", loinc_code="2345-7",
            value=250, unit="mg/dL", direction="high",
        )
    ]
    results = ExplanationGenerator._fallback_explanations(abnormal, "en")
    assert len(results) == 1
    assert "Glucose" in results[0].summary
    assert "high" in results[0].summary


# --- Disclaimer ---


def test_disclaimers_all_languages():
    assert "en" in DISCLAIMER
    assert "fr" in DISCLAIMER
    assert "ar" in DISCLAIMER
    assert "vn" in DISCLAIMER
    for lang, text in DISCLAIMER.items():
        assert len(text) > 20


# --- Models ---


def test_graph_context_defaults():
    ctx = GraphContext()
    assert ctx.related_analytes == []
    assert ctx.condition_associations == []
    assert ctx.follow_up_tests == []


def test_explanation_result():
    result = ExplanationResult(
        test_name="Glucose",
        summary="High blood sugar",
        what_it_means="Elevated glucose.",
        next_steps="See your doctor.",
        language="en",
    )
    assert result.test_name == "Glucose"
    assert result.sources == []


def test_final_report():
    report = FinalReport(
        interpreted_values=[],
        explanations=[],
        panels=[],
        coverage_score="0/0 analytes parsed, 0/0 abnormal explained",
        disclaimer=DISCLAIMER["en"],
        language="en",
    )
    assert report.language == "en"
