"""ctDNA screening attachment parser.

Extracts structured ScreeningResult from attachment pages classified as
SCREENING_ATTACHMENT by the section classifier. Uses qwen3-vl-plus for
model-based extraction with keyword fallback.

Screening results bypass the interpretation engine entirely (Contract D).
"""

import asyncio
import json
import logging
from functools import partial

from lablens.models.screening_result import ScreeningResult, ScreeningStatus

logger = logging.getLogger(__name__)

# Keyword detection for test types
_TEST_TYPE_KEYWORDS: dict[str, list[str]] = {
    "SPOT-MAS": ["spot-mas", "spot mas", "spotmas"],
    "Galleri": ["galleri"],
    "MCED": ["mced", "multi-cancer early detection"],
    "cfDNA": ["cfdna", "cell-free dna", "cell free dna"],
    "ctDNA": ["ctdna", "circulating tumor dna"],
}

_SCREENING_EXTRACTION_SCHEMA = """{
    "test_type": "string (SPOT-MAS | Galleri | MCED | cfDNA | other)",
    "result_status": "detected | not_detected | indeterminate",
    "signal_origin": "string or null (organ/tissue if detected)",
    "organs_screened": ["list of organ names screened"],
    "limitations": "string or null (sensitivity/specificity caveats)",
    "followup_recommendation": "string or null",
    "raw_summary": "string (verbatim key findings text)"
}"""

SCREENING_SYSTEM_PROMPT = (
    "You are extracting structured data from a cancer screening "
    "test report attachment.\n\n"
    "This is a ctDNA / liquid biopsy / MCED screening result — "
    "NOT a standard lab test.\n"
    f"Extract the following fields:\n{_SCREENING_EXTRACTION_SCHEMA}\n\n"
    "Rules:\n"
    "- result_status MUST be one of: detected, not_detected, indeterminate\n"
    "- If result says 'No signal detected' or 'Negative', use 'not_detected'\n"
    "- If result says 'Signal detected' or 'Positive', use 'detected'\n"
    "- signal_origin is only relevant when result is 'detected'\n"
    "- Extract limitations verbatim — do NOT summarize or omit caveats\n"
    "- If any field is unclear, set to null rather than guessing\n"
    "- organs_screened: list ALL organs/cancer types mentioned as screened\n"
)

SCREENING_USER_PROMPT = (
    "Extract the screening test results from this attachment page.\n"
    "Return ONLY valid JSON matching the schema above."
)


def detect_test_type(raw_text: str, rows: list[dict] | None = None) -> str:
    """Identify screening test type from page text and/or rows."""
    search_text = raw_text.lower()
    if rows:
        search_text += " " + " ".join(
            (r.get("test_name") or "") + " "
            + (r.get("reference_range_text") or "")
            for r in rows
        ).lower()

    for test_type, keywords in _TEST_TYPE_KEYWORDS.items():
        if any(kw in search_text for kw in keywords):
            return test_type
    return "Unknown"


def extract_from_keywords(
    raw_text: str, rows: list[dict], test_type: str
) -> ScreeningResult:
    """Keyword-based fallback extraction from OCR text + rows."""
    search_text = raw_text.lower()
    if rows:
        search_text += " " + " ".join(
            str(r.get("test_name", "")) + " " + str(r.get("value", ""))
            for r in rows
        ).lower()

    status = ScreeningStatus.INDETERMINATE
    if any(
        kw in search_text
        for kw in [
            "not detected",
            "negative",
            "no signal",
            "no abnormality",
            "không phát hiện",
        ]
    ):
        status = ScreeningStatus.NOT_DETECTED
    elif any(
        kw in search_text
        for kw in ["detected", "positive", "signal detected", "phát hiện"]
    ):
        status = ScreeningStatus.DETECTED

    return ScreeningResult(
        test_type=test_type,
        result_status=status,
        raw_text=search_text[:500],
        confidence=0.5,
    )


def parse_screening_json(raw: str) -> ScreeningResult | None:
    """Parse model JSON response into ScreeningResult."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Failed to parse screening JSON: %s", raw[:200])
        return None

    status_str = (data.get("result_status") or "indeterminate").lower()
    status_map = {
        "detected": ScreeningStatus.DETECTED,
        "not_detected": ScreeningStatus.NOT_DETECTED,
        "not detected": ScreeningStatus.NOT_DETECTED,
        "indeterminate": ScreeningStatus.INDETERMINATE,
    }
    return ScreeningResult(
        test_type=data.get("test_type", "Unknown"),
        result_status=status_map.get(status_str, ScreeningStatus.INDETERMINATE),
        signal_origin=data.get("signal_origin"),
        organs_screened=data.get("organs_screened", []),
        limitations=data.get("limitations"),
        followup_recommendation=data.get("followup_recommendation"),
        raw_text=data.get("raw_summary"),
        confidence=0.85,
    )


def canonicalize_screening(sr: ScreeningResult) -> ScreeningResult:
    """Post-process screening result into clean canonical form.

    - Deduplicate organs_screened (case-insensitive)
    - Filter out non-organ entries (descriptions, population terms)
    - Structure followup_recommendation into concise action items
    """
    # Deduplicate organs (case-insensitive, preserve first occurrence)
    _NON_ORGAN_TERMS = {
        "multiple cancers", "asymptomatic adults", "multiple organs",
        "general screening", "various cancers", "screening",
    }
    seen: set[str] = set()
    clean_organs: list[str] = []
    for organ in sr.organs_screened:
        key = organ.strip().lower()
        if key in seen or key in _NON_ORGAN_TERMS or len(key) < 2:
            continue
        seen.add(key)
        clean_organs.append(organ.strip())
    sr.organs_screened = clean_organs

    # Structure followup_recommendation: split numbered items into list
    if sr.followup_recommendation and isinstance(
        sr.followup_recommendation, str
    ):
        import re

        text = sr.followup_recommendation.strip()
        # Split on numbered patterns like "1.", "2.", etc.
        parts = re.split(r"(?:^|\n)\s*\d+\.\s*", text)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) > 1:
            # Reconstruct as clean numbered list
            sr.followup_recommendation = "\n".join(
                f"{i}. {p}" for i, p in enumerate(parts, 1)
            )

    return sr


class ScreeningParser:
    """Parse ctDNA/MCED screening attachment pages."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model  # qwen3-vl-plus

    async def parse_attachment(
        self,
        img_b64: str,
        raw_text: str,
        rows: list[dict],
        page_num: int,
    ) -> ScreeningResult:
        """Extract screening result from attachment page image.

        Uses qwen3-vl-plus for structured extraction.
        Falls back to keyword-based extraction if model fails.
        """
        test_type = detect_test_type(raw_text, rows)

        try:
            result = await self._extract_with_model(img_b64, page_num)
            if result:
                if result.test_type == "Unknown":
                    result.test_type = test_type
                return result
        except Exception as e:
            logger.warning(
                "Screening model extraction failed on page %d: %s",
                page_num, e,
            )

        return extract_from_keywords(raw_text, rows, test_type)

    async def _extract_with_model(
        self, img_b64: str, page_num: int
    ) -> ScreeningResult | None:
        """Call qwen3-vl-plus for structured screening extraction."""
        from dashscope import MultiModalConversation

        messages = [
            {"role": "system", "content": [{"text": SCREENING_SYSTEM_PROMPT}]},
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/png;base64,{img_b64}"},
                    {"text": SCREENING_USER_PROMPT},
                ],
            },
        ]

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            partial(
                MultiModalConversation.call,
                model=self.model,
                messages=messages,
                api_key=self.api_key,
            ),
        )
        raw = resp.output.choices[0].message.content[0]["text"]
        return parse_screening_json(raw)
