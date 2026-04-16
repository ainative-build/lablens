"""Qwen-OCR extraction via DashScope multimodal API.

Converts PDF pages to images, sends to qwen-vl-ocr-latest with structured
prompts, parses JSON responses into LabReport. Section classifier routes
pages/sub-blocks to specialized parsers. Suspicious pages get a targeted
retry with Qwen3-VL document parsing for better layout handling.
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
from lablens.extraction.hplc_semantic_validator import validate_hplc_semantics
from lablens.extraction.ocr_range_preprocessor import (
    fix_range_fields,
    is_page_suspicious,
    validate_range_plausibility,
)
from lablens.extraction.pdf_processor import PDFProcessor
from lablens.extraction.response_parser import deduplicate_values, filter_noise_values
from lablens.extraction.section_classifier import SectionClassifier
from lablens.models.lab_report import LabReport, LabValue
from lablens.models.section_types import SectionType

logger = logging.getLogger(__name__)


class OCRExtractor:
    """Extract lab values from PDF using Qwen vision models."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_ocr_model
        self.structure_model = settings.dashscope_structure_model
        self.reparse_model = "qwen-vl-max-latest"
        self._classifier = SectionClassifier()

    async def extract_from_pdf(
        self, pdf_bytes: bytes, language: str = "auto"
    ) -> tuple[LabReport, dict[int, str]]:
        """Full extraction pipeline: PDF → images → OCR → classify → route → LabReport.

        Returns (LabReport, page_images) where page_images = {page_num: img_b64}.
        Page images are passed through for the semantic verifier (Phase 4).
        They are NOT stored in LabReport to keep serialization-safe.
        """
        PDFProcessor.validate_pdf(pdf_bytes)
        images = PDFProcessor.pdf_to_base64_images(pdf_bytes)

        all_values: list[LabValue] = []
        screening_results: list[dict] = []
        page_images: dict[int, str] = {}
        metadata: dict = {}

        for i, img_b64 in enumerate(images):
            page_num = i + 1
            page_images[page_num] = img_b64

            page_result, raw_text = await self._extract_page(
                img_b64, language, page_num=page_num
            )
            if not page_result:
                continue

            # Capture metadata from first page
            if not metadata.get("source_language"):
                metadata["source_language"] = page_result.get("source_language", "en")
                metadata["lab_name"] = page_result.get("lab_name")
                metadata["report_date"] = page_result.get("report_date")
                metadata["patient_id"] = page_result.get("patient_id")

            raw_values = page_result.get("values", [])

            # Classify BEFORE noise filtering (red-team fix #1 + #2)
            blocks = self._classifier.classify_page(raw_text, raw_values)

            for block in blocks:
                logger.debug(
                    "Page %d block: %s (%d rows, conf=%.2f, kw=%s)",
                    page_num, block.section_type.value,
                    len(block.rows), block.confidence, block.trigger_keywords,
                )

                if block.section_type == SectionType.APPENDIX_TEXT:
                    logger.debug(
                        "Skipping appendix block on page %d: %d rows",
                        page_num, len(block.rows),
                    )
                    continue

                if block.section_type == SectionType.SCREENING_ATTACHMENT:
                    # PHASE 1 STUB: Screening pages are detected and logged
                    # but NOT parsed yet. Phase 3 will implement a dedicated
                    # ScreeningParser that extracts signal_value, result_status,
                    # and follow-up guidance into screening_results[].
                    # Until then, these pages are intentionally skipped to
                    # prevent the generic row extractor from misinterpreting
                    # non-tabular screening content as analyte rows.
                    logger.info(
                        "Screening attachment on page %d — detected but "
                        "skipped (Phase 3 will add ScreeningParser)",
                        page_num,
                    )
                    continue

                # Standard + HPLC + Hormone: suspicious-page retry, then validate
                # Guard: skip suspicious check for sub-blocks < 3 rows —
                # is_page_suspicious was designed for full pages; tiny blocks
                # always trigger it, causing wasted API calls + cross-block
                # contamination from full-page reparse merge.
                block_raw = block.rows
                if len(block_raw) >= 3 and is_page_suspicious(block_raw):
                    logger.info(
                        "Page %d block (%s) flagged suspicious — retrying",
                        page_num, block.section_type.value,
                    )
                    reparse_result = await self._reparse_page(
                        img_b64, language, page_num
                    )
                    if reparse_result:
                        reparse_values = reparse_result.get("values", [])
                        merged, patched = self._merge_row_level(
                            block_raw, reparse_values
                        )
                        if patched > 0:
                            logger.info(
                                "Row-level merge: patched %d/%d rows",
                                patched, len(merged),
                            )
                            block_raw = merged

                if block.section_type == SectionType.HPLC_DIABETES_BLOCK:
                    # Phase 2 will implement HPLCBlockParser here
                    # For now: process as standard rows with section_type tag
                    logger.info(
                        "HPLC block on page %d — stub: standard flow "
                        "with section_type tag (full parser in Phase 2)",
                        page_num,
                    )

                for v in block_raw:
                    try:
                        v = fix_range_fields(v)
                        v = validate_range_plausibility(v)
                        v = validate_hplc_semantics(v)
                        # Shallow copy to avoid mutating original block rows
                        v = {**v, "section_type": block.section_type.value}
                        all_values.append(LabValue(**v))
                    except Exception as e:
                        logger.warning(
                            "Skipping invalid value on page %d: %s",
                            page_num, e,
                        )

        all_values = filter_noise_values(all_values)
        all_values = deduplicate_values(all_values)

        report = LabReport(
            source_language=metadata.get("source_language", "en"),
            lab_name=metadata.get("lab_name"),
            report_date=metadata.get("report_date"),
            patient_id=metadata.get("patient_id"),
            values=all_values,
            screening_results=screening_results,
            page_count=len(images),
        )
        return report, page_images

    async def _extract_page(
        self, img_b64: str, language: str, page_num: int
    ) -> tuple[dict | None, str]:
        """Extract lab values from a single page image using primary OCR model.

        Returns (parsed_result, raw_text) where:
        - parsed_result: structured JSON from _parse_json_response()
        - raw_text: the model's full response string before JSON parsing

        raw_text is used by the section classifier (Pass 1) to scan for
        page-level keywords. For qwen-vl-ocr, the response IS the full
        OCR transcript of the page (the model outputs complete text even
        under structured extraction prompts), so Pass 1 operates on
        genuine page content — not just the structured JSON fields.
        """
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
            return self._parse_json_response(raw), raw
        except Exception as e:
            logger.warning("OCR failed on page %d: %s", page_num, e)
            return None, ""

    async def _reparse_page(
        self, img_b64: str, language: str, page_num: int
    ) -> dict | None:
        """Re-parse a suspicious page using Qwen3-VL with document-parsing prompt.

        Qwen3-VL handles complex layouts, footnote-style ranges, and mixed
        table formats better than the OCR-specialized model.

        KNOWN LIMITATION: This reparses the full page image, not individual
        sub-blocks. On mixed pages (e.g., standard table + HPLC block),
        _merge_row_level may introduce rows from outside the target block's
        scope. The len(block_raw) >= 3 guard in extract_from_pdf reduces
        this risk by skipping reparse for small sub-blocks, but does not
        eliminate it for larger blocks on mixed pages. Phase 2 should scope
        reparse to block-level regions using bounding-box coordinates.
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
