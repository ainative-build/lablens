"""Map extracted test names to LOINC codes with confidence scoring.

Matching strategy: exact → alias → fuzzy (SequenceMatcher ≥ 0.8).
"""

import logging
from difflib import SequenceMatcher

from lablens.extraction.alias_registry import AliasRegistry

logger = logging.getLogger(__name__)


class TerminologyMapper:
    """Match extracted test names to LOINC codes."""

    def __init__(self, registry: AliasRegistry | None = None):
        self.registry = registry or AliasRegistry()
        self._fuzzy_index = self.registry.all_entries

    def match(self, test_name: str) -> tuple[str | None, str]:
        """Match test name to LOINC code.

        Returns:
            (loinc_code or None, confidence: "high"|"medium"|"low")
        """
        # Step 1: Exact/alias match
        identity = self.registry.lookup(test_name)
        if identity:
            confidence = "high" if identity.match_type == "exact" else "medium"
            logger.debug(
                "Matched '%s' → %s (%s, %s)",
                test_name,
                identity.loinc_code,
                identity.match_type,
                confidence,
            )
            return identity.loinc_code, confidence

        # Step 2: Fuzzy match
        best_score = 0.0
        best_code = None
        key = test_name.lower().strip()
        for name, code in self._fuzzy_index:
            score = SequenceMatcher(None, key, name).ratio()
            if score > best_score:
                best_score = score
                best_code = code

        if best_score >= 0.8 and best_code is not None:
            logger.info(
                "Fuzzy matched '%s' → %s (score=%.2f)",
                test_name,
                best_code,
                best_score,
            )
            return best_code, "low"

        logger.warning("No match for '%s' (best fuzzy=%.2f)", test_name, best_score)
        return None, "low"
