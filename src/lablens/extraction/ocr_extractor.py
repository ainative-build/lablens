"""Qwen-OCR extraction via DashScope multimodal API.

Converts PDF pages to images, sends to Qwen-VL-OCR with structured prompts,
parses JSON responses into LabReport. Falls back to qwen-vl-max on failure.
"""

import json
import logging

from lablens.config import Settings
from lablens.extraction.extraction_prompts import (
    EXTRACTION_PROMPTS,
    EXTRACTION_USER_PROMPT,
)
from lablens.extraction.pdf_processor import PDFProcessor
from lablens.extraction.response_parser import deduplicate_values
from lablens.models.lab_report import LabReport, LabValue

logger = logging.getLogger(__name__)


class OCRExtractor:
    """Extract lab values from PDF using Qwen vision models."""

    def __init__(self, settings: Settings):
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_ocr_model
        self.fallback_model = "qwen-vl-max"

    async def extract_from_pdf(
        self, pdf_bytes: bytes, language: str = "auto"
    ) -> LabReport:
        """Full extraction pipeline: PDF → images → OCR → LabReport."""
        PDFProcessor.validate_pdf(pdf_bytes)
        images = PDFProcessor.pdf_to_base64_images(pdf_bytes)

        all_values: list[LabValue] = []
        metadata: dict = {}

        for i, img_b64 in enumerate(images):
            page_result = await self._extract_page(img_b64, language, page_num=i + 1)
            if not page_result:
                continue
            # Capture metadata from first page
            if not metadata.get("source_language"):
                metadata["source_language"] = page_result.get("source_language", "en")
                metadata["lab_name"] = page_result.get("lab_name")
                metadata["report_date"] = page_result.get("report_date")
                metadata["patient_id"] = page_result.get("patient_id")
            for v in page_result.get("values", []):
                try:
                    all_values.append(LabValue(**v))
                except Exception as e:
                    logger.warning("Skipping invalid value on page %d: %s", i + 1, e)

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
        """Extract lab values from a single page image."""
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
            from dashscope import MultiModalConversation

            resp = MultiModalConversation.call(
                model=self.model,
                messages=messages,
                api_key=self.api_key,
            )
            raw = resp.output.choices[0].message.content[0]["text"]
            return self._parse_json_response(raw)
        except Exception as e:
            logger.warning("OCR failed on page %d: %s. Trying fallback.", page_num, e)
            return await self._extract_page_fallback(img_b64, language, page_num)

    async def _extract_page_fallback(
        self, img_b64: str, language: str, page_num: int
    ) -> dict | None:
        """Fallback to Qwen3-VL for complex layouts."""
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
            from dashscope import MultiModalConversation

            resp = MultiModalConversation.call(
                model=self.fallback_model,
                messages=messages,
                api_key=self.api_key,
            )
            raw = resp.output.choices[0].message.content[0]["text"]
            return self._parse_json_response(raw)
        except Exception as e:
            logger.error("Fallback OCR also failed on page %d: %s", page_num, e)
            return None

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
