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
                    merged, patched = self._merge_row_level(
                        raw_values, reparse_values
                    )
                    if patched > 0:
                        logger.info(
                            "Row-level merge improved page %d: patched %d/%d rows",
                            page_num, patched, len(merged),
                        )
                        raw_values = merged

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
    def _normalize_name(name: str) -> str:
        """Normalize test name for matching between original and reparse."""
        import re
        name = name.lower().strip()
        name = re.sub(r"\s*\[.*?\]", "", name)   # Remove [Serum], [Whole blood]
        name = re.sub(r"\s*\(.*?\)", "", name)    # Remove (NGSP), (IFCC)
        name = re.sub(r"[*#†]", "", name)         # Remove footnote markers
        name = re.sub(r"\s+", " ", name).strip()
        return name

    @staticmethod
    def _row_is_complete(v: dict) -> bool:
        """Check if a row has unit AND at least one range bound."""
        has_unit = bool(v.get("unit"))
        has_range = (
            v.get("reference_range_low") is not None
            or v.get("reference_range_high") is not None
        )
        return has_unit and has_range

    @classmethod
    def _merge_row_level(
        cls, original: list[dict], reparsed: list[dict]
    ) -> tuple[list[dict], int]:
        """Merge original and reparsed values at row level.

        Keeps original rows that are already complete. Only patches
        incomplete rows with reparsed equivalents when the reparse is
        demonstrably better for that specific analyte.

        Returns:
            (merged_values, patch_count)
        """
        if not reparsed:
            return original, 0

        # Build reparse lookup by normalized name
        reparse_map: dict[str, list[dict]] = {}
        for v in reparsed:
            key = cls._normalize_name(v.get("test_name", ""))
            if key:
                reparse_map.setdefault(key, []).append(v)

        merged = []
        patched = 0

        for orig in original:
            if cls._row_is_complete(orig):
                # Original is good — keep it
                merged.append(orig)
                continue

            # Original is incomplete — look for reparse match
            key = cls._normalize_name(orig.get("test_name", ""))
            candidates = reparse_map.get(key, [])

            best = None
            for cand in candidates:
                if not cls._row_is_complete(cand):
                    continue
                # Verify unit consistency: if both have units, they should match
                orig_unit = (orig.get("unit") or "").strip().lower()
                cand_unit = (cand.get("unit") or "").strip().lower()
                if orig_unit and cand_unit and orig_unit != cand_unit:
                    continue  # Unit regression — skip
                best = cand
                break

            if best:
                merged.append(best)
                patched += 1
            else:
                merged.append(orig)

        # Add new values from reparse that weren't in original
        orig_keys = {cls._normalize_name(v.get("test_name", "")) for v in original}
        for v in reparsed:
            key = cls._normalize_name(v.get("test_name", ""))
            if key and key not in orig_keys and cls._row_is_complete(v):
                merged.append(v)
                patched += 1

        return merged, patched

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
