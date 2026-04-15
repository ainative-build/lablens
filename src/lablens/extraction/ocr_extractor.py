"""Qwen-OCR extraction via DashScope multimodal API.

Converts PDF pages to images, sends to Qwen-VL-OCR with structured prompts,
parses JSON responses into LabReport. Falls back to qwen-vl-max on failure.
"""

import asyncio
import json
import logging
import re
from functools import partial

from lablens.config import Settings
from lablens.extraction.extraction_prompts import (
    EXTRACTION_PROMPTS,
    EXTRACTION_USER_PROMPT,
)
from lablens.extraction.pdf_processor import PDFProcessor
from lablens.extraction.response_parser import deduplicate_values, filter_noise_values
from lablens.models.lab_report import LabReport, LabValue

logger = logging.getLogger(__name__)

# Pattern: "3.2 - 7.4", "0.22 - 0.45", etc.
_RANGE_PATTERN = re.compile(r"^\s*([\d.]+)\s*[-–—]\s*([\d.]+)\s*$")
# Pattern: "< 200", "<= 1.7", "≤ 5.0"
_UPPER_BOUND_PATTERN = re.compile(r"^\s*[<≤]\s*=?\s*([\d.]+)\s*$")
# Pattern: "> 60", ">= 3.5", "≥ 3.5"
_LOWER_BOUND_PATTERN = re.compile(r"^\s*[>≥]\s*=?\s*([\d.]+)\s*$")
# Pattern: text with embedded range, e.g. "Normal: 3.2 - 7.4", "Desirable: < 5.18"
_TEXT_RANGE_PATTERN = re.compile(r"([\d.]+)\s*[-–—]\s*([\d.]+)")


def _fix_range_fields(v: dict) -> dict:
    """Pre-process reference range fields from LLM output before Pydantic validation.

    Handles cases where the LLM returns range strings instead of separate numbers.
    """
    for field in ("reference_range_low", "reference_range_high"):
        val = v.get(field)
        if val is None or isinstance(val, (int, float)):
            continue
        val = str(val).strip()

        # Try simple "low - high" range pattern
        m = _RANGE_PATTERN.match(val)
        if m:
            v["reference_range_low"] = float(m.group(1))
            v["reference_range_high"] = float(m.group(2))
            if not v.get("reference_range_text"):
                v["reference_range_text"] = val
            return v

        # Try upper bound: "< 200"
        m = _UPPER_BOUND_PATTERN.match(val)
        if m:
            v["reference_range_low"] = None
            v["reference_range_high"] = float(m.group(1))
            if not v.get("reference_range_text"):
                v["reference_range_text"] = val
            return v

        # Try lower bound: "> 60"
        m = _LOWER_BOUND_PATTERN.match(val)
        if m:
            v["reference_range_low"] = float(m.group(1))
            v["reference_range_high"] = None
            if not v.get("reference_range_text"):
                v["reference_range_text"] = val
            return v

        # Try extracting embedded range from text like "Normal: 3.2 - 7.4"
        m = _TEXT_RANGE_PATTERN.search(val)
        if m:
            v["reference_range_low"] = float(m.group(1))
            v["reference_range_high"] = float(m.group(2))
            if not v.get("reference_range_text"):
                v["reference_range_text"] = val
            return v

        # Unparseable — save as text, set numeric to None
        v["reference_range_text"] = val
        v[field] = None

    return v


def _validate_range_plausibility(v: dict) -> dict:
    """Check if OCR-extracted ranges are plausible for the value.

    Catches row-swap errors where OCR grabs an adjacent row's range.
    If range is implausible, clear it so the engine falls back to curated ranges.
    """
    low = v.get("reference_range_low")
    high = v.get("reference_range_high")
    val = v.get("value")

    if low is None or high is None:
        return v

    # Range must be low < high
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        if low >= high:
            logger.info("Clearing inverted range for %s: [%s-%s]", v.get("test_name", "?"), low, high)
            v["reference_range_low"] = None
            v["reference_range_high"] = None
            return v

    # If value is numeric, check it's within plausible distance of range
    if isinstance(val, (int, float)) and isinstance(low, (int, float)) and isinstance(high, (int, float)):
        try:
            numeric_val = float(val)
            range_mid = (low + high) / 2
            range_span = high - low
            if range_span > 0 and range_mid > 0:
                # If value is >10x the range midpoint or <1/10th, range is likely from wrong row
                ratio = numeric_val / range_mid
                if ratio > 10 or ratio < 0.1:
                    logger.info(
                        "Suspicious range for %s: val=%s range=[%s-%s] ratio=%.1f — clearing",
                        v.get("test_name", "?"), val, low, high, ratio,
                    )
                    v["reference_range_low"] = None
                    v["reference_range_high"] = None
        except (ValueError, ZeroDivisionError):
            pass

    return v


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
                    v = _fix_range_fields(v)
                    v = _validate_range_plausibility(v)
                    all_values.append(LabValue(**v))
                except Exception as e:
                    logger.warning("Skipping invalid value on page %d: %s", i + 1, e)

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
            raw = await self._call_dashscope_ocr(self.model, messages)
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
            raw = await self._call_dashscope_ocr(self.fallback_model, messages)
            return self._parse_json_response(raw)
        except Exception as e:
            logger.error("Fallback OCR also failed on page %d: %s", page_num, e)
            return None

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
