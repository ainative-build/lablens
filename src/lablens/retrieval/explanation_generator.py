"""Qwen-based explanation generation for patient-facing reports.

LLM generates text; it does NOT make clinical decisions.
Explanations are grounded in evidence from the interpretation engine.
"""

import asyncio
import json
import logging
from functools import partial

from lablens.config import Settings
from lablens.interpretation.models import InterpretedReport
from lablens.retrieval.context_assembler import ContextAssembler
from lablens.retrieval.explanation_prompts import (
    DISCLAIMER,
    EXPLANATION_SYSTEM_PROMPT,
    EXPLANATION_USER_TEMPLATE,
)
from lablens.retrieval.models import ExplanationResult, FinalReport

logger = logging.getLogger(__name__)


class ExplanationGenerator:
    """Generate patient-friendly explanations using Qwen."""

    def __init__(self, settings: Settings, assembler: ContextAssembler):
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_chat_model
        self.assembler = assembler

    async def generate_report(
        self, interpreted: InterpretedReport, language: str = "en"
    ) -> FinalReport:
        """Generate patient-facing explanations for abnormal results."""
        abnormal = [v for v in interpreted.values if v.direction != "in-range"]
        explanations = []

        if abnormal:
            # Enrich with context
            contexts = {}
            for v in abnormal:
                ctx = await self.assembler.enrich(v.test_name, v.loinc_code)
                contexts[v.test_name] = ctx

            # Build prompt
            results_json = json.dumps(
                [v.evidence_trace for v in abnormal], indent=2, default=str
            )
            context_json = json.dumps(
                {
                    name: {
                        "related_analytes": ctx.graph.related_analytes,
                        "conditions": ctx.graph.condition_associations,
                        "follow_ups": ctx.graph.follow_up_tests,
                    }
                    for name, ctx in contexts.items()
                },
                indent=2,
            )
            snippets = "\n".join(
                f"- {s['text'][:300]}"
                for ctx in contexts.values()
                for s in ctx.vector.education_snippets
            )

            user_prompt = EXPLANATION_USER_TEMPLATE.format(
                language=language,
                results_json=results_json,
                context_json=context_json,
                education_snippets=snippets or "None available",
            )

            try:
                from dashscope import Generation

                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(
                    None,
                    partial(
                        Generation.call,
                        model=self.model,
                        messages=[
                            {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        api_key=self.api_key,
                        result_format="message",
                    ),
                )
                raw = resp.output.choices[0].message.content
                explanations = self._parse_explanations(raw, language)
                # Fallback if LLM returned valid response but parsing produced nothing
                if not explanations and abnormal:
                    logger.warning("LLM returned unparseable explanations, using templates")
                    explanations = self._fallback_explanations(abnormal, language)
            except Exception as e:
                logger.error("Explanation generation failed: %s", e)
                explanations = self._fallback_explanations(abnormal, language)

        return FinalReport(
            interpreted_values=interpreted.values,
            explanations=explanations,
            panels=interpreted.panels,
            coverage_score=interpreted.coverage_score,
            disclaimer=DISCLAIMER.get(language, DISCLAIMER["en"]),
            language=language,
        )

    @staticmethod
    def _parse_explanations(raw: str, language: str) -> list[ExplanationResult]:
        """Parse LLM JSON response into ExplanationResult list."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            items = json.loads(raw)
            return [
                ExplanationResult(
                    test_name=item.get("test_name", "Unknown"),
                    summary=item.get("summary", ""),
                    what_it_means=item.get("what_it_means", ""),
                    next_steps=item.get("next_steps", ""),
                    language=language,
                    sources=item.get("sources", []),
                )
                for item in items
            ]
        except json.JSONDecodeError:
            logger.error("Failed to parse explanation JSON: %s", raw[:200])
            return []

    @staticmethod
    def _fallback_explanations(abnormal, language: str) -> list[ExplanationResult]:
        """Template-based fallback when LLM fails."""
        return [
            ExplanationResult(
                test_name=v.test_name,
                summary=f"{v.test_name} is {v.direction} (value: {v.value} {v.unit})",
                what_it_means="Explanation unavailable due to a processing error.",
                next_steps="Please consult your healthcare provider.",
                language=language,
                sources=[],
            )
            for v in abnormal
        ]
