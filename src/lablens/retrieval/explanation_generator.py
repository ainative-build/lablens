"""Qwen-based explanation generation for patient-facing reports.

Section-aware: dispatches to specialized prompts for HPLC diabetes
results, ctDNA screening results, and standard lab values.
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
    HPLC_EXPLANATION_SYSTEM_PROMPT,
    HPLC_USER_TEMPLATE,
    SCREENING_EXPLANATION_SYSTEM_PROMPT,
    SCREENING_USER_TEMPLATE,
)
from lablens.retrieval.models import ExplanationResult, FinalReport

logger = logging.getLogger(__name__)


class ExplanationGenerator:
    """Generate patient-friendly explanations using Qwen, section-aware."""

    def __init__(self, settings: Settings, assembler: ContextAssembler):
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_chat_model
        self.assembler = assembler

    async def generate_report(
        self,
        interpreted: InterpretedReport,
        language: str = "en",
        hplc_blocks: list | None = None,
        screening_results: list | None = None,
    ) -> FinalReport:
        """Generate section-aware patient-facing explanations."""
        explanations: list[ExplanationResult] = []

        # Standard abnormal values
        standard_abnormal = [
            v
            for v in interpreted.values
            if v.direction not in ("in-range", "indeterminate")
        ]
        if standard_abnormal:
            explanations.extend(
                await self._explain_standard(standard_abnormal, language)
            )

        # HPLC-specific explanations
        if hplc_blocks:
            explanations.extend(
                await self._explain_hplc(hplc_blocks, language)
            )

        # Screening-specific explanations
        if screening_results:
            explanations.extend(
                await self._explain_screening(screening_results, language)
            )

        return FinalReport(
            interpreted_values=interpreted.values,
            explanations=explanations,
            panels=interpreted.panels,
            coverage_score=interpreted.coverage_score,
            disclaimer=DISCLAIMER.get(language, DISCLAIMER["en"]),
            language=language,
        )

    async def _explain_standard(
        self, abnormal: list, language: str
    ) -> list[ExplanationResult]:
        """Standard lab value explanations (existing flow)."""
        contexts = {}
        for v in abnormal:
            section = getattr(v, "section_type", "standard_lab_table") or "standard_lab_table"
            ctx = await self.assembler.enrich(
                v.test_name, v.loinc_code, section_type=section
            )
            contexts[v.test_name] = ctx

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

        return await self._call_llm(
            EXPLANATION_SYSTEM_PROMPT, user_prompt, abnormal, language
        )

    async def _explain_hplc(
        self, hplc_blocks: list, language: str
    ) -> list[ExplanationResult]:
        """HPLC-specific explanation with diabetes context."""
        explanations = []
        for block in hplc_blocks:
            # Build context for HbA1c
            ctx = await self.assembler.enrich(
                "HbA1c", None, section_type="hplc_diabetes_block"
            )

            results_data = []
            for attr in ("ngsp", "ifcc", "eag"):
                analyte = getattr(block, attr, None)
                if analyte and analyte.value is not None:
                    results_data.append({
                        "test_name": analyte.test_name,
                        "value": analyte.value,
                        "unit": analyte.unit,
                    })

            snippets = "\n".join(
                f"- {s['text'][:300]}"
                for s in ctx.vector.education_snippets
            )
            user_prompt = HPLC_USER_TEMPLATE.format(
                language=language,
                results_json=json.dumps(results_data, indent=2),
                diabetes_category=block.diabetes_category.value,
                context_json=json.dumps({
                    "related_analytes": ctx.graph.related_analytes,
                    "conditions": ctx.graph.condition_associations,
                    "follow_ups": ctx.graph.follow_up_tests,
                }, indent=2),
                education_snippets=snippets or "None available",
            )

            result = await self._call_llm(
                HPLC_EXPLANATION_SYSTEM_PROMPT, user_prompt, [], language
            )
            if result:
                explanations.extend(result)
            else:
                # Fallback for HPLC
                explanations.append(ExplanationResult(
                    test_name="HbA1c",
                    summary=f"HbA1c result: {block.diabetes_category.value}",
                    what_it_means=(
                        "Your HbA1c measures average blood sugar over 2-3 months. "
                        "Please discuss the result with your healthcare provider."
                    ),
                    next_steps="Follow up with your doctor for guidance.",
                    language=language,
                    is_fallback=True,
                ))
        return explanations

    async def _explain_screening(
        self, screening_results: list, language: str
    ) -> list[ExplanationResult]:
        """Screening-specific explanation with caveat framing."""
        explanations = []
        for sr in screening_results:
            ctx = await self.assembler.enrich(
                sr.test_type, None, section_type="screening_attachment"
            )
            screening_data = {
                "test_type": sr.test_type,
                "result_status": sr.result_status.value,
                "signal_origin": sr.signal_origin,
                "organs_screened": sr.organs_screened,
                "limitations": sr.limitations,
                "followup_recommendation": sr.followup_recommendation,
            }
            snippets = "\n".join(
                f"- {s['text'][:300]}"
                for s in ctx.vector.education_snippets
            )
            user_prompt = SCREENING_USER_TEMPLATE.format(
                language=language,
                screening_json=json.dumps(screening_data, indent=2),
                context_json=json.dumps({
                    "related_analytes": ctx.graph.related_analytes,
                    "follow_ups": ctx.graph.follow_up_tests,
                }, indent=2),
                education_snippets=snippets or "None available",
            )

            result = await self._call_llm(
                SCREENING_EXPLANATION_SYSTEM_PROMPT, user_prompt, [], language
            )
            if result:
                explanations.extend(result)
            else:
                status_text = sr.result_status.value.replace("_", " ")
                explanations.append(ExplanationResult(
                    test_name=sr.test_type,
                    summary=f"{sr.test_type} screening: {status_text}",
                    what_it_means=(
                        "This screening test looks for early signs of cancer. "
                        "Please discuss the full results with your doctor."
                    ),
                    next_steps="Continue routine screening as recommended.",
                    language=language,
                    is_fallback=True,
                ))
        return explanations

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_values: list,
        language: str,
    ) -> list[ExplanationResult]:
        """Call LLM with given prompts, parse response, fallback on error.

        Resilience layers:
        1. API key validation — skip call if key is missing
        2. Response null-guard — check resp.output before accessing .choices
        3. Diagnostic logging — log resp.code/message for API-side errors
        4. Graceful fallback — always return usable ExplanationResult list
        """
        if not self.api_key:
            logger.warning(
                "Explanation LLM skipped: no API key configured "
                "(set LABLENS_DASHSCOPE_API_KEY)"
            )
            if fallback_values:
                return self._fallback_explanations(fallback_values, language)
            return []

        try:
            from dashscope import Generation

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                partial(
                    Generation.call,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    api_key=self.api_key,
                    result_format="message",
                ),
            )

            # Null-guard: DashScope returns output=None on auth/model errors
            if not resp or not getattr(resp, "output", None):
                code = getattr(resp, "code", "unknown")
                msg = getattr(resp, "message", "no details")
                logger.warning(
                    "Explanation LLM returned empty output "
                    "(code=%s, message=%s, model=%s)",
                    code, msg, self.model,
                )
                if fallback_values:
                    return self._fallback_explanations(fallback_values, language)
                return []

            choices = getattr(resp.output, "choices", None)
            if not choices:
                logger.warning(
                    "Explanation LLM returned no choices (model=%s)",
                    self.model,
                )
                if fallback_values:
                    return self._fallback_explanations(fallback_values, language)
                return []

            raw = choices[0].message.content
            explanations = self._parse_explanations(raw, language)
            if not explanations and fallback_values:
                logger.warning(
                    "LLM returned unparseable explanations, using templates"
                )
                return self._fallback_explanations(fallback_values, language)
            return explanations

        except Exception as e:
            logger.error("Explanation generation failed: %s", e)
            if fallback_values:
                return self._fallback_explanations(fallback_values, language)
            return []

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
    def _fallback_explanations(
        abnormal: list, language: str
    ) -> list[ExplanationResult]:
        """Template-based fallback when LLM fails."""
        return [
            ExplanationResult(
                test_name=v.test_name,
                summary=(
                    f"{v.test_name} is {v.direction} "
                    f"(value: {v.value} {v.unit})"
                ),
                what_it_means=(
                    "Explanation unavailable due to a processing error."
                ),
                next_steps="Please consult your healthcare provider.",
                language=language,
                sources=[],
                is_fallback=True,
            )
            for v in abnormal
        ]
