"""Unit normalization and conversion.

Converts lab values to canonical units using LOINC-code-keyed conversion factors.
Never silently converts ambiguous units — flags as low confidence instead.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONVERSIONS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "aliases" / "unit-conversions.yaml"


@dataclass
class NormalizationResult:
    value: float
    unit: str
    original_value: float
    original_unit: str
    converted: bool
    confidence: str  # "high" | "low"


class UnitNormalizer:
    """Normalize units to canonical form with conversion support."""

    def __init__(self, conversions_path: Path | None = None):
        self._conversions: dict = {}
        self._unit_aliases: dict[str, str] = {}
        self._load(conversions_path or CONVERSIONS_PATH)

    def _load(self, path: Path):
        if not path.exists():
            logger.warning("Unit conversions file not found: %s", path)
            return
        data = yaml.safe_load(path.read_text())
        self._unit_aliases = data.get("unit_aliases", {})
        conversions = data.get("conversions", {})
        # Filter out unit_aliases key from conversions dict
        self._conversions = {
            k: v for k, v in conversions.items() if isinstance(v, dict) and "canonical_unit" in v
        }

    def normalize_unit(self, unit: str) -> str:
        """Normalize unit alias to canonical form."""
        return self._unit_aliases.get(unit, unit)

    def normalize(
        self, loinc_code: str, value: float, unit: str
    ) -> NormalizationResult:
        """Normalize value+unit to canonical unit for the test.

        Lookup by LOINC code (Finding #10 — never by test name).
        Returns original if conversion uncertain.
        """
        normalized_unit = self.normalize_unit(unit)

        test_conv = self._conversions.get(loinc_code)
        if not test_conv:
            return NormalizationResult(
                value=value,
                unit=normalized_unit,
                original_value=value,
                original_unit=unit,
                converted=False,
                confidence="high",
            )

        canonical = test_conv["canonical_unit"]
        if normalized_unit == canonical:
            return NormalizationResult(
                value=value,
                unit=canonical,
                original_value=value,
                original_unit=unit,
                converted=False,
                confidence="high",
            )

        # Find conversion factor
        for conv in test_conv.get("conversions", []):
            if conv["from"].lower() == normalized_unit.lower():
                converted_value = round(value * conv["factor"], 4)
                return NormalizationResult(
                    value=converted_value,
                    unit=canonical,
                    original_value=value,
                    original_unit=unit,
                    converted=True,
                    confidence=conv.get("confidence", "high"),
                )

        # No conversion found — keep original with low confidence
        logger.warning(
            "No conversion for LOINC %s: %s → %s. Keeping original.",
            loinc_code,
            unit,
            canonical,
        )
        return NormalizationResult(
            value=value,
            unit=normalized_unit,
            original_value=value,
            original_unit=unit,
            converted=False,
            confidence="low",
        )
