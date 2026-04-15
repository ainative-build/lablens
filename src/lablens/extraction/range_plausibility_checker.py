"""Analyte-family plausibility checker for OCR-extracted ranges.

Loads analyte-family rules and validates that extracted reference ranges
are plausible for the given test. Catches OCR row-swaps where an adjacent
row's range is grabbed (e.g. Calcium getting Phosphorus range).
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_FAMILIES_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "data"
    / "aliases"
    / "analyte-families.yaml"
)


class RangePlausibilityChecker:
    """Validate OCR-extracted ranges against analyte-family expectations."""

    def __init__(self, families_path: Path | None = None):
        self._families: list[dict] = []
        self._restricted_categories: set[str] = set()
        self._decision_threshold_codes: set[str] = set()
        self._loinc_to_category: dict[str, str] = {}
        self._load(families_path or _FAMILIES_PATH)

    def _load(self, path: Path):
        if not path.exists():
            logger.warning("Analyte families file not found: %s", path)
            return
        data = yaml.safe_load(path.read_text())

        families = data.get("families", {})
        for name, fam in families.items():
            fam["name"] = name
            self._families.append(fam)
            cat = fam.get("category", "")
            for code in fam.get("loinc_codes", []):
                self._loinc_to_category[code] = cat

        self._restricted_categories = set(
            data.get("restricted_flag_categories", [])
        )
        self._decision_threshold_codes = set(
            data.get("decision_threshold_loinc_codes", [])
        )

    def get_category(self, loinc_code: str | None) -> str | None:
        """Get the analyte category for a LOINC code."""
        if not loinc_code:
            return None
        return self._loinc_to_category.get(loinc_code)

    def is_restricted_flag_category(self, loinc_code: str | None) -> bool:
        """Check if OCR flag should NOT drive severity for this test."""
        cat = self.get_category(loinc_code)
        return cat in self._restricted_categories if cat else False

    def is_decision_threshold(self, loinc_code: str | None) -> bool:
        """Check if this LOINC uses decision thresholds, not reference intervals."""
        return loinc_code in self._decision_threshold_codes if loinc_code else False

    def validate_range(
        self,
        loinc_code: str | None,
        value: float,
        ref_low: float | None,
        ref_high: float | None,
        unit: str | None,
        curated_ref_low: float | None = None,
        curated_ref_high: float | None = None,
    ) -> str:
        """Validate range plausibility for a given analyte.

        Returns:
            "high" — range looks plausible
            "medium" — range is usable but imperfect
            "low" — range is suspicious (likely OCR error)
        """
        if ref_low is None or ref_high is None:
            return "high"  # No range to validate

        # Curated cross-check: if lab range midpoint differs from curated by >5x,
        # the lab range is likely from a different unit system or adjacent row
        if curated_ref_low is not None and curated_ref_high is not None:
            lab_mid = (ref_low + ref_high) / 2
            cur_mid = (curated_ref_low + curated_ref_high) / 2
            if lab_mid > 0 and cur_mid > 0:
                ratio = max(lab_mid / cur_mid, cur_mid / lab_mid)
                if ratio > 5.0:
                    logger.info(
                        "Lab range [%s-%s] midpoint differs from curated [%s-%s] "
                        "by %.1fx — suspicious for %s",
                        ref_low, ref_high, curated_ref_low, curated_ref_high,
                        ratio, loinc_code,
                    )
                    return "low"

        if not loinc_code:
            # No LOINC — can't do family-specific check, use generic
            return self._generic_check(value, ref_low, ref_high)

        # Find matching families for this LOINC — check all, return best
        matched_any = False
        for fam in self._families:
            if loinc_code not in fam.get("loinc_codes", []):
                continue
            matched_any = True

            fam_ref_low, fam_ref_high = fam.get("ref_range", [0, 999999])

            fam_val_low, fam_val_high = fam.get("value_range", [0, 999999])

            # Check: value AND range should be in the same family scale
            ref_mid = (ref_low + ref_high) / 2
            fam_mid = (fam_ref_low + fam_ref_high) / 2
            if fam_mid > 0 and ref_mid > 0:
                range_ratio = ref_mid / fam_mid
                value_ratio = (
                    value / ((fam_val_low + fam_val_high) / 2)
                    if (fam_val_low + fam_val_high) > 0
                    else 1.0
                )
                # Both value and range should be in similar scale to family
                range_ok = 0.2 <= range_ratio <= 5.0
                value_ok = 0.01 <= value_ratio <= 100.0
                # If range fits one scale but value fits another → suspicious
                if range_ok and value_ok:
                    return "high"
            elif fam_ref_high > 0:
                if ref_low >= fam_ref_low * 0.1 and ref_high <= fam_ref_high * 10:
                    return "high"

        if matched_any:
            # None of the matching families validated the range
            logger.info(
                "Range [%s-%s] not plausible for any family of %s — suspicious",
                ref_low, ref_high, loinc_code,
            )
            return "low"

        # No matching family — use generic check
        return self._generic_check(value, ref_low, ref_high)

    @staticmethod
    def _generic_check(
        value: float, ref_low: float, ref_high: float
    ) -> str:
        """Generic plausibility: value within 10x of range midpoint."""
        range_mid = (ref_low + ref_high) / 2
        if range_mid <= 0:
            return "medium"
        ratio = value / range_mid
        if ratio > 10 or ratio < 0.1:
            return "low"
        return "high"
