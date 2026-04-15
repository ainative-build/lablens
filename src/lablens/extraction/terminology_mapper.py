"""Map extracted test names to LOINC codes with confidence scoring.

Matching cascade: exact → alias → normalized exact → normalized alias → fuzzy (≥ 0.8).
Aggressive normalization strips specimen types, brackets, and abbreviation variants
to handle real-world OCR output like "Testosterone [Serum]*" → "testosterone".
"""

import logging
import re
from difflib import SequenceMatcher

from lablens.extraction.alias_registry import AliasRegistry

logger = logging.getLogger(__name__)

# Patterns to strip from test names during normalization
_SPECIMEN_PATTERN = re.compile(
    r"\s*[\[\(]\s*(serum|plasma|whole blood|blood|urine|huyết thanh|"
    r"máu|nước tiểu|sang|urina)\s*[\]\)]", re.I
)
# Parenthetical abbreviations like (NEU), (HCT), (Ca), (Fe)
_PAREN_ABBREV = re.compile(r"\s*\([A-Za-z\s]{1,10}\)\s*")
_TRAILING_JUNK = re.compile(r"[\s*#†‡§]+$")
_TRAILING_PCT = re.compile(r"\s*%\s*$")
_MULTI_SPACE = re.compile(r"\s+")

# Common abbreviation expansions for normalization
_ABBREVIATION_MAP = {
    "gamma gt": "ggt",
    "gamma glutamyl transferase": "ggt",
    "hba1c": "hba1c",
    "hb a1c": "hba1c",
    "hemoglobin a1c": "hba1c",
    "hdl-c": "hdl cholesterol",
    "hdl c": "hdl cholesterol",
    "high density lipoprotein cholesterol": "hdl cholesterol",
    "ldl-c": "ldl cholesterol",
    "ldl c": "ldl cholesterol",
    "alt (gpt)": "alt",
    "ast (got)": "ast",
    "hs crp": "crp",
    "hs-crp": "crp",
    "high-sensitive c-reactive protein": "crp",
    "high sensitive c-reactive protein": "crp",
    "25-oh vitamin d": "vitamin d",
    "25 oh vitamin d": "vitamin d",
    "tsh": "tsh",
    "free t4": "free t4",
    "free t3": "free t3",
    "egfr": "egfr",
    "eag": "estimated average glucose",
    "mchc": "mchc",
    "mch": "mch",
    "mcv": "mcv",
    "rdw": "rdw",
    "mpv": "mpv",
    "pdw": "pdw",
    "pct": "plateletcrit",
    "plt": "platelets",
    "rbc": "erythrocytes",
    "wbc": "leukocytes",
    "hct": "hematocrit",
    "hb": "hemoglobin",
    "hgb": "hemoglobin",
    "neu": "neutrophils",
    "eos": "eosinophils",
    "ba so": "basophils",
    "nrbc": "nucleated red blood cells",
    "shbg": "sex hormone binding globulin",
    "ca 19-9": "ca 19-9",
    "ca 125": "ca 125",
    "cea": "cea",
    "afp": "afp",
    "psa": "psa",
    "hbsab": "hepatitis b surface antibody",
    "hbsag": "hepatitis b surface antigen",
    "hcv ab": "hepatitis c antibody",
    "alp": "alkaline phosphatase",
    "ig": "immature granulocytes",
}


def normalize_test_name(name: str) -> str:
    """Aggressively normalize a test name for matching.

    Strips specimen types, brackets, special chars, and maps abbreviations.
    """
    s = name.lower().strip()
    # Remove specimen info in brackets/parens
    s = _SPECIMEN_PATTERN.sub("", s)
    # Remove trailing % (differential CBC)
    s = _TRAILING_PCT.sub("", s)
    # Remove parenthetical abbreviations like (NEU), (HCT), (Ca)
    s = _PAREN_ABBREV.sub(" ", s)
    # Remove trailing special chars
    s = _TRAILING_JUNK.sub("", s)
    # Collapse whitespace
    s = _MULTI_SPACE.sub(" ", s).strip()

    # Check abbreviation map (match longest first)
    for abbr, expansion in _ABBREVIATION_MAP.items():
        if s == abbr or s.startswith(abbr + " "):
            return expansion

    return s


class TerminologyMapper:
    """Match extracted test names to LOINC codes."""

    def __init__(self, registry: AliasRegistry | None = None):
        self.registry = registry or AliasRegistry()
        self._fuzzy_index = self.registry.all_entries
        # Build normalized lookup index
        self._normalized_index: dict[str, str] = {}
        for name, loinc in self._fuzzy_index:
            norm = normalize_test_name(name)
            if norm not in self._normalized_index:
                self._normalized_index[norm] = loinc

    def match(self, test_name: str) -> tuple[str | None, str]:
        """Match test name to LOINC code.

        Cascade: exact → alias → normalized → fuzzy.
        Returns (loinc_code or None, confidence).
        """
        # Step 1: Exact/alias match (raw)
        identity = self.registry.lookup(test_name)
        if identity:
            conf = "high" if identity.match_type == "exact" else "medium"
            return identity.loinc_code, conf

        # Step 2: Normalized match
        norm = normalize_test_name(test_name)
        if norm in self._normalized_index:
            logger.info("Normalized match: '%s' → '%s'", test_name, norm)
            return self._normalized_index[norm], "medium"

        # Step 3: Fuzzy match on normalized name
        best_score = 0.0
        best_code = None
        for name, code in self._fuzzy_index:
            score = SequenceMatcher(None, norm, normalize_test_name(name)).ratio()
            if score > best_score:
                best_score = score
                best_code = code

        if best_score >= 0.8 and best_code is not None:
            logger.info("Fuzzy match: '%s' → %s (%.2f)", test_name, best_code, best_score)
            return best_code, "low"

        logger.warning("No match for '%s' (best fuzzy=%.2f)", test_name, best_score)
        return None, "low"
