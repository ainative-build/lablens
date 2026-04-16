"""Deterministic section classifier using keyword + layout heuristics.

Two-pass classification (red-team fix #1 + #2):
  Pass 1 (pre-filter): Scan raw OCR text for page-level section keywords.
           Catches non-tabular pages (screening) before noise filter kills them.
  Pass 2 (post-filter): Split parsed rows into sub-blocks by keyword transition.

Zero API calls. Classification adds < 5ms per page. 100% deterministic.
"""

import logging
import re

from lablens.models.section_types import ClassifiedBlock, SectionType

logger = logging.getLogger(__name__)

# --- Keyword sets per section type (priority order: screening > HPLC > hormone) ---

_SCREENING_KEYWORDS = frozenset({
    "spot-mas", "spot mas", "spotmas", "galleri", "cfdna", "ctdna",
    "methylation", "mced", "screening", "cell-free dna", "cell free dna",
    "liquid biopsy", "circulating tumor", "multi-cancer",
    # Vietnamese
    "tầm soát ung thư", "phát hiện sớm", "chưa phát hiện",
})

_HPLC_KEYWORDS = frozenset({
    "hba1c", "hb a1c", "a1c", "ifcc", "ngsp", "eag",
    "estimated average glucose", "hemoglobin a1c", "glycated",
    "electrophoresis", "hplc",
    # Vietnamese
    "đường huyết trung bình",
})

_HORMONE_KEYWORDS = frozenset({
    "testosterone", "estradiol", "progesterone", "fsh", "lh",
    "prolactin", "cortisol", "dhea", "tsh", "free t3", "free t4",
    "anti-mullerian", "amh", "inhibin",
})

_APPENDIX_KEYWORDS = frozenset({
    "methodology", "procedure", "specimen requirement",
    "certification", "accreditation", "note:", "disclaimer",
    "phương pháp", "quy trình",
})

# Minimum keyword matches for page-level classification
_SCREENING_PAGE_THRESHOLD = 2
_APPENDIX_PAGE_THRESHOLD = 3

# Minimum consecutive rows to start a new sub-block
_TRANSITION_MIN_ROWS = 2


def _find_keywords(text: str, keyword_set: frozenset[str]) -> list[str]:
    """Return all keywords from the set found in the text (word-boundary match).

    Uses \\b word boundaries to prevent substring false positives
    (e.g., "eag" inside "reagent", "amh" inside "amherst").
    Multi-word keywords and those with hyphens are handled correctly
    because re.escape preserves hyphens and spaces within the pattern.
    """
    return [
        kw for kw in keyword_set
        if re.search(r"\b" + re.escape(kw) + r"\b", text)
    ]


def _score_row(row: dict) -> tuple[SectionType, float, list[str]]:
    """Score a single row against all keyword sets.

    Returns (best_section_type, confidence, matched_keywords).
    Priority: screening > HPLC > hormone > standard.
    """
    name = (row.get("test_name") or "").lower()
    unit = (row.get("unit") or "").lower()
    ref_text = (row.get("reference_range_text") or "").lower()
    text = f"{name} {unit} {ref_text}"

    # Check each set in priority order
    matches = _find_keywords(text, _SCREENING_KEYWORDS)
    if matches:
        return SectionType.SCREENING_ATTACHMENT, 0.90, matches

    matches = _find_keywords(text, _HPLC_KEYWORDS)
    if matches:
        return SectionType.HPLC_DIABETES_BLOCK, 0.85, matches

    matches = _find_keywords(text, _HORMONE_KEYWORDS)
    if matches:
        return SectionType.HORMONE_IMMUNOLOGY_BLOCK, 0.80, matches

    return SectionType.STANDARD_LAB_TABLE, 1.0, []


class SectionClassifier:
    """Deterministic section classifier — no API calls, < 5ms per page."""

    def classify_page(
        self, raw_text: str, rows: list[dict]
    ) -> list[ClassifiedBlock]:
        """Two-pass classification: raw text first, then row-level.

        Pass 1 (pre-filter): Scan raw_text for page-level keywords.
                 Catches non-tabular pages that produce empty/garbled rows.
        Pass 2 (post-filter): Split parsed rows into sub-blocks by keyword.
        """
        raw_lower = raw_text.lower()

        # Pass 1: Page-level classification from raw OCR text
        screening_kws = _find_keywords(raw_lower, _SCREENING_KEYWORDS)
        if len(screening_kws) >= _SCREENING_PAGE_THRESHOLD:
            logger.debug(
                "Page classified as SCREENING (keywords: %s)", screening_kws
            )
            return [ClassifiedBlock(
                section_type=SectionType.SCREENING_ATTACHMENT,
                rows=rows,
                confidence=min(0.90 + len(screening_kws) * 0.02, 0.98),
                trigger_keywords=screening_kws,
            )]

        appendix_kws = _find_keywords(raw_lower, _APPENDIX_KEYWORDS)
        if len(appendix_kws) >= _APPENDIX_PAGE_THRESHOLD:
            logger.debug(
                "Page classified as APPENDIX (keywords: %s)", appendix_kws
            )
            return [ClassifiedBlock(
                section_type=SectionType.APPENDIX_TEXT,
                rows=rows,
                confidence=min(0.85 + len(appendix_kws) * 0.02, 0.95),
                trigger_keywords=appendix_kws,
            )]

        # Pass 2: Row-level sub-block classification
        if not rows:
            return [ClassifiedBlock(
                section_type=SectionType.STANDARD_LAB_TABLE,
                rows=[],
                confidence=1.0,
            )]

        return self._classify_rows(rows)

    def _classify_rows(self, rows: list[dict]) -> list[ClassifiedBlock]:
        """Split parsed rows into sub-blocks by keyword transitions.

        Single-row matches embedded in a larger block are absorbed by
        neighbors (noise tolerance via _TRANSITION_MIN_ROWS).
        """
        # Score each row
        scored = [_score_row(r) for r in rows]

        # Build blocks: group consecutive rows of same section type
        blocks: list[ClassifiedBlock] = []
        current_type = scored[0][0]
        current_rows: list[dict] = [rows[0]]
        current_kws: list[str] = list(scored[0][2])

        for i in range(1, len(rows)):
            row_type, _, row_kws = scored[i]
            if row_type == current_type:
                current_rows.append(rows[i])
                current_kws.extend(row_kws)
            else:
                # Potential transition — check if it's sustained
                lookahead_same = 1
                for j in range(i + 1, min(i + _TRANSITION_MIN_ROWS, len(rows))):
                    if scored[j][0] == row_type:
                        lookahead_same += 1
                if lookahead_same >= _TRANSITION_MIN_ROWS:
                    # Real transition — flush current block, start new
                    blocks.append(self._make_block(
                        current_type, current_rows, current_kws,
                    ))
                    current_type = row_type
                    current_rows = [rows[i]]
                    current_kws = list(row_kws)
                else:
                    # Single-row blip — absorb into current block
                    current_rows.append(rows[i])

        # Flush last block
        blocks.append(self._make_block(current_type, current_rows, current_kws))
        return blocks

    @staticmethod
    def _make_block(
        section_type: SectionType,
        rows: list[dict],
        keywords: list[str],
    ) -> ClassifiedBlock:
        """Create a ClassifiedBlock with confidence based on keyword count."""
        unique_kws = list(set(keywords))
        n = len(unique_kws)
        if section_type == SectionType.STANDARD_LAB_TABLE:
            confidence = 1.0  # Default type always confident
        elif n >= 3:
            confidence = 0.95
        elif n == 2:
            confidence = 0.80
        elif n == 1:
            confidence = 0.60
        else:
            confidence = 1.0  # No keywords = standard (default)
        return ClassifiedBlock(
            section_type=section_type,
            rows=rows,
            confidence=confidence,
            trigger_keywords=unique_kws,
        )
