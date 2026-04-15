"""Qwen-OCR extraction via DashScope multimodal API.

Converts PDF pages to images, sends to qwen-vl-ocr-latest with structured
prompts, parses JSON responses into LabReport. Suspicious pages get a
targeted retry with Qwen3-VL document parsing for better layout handling.
"""

import asyncio
import json
import logging
from functools import partial

from lablens.config import Settings
from lablens.extraction.extraction_prompts import (
    EXTRACTION_PROMPTS,
    EXTRACTION_USER_PROMPT,
    REPARSE_SYSTEM_PROMPT,
    REPARSE_USER_PROMPT,
)
from lablens.extraction.ocr_range_preprocessor import (
    fix_range_fields,
    is_page_suspicious,
    validate_range_plausibility,
)
from lablens.extraction.pdf_processor import PDFProcessor
from lablens.extraction.response_parser import deduplicate_values, filter_noise_values
from lablens.models.lab_report import LabReport, LabValue

logger = logging.getLogger(__name__)


class OCRExtractor:
    """Extract lab values from PDF using Qwen vision models."""

    def __init__(self, settings: Settings):
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_ocr_model
        self.reparse_model = "qwen-vl-max-latest"

    async def extract_from_pdf(
        self, pdf_bytes: bytes, language: str = "auto"
    ) -> LabReport:
        """Full extraction pipeline: PDF → images → OCR → LabReport."""
        PDFProcessor.validate_pdf(pdf_bytes)
        images = PDFProcessor.pdf_to_base64_images(pdf_bytes)

        all_values: list[LabValue] = []
        metadata: dict = {}

        for i, img_b64 in enumerate(images):
            page_num = i + 1
            page_result = await self._extract_page(img_b64, language, page_num=page_num)
            if not page_result:
                continue

            # Capture metadata from first page
            if not metadata.get("source_language"):
                metadata["source_language"] = page_result.get("source_language", "en")
                metadata["lab_name"] = page_result.get("lab_name")
                metadata["report_date"] = page_result.get("report_date")
                metadata["patient_id"] = page_result.get("patient_id")

            raw_values = page_result.get("values", [])

            # Check if page needs re-parsing with Qwen3-VL
            if is_page_suspicious(raw_values):
                logger.info(
                    "Page %d flagged as suspicious — retrying with %s",
                    page_num, self.reparse_model,
                )
                reparse_result = await self._reparse_page(
                    img_b64, language, page_num
                )
                if reparse_result:
                    reparse_values = reparse_result.get("values", [])
                    if self._reparse_is_better(raw_values, reparse_values):
                        logger.info(
                            "Reparse improved page %d: %d→%d values",
                            page_num, len(raw_values), len(reparse_values),
                        )
                        raw_values = reparse_values

            for v in raw_values:
                try:
                    v = fix_range_fields(v)
                    v = validate_range_plausibility(v)
                    all_values.append(LabValue(**v))
                except Exception as e:
                    logger.warning("Skipping invalid value on page %d: %s", page_num, e)

        all_values = filter_noise_values(all_values)
        all_values = deduplicate_values(all_values)

        return LabReport(
            source_language=metadata.get("source_language", "en"),
            lab_name=metadata.get("lab_name"),
            report_date=metadata.get("report_date"),
            patient_id=metadata.get("patient_id"),
            values=all_values,
            page_count=len(images),
        )

    async def _extract_page(
        self, img_b64: str, language: str, page_num: int
    ) -> dict | None:
        """Extract lab values from a single page image using primary OCR model."""
        system_prompt = EXTRACTION_PROMPTS.get(language, EXTRACTION_PROMPTS["auto"])
        messages = [
            {"role": "system", "content": [{"text": system_prompt}]},
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/png;base64,{img_b64}"},
                    {"text": EXTRACTION_USER_PROMPT},
                ],
            },
        ]
        try:
            raw = await self._call_dashscope_ocr(self.model, messages)
            return self._parse_json_response(raw)
        except Exception as e:
            logger.warning("OCR failed on page %d: %s", page_num, e)
            return None

    async def _reparse_page(
        self, img_b64: str, language: str, page_num: int
    ) -> dict | None:
        """Re-parse a suspicious page using Qwen3-VL with document-parsing prompt.

        Qwen3-VL handles complex layouts, footnote-style ranges, and mixed
        table formats better than the OCR-specialized model.
        """
        messages = [
            {"role": "system", "content": [{"text": REPARSE_SYSTEM_PROMPT}]},
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/png;base64,{img_b64}"},
                    {"text": REPARSE_USER_PROMPT},
                ],
            },
        ]
        try:
            raw = await self._call_dashscope_ocr(self.reparse_model, messages)
            return self._parse_json_response(raw)
        except Exception as e:
            logger.warning(
                "Qwen3-VL reparse failed on page %d: %s", page_num, e
            )
            return None

    @staticmethod
    def _reparse_is_better(
        original: list[dict], reparsed: list[dict]
    ) -> bool:
        """Compare original vs reparsed extraction quality.

        Reparse wins if it has more values with units and ranges.
        """
        if not reparsed:
            return False

        def quality_score(values: list[dict]) -> float:
            if not values:
                return 0
            total = len(values)
            has_unit = sum(1 for v in values if v.get("unit"))
            has_range = sum(
                1 for v in values
                if v.get("reference_range_low") is not None
                or v.get("reference_range_high") is not None
            )
            return total + (has_unit / total) * total + (has_range / total) * total

        return quality_score(reparsed) > quality_score(original)

    async def _call_dashscope_ocr(self, model: str, messages: list) -> str:
        """Call DashScope multimodal API in executor to avoid blocking event loop."""
        from dashscope import MultiModalConversation

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            partial(
                MultiModalConversation.call,
                model=model,
                messages=messages,
                api_key=self.api_key,
            ),
        )
        return resp.output.choices[0].message.content[0]["text"]

    @staticmethod
    def _parse_json_response(raw: str) -> dict | None:
        """Extract JSON from LLM response, handling markdown fences."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Failed to parse extraction JSON: %s", raw[:200])
            return None
