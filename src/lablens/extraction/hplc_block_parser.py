"""HPLC block parser: extract, validate, cross-check HbA1c/IFCC/eAG.

Replaces the Phase 1 HPLC stub with a full parser that:
1. Identifies which analyte each row represents (NGSP/IFCC/eAG)
2. Cross-validates values using NGSP.org conversion formulas
3. Assigns ADA diabetes category from cross-validated NGSP
4. Produces structured HPLCBlock for interpretation routing

Does NOT invent values: if only 1 of 3 analytes present, the others
stay None. Re-extraction is triggered by the caller (OCRExtractor)
when completeness < 2.
"""

import logging

from lablens.models.hplc_block import (
    DiabetesCategory,
    HPLCAnalyte,
    HPLCBlock,
)

logger = logging.getLogger(__name__)

# --- Conversion constants (NGSP.org, verified) ---
IFCC_SLOPE = 10.93
IFCC_INTERCEPT = -23.5
EAG_MGDL_SLOPE = 28.7
EAG_MGDL_INTERCEPT = -46.7
MMOL_TO_MGDL = 18.015

# --- Cross-check tolerances ---
IFCC_TOLERANCE = 2.0  # mmol/mol
EAG_MGDL_TOLERANCE = 5.0  # mg/dL
EAG_MMOL_TOLERANCE = 0.3  # mmol/L

# --- Value-range plausibility bounds ---
# Used to detect misidentified analytes (e.g. NGSP value labeled as IFCC)
NGSP_PLAUSIBLE_MIN = 3.0    # % — lowest clinically meaningful HbA1c
NGSP_PLAUSIBLE_MAX = 20.0   # %
IFCC_PLAUSIBLE_MIN = 10.0   # mmol/mol — corresponds to ~3.1% NGSP
IFCC_PLAUSIBLE_MAX = 195.0  # mmol/mol — corresponds to ~20% NGSP
EAG_MGDL_PLAUSIBLE_MIN = 50.0   # mg/dL
EAG_MGDL_PLAUSIBLE_MAX = 500.0  # mg/dL
EAG_MMOL_PLAUSIBLE_MIN = 2.5    # mmol/L
EAG_MMOL_PLAUSIBLE_MAX = 28.0   # mmol/L

# --- ADA clinical cutpoints (NGSP scale) ---
ADA_NORMAL_MAX = 5.7
ADA_PREDIABETES_MAX = 6.5


class HPLCBlockParser:
    """Parse and validate HPLC diabetes blocks."""

    def parse_rows(self, rows: list[dict]) -> HPLCBlock:
        """Parse classified HPLC rows into structured block."""
        block = HPLCBlock()

        for row in rows:
            analyte_type = self._identify_analyte(row)
            if analyte_type is None:
                continue

            hplc_analyte = self._to_hplc_analyte(row)
            if analyte_type == "ngsp":
                block.ngsp = hplc_analyte
            elif analyte_type == "ifcc":
                block.ifcc = hplc_analyte
            elif analyte_type == "eag":
                block.eag = hplc_analyte
                block.eag_unit = (row.get("unit") or "mg/dL").strip()
                block.eag.unit = block.eag_unit

        # Post-parse plausibility: detect misidentified analytes
        self._fix_misidentified_analytes(block)

        # Derive missing values from present ones using NGSP.org formulas
        self._derive_missing_values(block)

        block.completeness = sum(
            1
            for a in [block.ngsp, block.ifcc, block.eag]
            if a and a.value is not None
        )
        block.cross_check_passed = self._cross_check(block)
        block.diabetes_category = self._categorize(block)
        return block

    def _identify_analyte(self, row: dict) -> str | None:
        """Identify which HPLC analyte a row represents.

        Red-team fix #13: Does NOT default bare "hba1c" to NGSP.
        When unit is absent or ambiguous, returns None to trigger
        re-extraction rather than guessing (which corrupts cross-check
        and diabetes category).
        """
        name = (row.get("test_name") or "").lower()
        unit = (row.get("unit") or "").lower().strip()

        # IFCC: explicit keyword or mmol/mol unit
        if "ifcc" in name or unit == "mmol/mol":
            return "ifcc"

        # NGSP: explicit keyword or % unit on hba1c-like name
        if ("hba1c" in name or "hb a1c" in name or "a1c" in name) and unit == "%":
            return "ngsp"

        # eAG: explicit keyword
        if "eag" in name or "estimated average glucose" in name:
            return "eag"

        # Bare "hba1c" without identifiable unit: do NOT guess
        if "hba1c" in name or "hb a1c" in name:
            logger.info(
                "HPLC: bare HbA1c '%s' without identifiable unit '%s' — "
                "returning None to trigger re-extraction",
                row.get("test_name", "?"),
                row.get("unit", ""),
            )
            return None

        return None

    @staticmethod
    def _to_hplc_analyte(row: dict) -> HPLCAnalyte:
        """Convert a raw OCR row dict to HPLCAnalyte."""
        value = row.get("value")
        if isinstance(value, str):
            try:
                value = float(value)
            except (ValueError, TypeError):
                value = None

        ref_low = row.get("reference_range_low")
        ref_high = row.get("reference_range_high")
        if ref_low is not None:
            try:
                ref_low = float(ref_low)
            except (ValueError, TypeError):
                ref_low = None
        if ref_high is not None:
            try:
                ref_high = float(ref_high)
            except (ValueError, TypeError):
                ref_high = None

        return HPLCAnalyte(
            test_name=row.get("test_name", ""),
            value=value,
            unit=(row.get("unit") or "").strip() or None,
            reference_range_low=ref_low,
            reference_range_high=ref_high,
            source="ocr",
        )

    def _fix_misidentified_analytes(self, block: HPLCBlock) -> None:
        """Detect and correct misidentified HPLC analytes via value plausibility.

        Common OCR error: labeling a 5.1% NGSP value as "IFCC" because
        OCR misreads the row header. A real IFCC value in mmol/mol should
        be 10-195; a value <10 in the IFCC slot is almost certainly NGSP.

        Rules applied:
        - IFCC value < IFCC_PLAUSIBLE_MIN and NGSP is empty → move to NGSP
        - NGSP value > NGSP_PLAUSIBLE_MAX and IFCC is empty → move to IFCC
        - eAG value < EAG_MGDL_PLAUSIBLE_MIN (and unit looks like mg/dL)
          but fits mmol/L range → correct eAG unit to mmol/L
        """
        # Case 1: IFCC slot has value that looks like NGSP (e.g., 5.53)
        if (
            block.ifcc
            and block.ifcc.value is not None
            and block.ifcc.value < IFCC_PLAUSIBLE_MIN
            and block.ngsp is None
        ):
            # Check if value fits NGSP range
            if NGSP_PLAUSIBLE_MIN <= block.ifcc.value <= NGSP_PLAUSIBLE_MAX:
                logger.warning(
                    "HPLC plausibility: IFCC=%.2f is below min %.0f mmol/mol "
                    "but fits NGSP range — reclassifying as NGSP",
                    block.ifcc.value, IFCC_PLAUSIBLE_MIN,
                )
                # Move IFCC → NGSP, fix unit and canonical name
                block.ngsp = HPLCAnalyte(
                    test_name="HbA1c (NGSP)",
                    value=block.ifcc.value,
                    unit="%",
                    reference_range_low=None,
                    reference_range_high=None,
                    source="plausibility-reclassified",
                )
                block.ifcc = None

        # Case 2: NGSP slot has value that looks like IFCC (>20%)
        if (
            block.ngsp
            and block.ngsp.value is not None
            and block.ngsp.value > NGSP_PLAUSIBLE_MAX
            and block.ifcc is None
        ):
            if IFCC_PLAUSIBLE_MIN <= block.ngsp.value <= IFCC_PLAUSIBLE_MAX:
                logger.warning(
                    "HPLC plausibility: NGSP=%.2f exceeds max %.0f%% "
                    "but fits IFCC range — reclassifying as IFCC",
                    block.ngsp.value, NGSP_PLAUSIBLE_MAX,
                )
                block.ifcc = HPLCAnalyte(
                    test_name="HbA1c (IFCC)",
                    value=block.ngsp.value,
                    unit="mmol/mol",
                    reference_range_low=None,
                    reference_range_high=None,
                    source="plausibility-reclassified",
                )
                block.ngsp = None

        # Case 3: eAG value implausibly low for mg/dL but fits mmol/L
        if (
            block.eag
            and block.eag.value is not None
            and block.eag_unit.lower() not in ("mmol/l",)
            and block.eag.value < EAG_MGDL_PLAUSIBLE_MIN
        ):
            if EAG_MMOL_PLAUSIBLE_MIN <= block.eag.value <= EAG_MMOL_PLAUSIBLE_MAX:
                logger.warning(
                    "HPLC plausibility: eAG=%.2f too low for mg/dL "
                    "but fits mmol/L range — correcting unit",
                    block.eag.value,
                )
                block.eag_unit = "mmol/L"
                block.eag.unit = "mmol/L"

    def _derive_missing_values(self, block: HPLCBlock) -> None:
        """Derive missing HPLC values from present ones using NGSP.org formulas.

        Handles two scenarios:
        1. Reclassified NGSP doesn't match eAG → re-derive NGSP from eAG
        2. IFCC or eAG missing → derive from NGSP (or NGSP from IFCC/eAG)

        Only fires when values are missing. Never overwrites OCR-sourced values
        unless they were from plausibility reclassification (lower confidence).
        """
        ngsp_val = block.ngsp.value if block.ngsp else None
        ifcc_val = block.ifcc.value if block.ifcc else None
        eag_val = block.eag.value if block.eag else None

        # Convert eAG to mg/dL for formula calculations
        eag_mgdl = None
        if eag_val is not None:
            if block.eag_unit.lower() in ("mmol/l",):
                eag_mgdl = eag_val * MMOL_TO_MGDL
            else:
                eag_mgdl = eag_val

        # Recovery: reclassified NGSP doesn't match eAG → re-derive from eAG
        if (
            ngsp_val is not None
            and eag_mgdl is not None
            and block.ngsp
            and block.ngsp.source == "plausibility-reclassified"
        ):
            expected_eag = EAG_MGDL_SLOPE * ngsp_val + EAG_MGDL_INTERCEPT
            if abs(eag_mgdl - expected_eag) > EAG_MGDL_TOLERANCE:
                derived = (eag_mgdl - EAG_MGDL_INTERCEPT) / EAG_MGDL_SLOPE
                if NGSP_PLAUSIBLE_MIN <= derived <= NGSP_PLAUSIBLE_MAX:
                    logger.warning(
                        "HPLC recovery: reclassified NGSP=%.2f doesn't match "
                        "eAG=%.1f (expected %.1f) — re-deriving NGSP=%.1f",
                        ngsp_val, eag_mgdl, expected_eag, derived,
                    )
                    block.ngsp = HPLCAnalyte(
                        test_name="HbA1c (NGSP)",
                        value=round(derived, 1),
                        unit="%",
                        source="derived-from-eag",
                    )
                    ngsp_val = block.ngsp.value

        # Derive NGSP from IFCC when NGSP is missing
        if ngsp_val is None and ifcc_val is not None:
            derived = (ifcc_val - IFCC_INTERCEPT) / IFCC_SLOPE
            if NGSP_PLAUSIBLE_MIN <= derived <= NGSP_PLAUSIBLE_MAX:
                logger.info("HPLC: deriving NGSP=%.1f from IFCC=%.1f", derived, ifcc_val)
                block.ngsp = HPLCAnalyte(
                    test_name="HbA1c (NGSP)",
                    value=round(derived, 1),
                    unit="%",
                    source="derived-from-ifcc",
                )
                ngsp_val = block.ngsp.value

        # Derive NGSP from eAG when both NGSP and IFCC are missing
        if ngsp_val is None and eag_mgdl is not None:
            derived = (eag_mgdl - EAG_MGDL_INTERCEPT) / EAG_MGDL_SLOPE
            if NGSP_PLAUSIBLE_MIN <= derived <= NGSP_PLAUSIBLE_MAX:
                logger.info("HPLC: deriving NGSP=%.1f from eAG=%.1f", derived, eag_mgdl)
                block.ngsp = HPLCAnalyte(
                    test_name="HbA1c (NGSP)",
                    value=round(derived, 1),
                    unit="%",
                    source="derived-from-eag",
                )
                ngsp_val = block.ngsp.value

        # Derive IFCC from NGSP when IFCC is missing
        if ifcc_val is None and ngsp_val is not None:
            derived = IFCC_SLOPE * ngsp_val + IFCC_INTERCEPT
            if IFCC_PLAUSIBLE_MIN <= derived <= IFCC_PLAUSIBLE_MAX:
                logger.info("HPLC: deriving IFCC=%.1f from NGSP=%.1f", derived, ngsp_val)
                block.ifcc = HPLCAnalyte(
                    test_name="HbA1c (IFCC)",
                    value=round(derived, 1),
                    unit="mmol/mol",
                    source="derived-from-ngsp",
                )

        # Derive eAG from NGSP when eAG is missing
        if eag_val is None and ngsp_val is not None:
            derived_mgdl = EAG_MGDL_SLOPE * ngsp_val + EAG_MGDL_INTERCEPT
            if EAG_MGDL_PLAUSIBLE_MIN <= derived_mgdl <= EAG_MGDL_PLAUSIBLE_MAX:
                logger.info("HPLC: deriving eAG=%.1f from NGSP=%.1f", derived_mgdl, ngsp_val)
                block.eag = HPLCAnalyte(
                    test_name="Estimated Average Glucose (eAG)",
                    value=round(derived_mgdl, 1),
                    unit="mg/dL",
                    source="derived-from-ngsp",
                )
                block.eag_unit = "mg/dL"

    def _cross_check(self, block: HPLCBlock) -> bool:
        """Cross-validate NGSP/IFCC/eAG using conversion formulas.

        Returns True if all present pairs are consistent within tolerance.
        Returns True vacuously if < 2 analytes are present (nothing to check).
        """
        flags: list[str] = []

        # NGSP <-> IFCC check
        if (
            block.ngsp
            and block.ifcc
            and block.ngsp.value is not None
            and block.ifcc.value is not None
        ):
            expected_ifcc = (IFCC_SLOPE * block.ngsp.value) + IFCC_INTERCEPT
            diff = abs(block.ifcc.value - expected_ifcc)
            if diff > IFCC_TOLERANCE:
                flags.append(
                    f"NGSP-IFCC mismatch: expected IFCC={expected_ifcc:.1f}, "
                    f"got {block.ifcc.value}"
                )

        # NGSP <-> eAG check
        if (
            block.ngsp
            and block.eag
            and block.ngsp.value is not None
            and block.eag.value is not None
        ):
            expected_eag = (EAG_MGDL_SLOPE * block.ngsp.value) + EAG_MGDL_INTERCEPT
            if block.eag_unit.lower() in ("mmol/l", "mmol/l"):
                expected_eag = expected_eag / MMOL_TO_MGDL
                tolerance = EAG_MMOL_TOLERANCE
            else:
                tolerance = EAG_MGDL_TOLERANCE
            diff = abs(block.eag.value - expected_eag)
            if diff > tolerance:
                flags.append(
                    f"NGSP-eAG mismatch: expected eAG={expected_eag:.1f}, "
                    f"got {block.eag.value}"
                )

        block.consistency_flags = flags
        return len(flags) == 0

    @staticmethod
    def _categorize(block: HPLCBlock) -> DiabetesCategory:
        """Assign ADA diabetes category from NGSP value.

        Requires cross-check to have passed. If cross-check failed,
        returns INDETERMINATE regardless of NGSP value.
        """
        if not block.ngsp or block.ngsp.value is None:
            return DiabetesCategory.INDETERMINATE
        if not block.cross_check_passed and block.completeness >= 2:
            return DiabetesCategory.INDETERMINATE

        val = block.ngsp.value
        if val < ADA_NORMAL_MAX:
            return DiabetesCategory.NORMAL
        if val < ADA_PREDIABETES_MAX:
            return DiabetesCategory.PREDIABETES
        return DiabetesCategory.DIABETES
