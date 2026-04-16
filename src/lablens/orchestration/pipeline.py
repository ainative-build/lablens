"""Analysis pipeline — orchestrates extraction → mapping → interpretation → explanation.

PlainPipeline is the primary MVP implementation (direct async calls).
AgentScope wrapper can be added later if needed.
"""

import logging
from typing import Protocol

from lablens.config import Settings

logger = logging.getLogger(__name__)


class PipelineProtocol(Protocol):
    async def analyze(self, pdf_bytes: bytes, language: str = "en") -> dict: ...


class PlainPipeline:
    """Direct async pipeline without AgentScope dependency."""

    def __init__(self, settings: Settings):
        self.settings = settings

    _cached_rules: dict | None = None

    @staticmethod
    def _build_hplc_category_map(hplc_blocks: list) -> dict[str, str]:
        """Build test_name → diabetes_category lookup from HPLCBlocks.

        Maps each analyte's lowercase test_name to the block's
        cross-validated diabetes_category. If cross-check failed,
        all analytes map to "indeterminate".
        """
        cat_map: dict[str, str] = {}
        for block in hplc_blocks:
            if block.cross_check_passed:
                cat = block.diabetes_category.value
            else:
                cat = "indeterminate"
            for attr in ("ngsp", "ifcc", "eag"):
                analyte = getattr(block, attr)
                if analyte and analyte.test_name:
                    key = analyte.test_name.lower().strip()
                    cat_map[key] = cat
        return cat_map

    @classmethod
    def _check_unit_misreport(
        cls, vdict: dict, loinc_code: str | None, normalizer
    ) -> dict:
        """Detect OCR unit misreport via curated range plausibility.

        If value with reported unit is >10x outside curated range but converting
        from an alternative unit brings it into plausible range, flag low confidence.
        Example: HDL-C=0.92 "mg/dL" — actually mmol/L (0.92×38.67=35.6 mg/dL).
        """
        if not loinc_code:
            return vdict

        from lablens.knowledge.rules_loader import get_rule, load_all_rules

        if cls._cached_rules is None:
            cls._cached_rules = load_all_rules()
        rule = get_rule(loinc_code, cls._cached_rules)
        if not rule:
            return vdict

        ranges = rule.get("reference_ranges", [])
        if not ranges:
            return vdict

        cur_low = ranges[0]["low"]
        cur_high = ranges[0]["high"]
        value = float(vdict["value"])

        # Check if value is implausibly outside curated range (>5x from bounds)
        if cur_low > 0 and value < cur_low / 5:
            pass  # Implausibly low — try conversion
        elif cur_high > 0 and value > cur_high * 5:
            pass  # Implausibly high — try conversion
        else:
            return vdict  # Value is in plausible range for reported unit

        # Value is wildly implausible — check if any conversion would fix it
        conv_data = normalizer._conversions.get(loinc_code)
        if not conv_data:
            # No conversion available — just drop confidence
            vdict["unit_confidence"] = "low"
            return vdict

        reported_unit = vdict.get("unit", "")
        canonical_unit = conv_data.get("canonical_unit", "")

        for conv in conv_data.get("conversions", []):
            converted = round(value * conv["factor"], 4)
            # Check if converted value is in plausible range (within 50% of bounds)
            plausible_low = cur_low * 0.5 if cur_low > 0 else float("-inf")
            if plausible_low <= converted <= cur_high * 2:
                logger.warning(
                    "Unit misreport detected for %s: value=%s '%s' is "
                    "implausible for curated [%s-%s] %s, but converting "
                    "from '%s' gives %s — flagging low confidence.",
                    vdict.get("test_name", "?"), value, reported_unit,
                    cur_low, cur_high, canonical_unit,
                    conv["from"], converted,
                )
                vdict["unit_confidence"] = "low"
                return vdict

        return vdict

    async def analyze(self, pdf_bytes: bytes, language: str = "en") -> dict:
        """Full pipeline: PDF → extraction → mapping → interpretation → explanation."""

        # Stage 1: Extract
        from lablens.extraction.ocr_extractor import OCRExtractor

        extractor = OCRExtractor(self.settings)
        report, page_images, hplc_blocks, screening_results = (
            await extractor.extract_from_pdf(pdf_bytes, language=language)
        )
        logger.info(
            "Extracted %d values, %d screening from %d pages",
            len(report.values), len(screening_results), report.page_count,
        )
        # page_images kept for Phase 4 semantic verifier (not used yet)

        # Build HPLC category lookup for interpretation routing
        hplc_category_map = self._build_hplc_category_map(hplc_blocks)

        # Stage 2: Map terminology + normalize units
        from lablens.extraction.alias_registry import AliasRegistry
        from lablens.extraction.terminology_mapper import TerminologyMapper
        from lablens.extraction.unit_normalizer import UnitNormalizer

        from lablens.extraction.range_plausibility_checker import (
            RangePlausibilityChecker,
        )

        from lablens.knowledge.rules_loader import load_all_rules

        mapper = TerminologyMapper(AliasRegistry())
        normalizer = UnitNormalizer()
        plausibility_checker = RangePlausibilityChecker()

        if PlainPipeline._cached_rules is None:
            PlainPipeline._cached_rules = load_all_rules()

        enriched_values = []
        confidences = {}
        for i, v in enumerate(report.values):
            loinc_code, match_conf = mapper.match(v.test_name)
            vdict = v.model_dump()
            vdict["loinc_code"] = loinc_code

            # Convert numeric string values to float (OCR returns strings)
            raw_val = vdict["value"]
            if isinstance(raw_val, str):
                try:
                    raw_val = float(raw_val)
                    vdict["value"] = raw_val
                except ValueError:
                    pass  # Keep as string for qualitative values

            has_lab_range = (
                vdict.get("reference_range_low") is not None
                and vdict.get("reference_range_high") is not None
            )
            unit_present = v.unit and v.unit.strip()
            if isinstance(vdict["value"], (int, float)) and unit_present:
                if has_lab_range:
                    # Keep original units — value and ranges are already consistent
                    vdict["unit_confidence"] = "high"
                else:
                    # Convert to canonical unit for curated fallback comparison
                    norm = normalizer.normalize(
                        loinc_code or "", float(vdict["value"]), v.unit
                    )
                    vdict["value"] = norm.value
                    vdict["unit"] = norm.unit
                    vdict["unit_confidence"] = norm.confidence
                    # If conversion failed (low confidence), clear LOINC to prevent
                    # curated fallback range comparison with mismatched units
                    if norm.confidence == "low" and not norm.converted:
                        logger.warning(
                            "Unit mismatch for %s: %s not convertible to canonical. "
                            "Clearing LOINC to prevent curated range mismatch.",
                            v.test_name, v.unit,
                        )
                        vdict["loinc_code"] = None

                # Check for unit misreport: if value is implausibly far from
                # curated range, OCR may have reported the wrong unit
                if vdict.get("loinc_code"):
                    vdict = self._check_unit_misreport(
                        vdict, vdict["loinc_code"], normalizer
                    )
            # If no unit and no lab range, clear LOINC to prevent curated
            # fallback with unknown unit system (e.g. Free T4 in pmol/L vs ng/dL)
            if not unit_present and not has_lab_range and vdict.get("loinc_code"):
                logger.warning(
                    "No unit and no lab range for %s — clearing LOINC to "
                    "prevent curated fallback with unknown unit system.",
                    v.test_name,
                )
                vdict["loinc_code"] = None

            # Compute range_trust via analyte-family plausibility
            lc = vdict.get("loinc_code")
            curated_low, curated_high = None, None
            if lc:
                from lablens.knowledge.rules_loader import get_rule
                rule = get_rule(lc, PlainPipeline._cached_rules or {})
                if rule:
                    ranges = rule.get("reference_ranges", [])
                    if ranges:
                        curated_low = ranges[0]["low"]
                        curated_high = ranges[0]["high"]

            if isinstance(vdict["value"], (int, float)) and has_lab_range:
                vdict["range_trust"] = plausibility_checker.validate_range(
                    lc,
                    float(vdict["value"]),
                    vdict.get("reference_range_low"),
                    vdict.get("reference_range_high"),
                    vdict.get("unit"),
                    curated_ref_low=curated_low,
                    curated_ref_high=curated_high,
                )
            else:
                vdict["range_trust"] = "high"

            # Pass analyte category and decision-threshold flag
            vdict["analyte_category"] = plausibility_checker.get_category(lc)
            vdict["is_decision_threshold"] = (
                plausibility_checker.is_decision_threshold(lc)
            )

            # Fallback: detect decision-threshold HbA1c variants by name
            # when LOINC mapping fails (e.g., "HbA1c (NGSP)" not in alias
            # registry). Without this, the engine gate is bypassed and HbA1c
            # gets standard-range interpretation with OCR-grabbed ranges —
            # producing false "high/mild" from clinical cutpoints.
            #
            # NOTE: This targets glycated hemoglobin markers only, NOT the
            # entire hplc_diabetes_block. eAG and other HPLC-adjacent rows
            # are already covered by LOINC-based detection (53553-4 is in
            # decision_threshold_loinc_codes). Blanket section_type fallback
            # would over-degrade non-HbA1c rows in the HPLC block.
            if not vdict["is_decision_threshold"]:
                name_lower = (v.test_name or "").lower()
                if any(kw in name_lower for kw in (
                    "hba1c", "hb a1c", "hemoglobin a1c",
                    "glycated hemoglobin", "glycosylated hemoglobin",
                )):
                    vdict["is_decision_threshold"] = True

            vdict["restricted_flag"] = (
                plausibility_checker.is_restricted_flag_category(lc)
            )

            # HPLC interpretation routing: inject cross-validated category
            # so the engine bypasses standard range-selection for HPLC values
            if vdict.get("section_type") == "hplc_diabetes_block":
                vdict["is_decision_threshold"] = True
                cat = hplc_category_map.get(
                    (v.test_name or "").lower().strip()
                )
                if cat:
                    vdict["hplc_diabetes_category"] = cat

            confidences[i] = match_conf
            enriched_values.append(vdict)

        logger.info("Mapped %d values to LOINC codes", len(enriched_values))

        # Stage 3: Interpret
        from lablens.interpretation.engine import InterpretationEngine

        engine = InterpretationEngine()
        interpreted = engine.interpret_report(enriched_values, confidences)
        logger.info(
            "Interpreted: %d total, %d abnormal",
            interpreted.total_parsed,
            interpreted.total_abnormal,
        )

        # Stage 4: Explain
        from lablens.retrieval.context_assembler import ContextAssembler
        from lablens.retrieval.explanation_generator import ExplanationGenerator
        from lablens.retrieval.graph_retriever import NullGraphRetriever
        from lablens.retrieval.vector_retriever import NullVectorRetriever

        assembler = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
        generator = ExplanationGenerator(self.settings, assembler)
        final = await generator.generate_report(interpreted, language)

        # Build screening output (bypass interpretation — Contract D)
        screening_output = [
            {
                "test_type": s.test_type,
                "result_status": s.result_status.value,
                "signal_origin": s.signal_origin,
                "organs_screened": s.organs_screened,
                "limitations": s.limitations,
                "followup_recommendation": s.followup_recommendation,
                "confidence": s.confidence,
            }
            for s in screening_results
        ]

        # Build audit HPLC block summaries
        audit_hplc = []
        for hb in hplc_blocks:
            audit_hplc.append({
                "ngsp_value": hb.ngsp.value if hb.ngsp else None,
                "ifcc_value": hb.ifcc.value if hb.ifcc else None,
                "eag_value": hb.eag.value if hb.eag else None,
                "diabetes_category": hb.diabetes_category.value,
                "cross_check_passed": hb.cross_check_passed,
                "consistency_flags": hb.consistency_flags,
            })

        result = {
            "values": [vars(v) for v in final.interpreted_values],
            "screening_results": screening_output,
            "explanations": [vars(e) for e in final.explanations],
            "panels": [vars(p) for p in final.panels] if final.panels else [],
            "coverage_score": final.coverage_score,
            "disclaimer": final.disclaimer,
            "language": final.language,
        }
        if audit_hplc:
            result.setdefault("audit", {})["hplc_blocks"] = audit_hplc
        return result
