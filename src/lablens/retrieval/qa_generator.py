"""Q&A LLM call wrapper — Phase 3.

Single Qwen-Plus call per question.  JSON-mode preferred; on parse fail,
strip code-fences and retry parse (no LLM retry).  On 2nd parse fail →
caller's canned refusal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from functools import partial

from lablens.config import Settings
from lablens.retrieval.qa_prompts import (
    FEWSHOT_BLOCK,
    USER_TEMPLATE,
    get_system_prompt,
    render_history,
)

logger = logging.getLogger(__name__)


class QaGenerator:
    """Async Qwen-Plus wrapper for single-shot grounded Q&A."""

    def __init__(self, settings: Settings):
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_chat_model

    async def generate(
        self,
        compact_report: dict,
        question: str,
        history: list[dict],
        language: str,
    ) -> dict | None:
        """Call Qwen and return parsed JSON dict, or None on failure."""
        if not self.api_key:
            logger.warning("QaGenerator: no API key configured")
            return None

        compact_json = json.dumps(compact_report, ensure_ascii=False, default=str)
        system = get_system_prompt(language, compact_json)
        user = (
            FEWSHOT_BLOCK
            + "\n\n"
            + USER_TEMPLATE.format(
                history_block=render_history(history),
                question=question,
            )
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
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    api_key=self.api_key,
                    result_format="message",
                    response_format={"type": "json_object"},
                ),
            )
            if not resp or not getattr(resp, "output", None):
                logger.warning(
                    "QaGenerator empty resp (code=%s, msg=%s)",
                    getattr(resp, "code", "?"),
                    getattr(resp, "message", "?"),
                )
                return None
            choices = getattr(resp.output, "choices", None)
            if not choices:
                return None
            raw = choices[0].message.content
            return _parse_json(raw)
        except TypeError:
            # response_format may not be supported; retry without it.
            return await self._generate_no_json_mode(system, user)
        except Exception as e:
            logger.error("QaGenerator error: %s", e)
            return None

    async def _generate_no_json_mode(self, system: str, user: str) -> dict | None:
        """Fallback when DashScope SDK doesn't accept response_format."""
        try:
            from dashscope import Generation

            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                partial(
                    Generation.call,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    api_key=self.api_key,
                    result_format="message",
                ),
            )
            if not resp or not getattr(resp, "output", None):
                return None
            choices = getattr(resp.output, "choices", None)
            if not choices:
                return None
            raw = choices[0].message.content
            return _parse_json(raw)
        except Exception as e:
            logger.error("QaGenerator fallback error: %s", e)
            return None


def _parse_json(raw: str) -> dict | None:
    """Tolerant JSON parser — strips code-fences, attempts plain parse,
    then regex fallback for the {answer:...} shape."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        # Strip first ```... line and trailing ```
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Regex fallback: try to extract JSON object substring
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    return None
