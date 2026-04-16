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

    @staticmethod
    def _normalize_micro(text: str) -> str:
        """Normalize unicode micro sign variants (µ U+00B5 ↔ μ U+03BC)."""
        return text.replace("\u00b5", "\u03bc")  # µ → μ

    @staticmethod
    def _dedupe_analytes(values: list) -> tuple[list, list]:
        """Deduplicate analytes with same name in multiple units.

        When the source PDF reports the same test in two unit systems
        (e.g. Free T4 in pmol/L and ng/dL), keep the higher-confidence
        row and move the alternate to an audit list.

        Also normalizes micro-symbol variants (µ/μ) to detect TSH dupes.

        Returns (canonical_values, alternate_values).
        """
        import unicodedata

        def norm_key(v) -> str:
            name = (v.test_name or "").lower().strip()
            # Normalize unicode (µ → μ)
            name = name.replace("\u00b5", "\u03bc")
            # Strip bracketed/parenthesized qualifiers for grouping
            import re
            name = re.sub(r"\s*\[.*?\]", "", name)
            name = re.sub(r"\s*\(.*?\)", "", name)
            name = re.sub(r"[*#]", "", name)
            return name.strip()

        # Confidence ranking: high > medium > low
        conf_rank = {"high": 3, "medium": 2, "low": 1}
        # Range source trust hierarchy
        range_trust = {
            "lab-provided-validated": 5,
            "curated-fallback": 4,
            "unit-corrected": 3,
            "lab-provided-suspicious": 2,
            "range-text": 1,
            "ocr-flag-fallback": 0,
            "no-range": 0,
        }

        # Group by normalized name, then split by LOINC only when
        # multiple distinct non-empty LOINCs exist (genuinely different tests).
        # Exempt HPLC values — NGSP/IFCC/eAG are intentionally different
        # representations and must never be collapsed.
        canonical = []
        alternates = []
        name_groups: dict[str, list] = {}
        for v in values:
            section = getattr(v, "section_type", None) or ""
            if section == "hplc_diabetes_block":
                canonical.append(v)  # bypass grouping entirely
                continue
            name_groups.setdefault(norm_key(v), []).append(v)

        # Split name groups by distinct LOINCs when needed
        groups: dict[str, list] = {}
        for name, items in name_groups.items():
            distinct = {v.loinc_code for v in items if v.loinc_code}
            if len(distinct) > 1:
                # Multiple distinct LOINCs → genuinely different tests
                for v in items:
                    loinc = v.loinc_code or ""
                    groups.setdefault(f"{name}|{loinc}", []).append(v)
            else:
                # 0 or 1 distinct LOINC → same test, group for dedup
                groups.setdefault(name, []).extend(items)
        for key, group in groups.items():
            if len(group) == 1:
                canonical.append(group[0])
                continue
            # Rank: confidence → unit present → range_source trust → unit_confidence
            # A row missing its unit is fundamentally unverifiable — penalize it
            # regardless of range source trust (fixes Vitamin D empty-unit row
            # wrongly beating the ng/mL curated-fallback row).
            group.sort(key=lambda v: (
                conf_rank.get(v.confidence, 0),
                1 if (getattr(v, "unit", "") or "").strip() else 0,
                range_trust.get(v.range_source, 0),
                conf_rank.get(
                    getattr(v, "unit_confidence", "high"), 0
                ),
            ), reverse=True)
            canonical.append(group[0])
            alternates.extend(group[1:])

        return canonical, alternates

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
                    "from '%s' gives %s — applying correction.",
                    vdict.get("test_name", "?"), value, reported_unit,
                    cur_low, cur_high, canonical_unit,
                    conv["from"], converted,
                )
                # Apply the correction: convert to canonical unit
                vdict["value"] = converted
                vdict["unit"] = canonical_unit
                vdict["unit_confidence"] = "medium"
                # Clear lab range — it was for the wrong unit system
                vdict["reference_range_low"] = None
                vdict["reference_range_high"] = None
                vdict["range_source"] = "unit-corrected"
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

        # Build HPLC category lookup for interpretation routing
        hplc_category_map = self._build_hplc_category_map(hplc_blocks)

        # Stage 1.5: Semantic verification (deterministic checks)
        from lablens.extraction.semantic_verifier import (
            SemanticVerifier,
            Verdict,
        )

        verifier = SemanticVerifier(
            api_key=self.settings.dashscope_api_key,
            verify_model=self.settings.dashscope_verify_model,
        )
        value_dicts = [v.model_dump() for v in report.values]
        verdicts = verifier.verify_batch(value_dicts)
        verification_verdicts = []
        for i, (vdict, vr) in enumerate(zip(value_dicts, verdicts)):
            vr.index = i
            vr.value_id = f"v{i}"
            verification_verdicts.append(vr)
            if vr.verdict == Verdict.MARK_INDETERMINATE:
                vdict["verification_verdict"] = "indeterminate"
                vdict["unit_confidence"] = "low"
            elif vr.verdict == Verdict.DOWNGRADE:
                vdict["verification_verdict"] = "downgraded"
                cur = vdict.get("unit_confidence", "high")
                if cur == "high":
                    vdict["unit_confidence"] = "medium"
            elif vr.verdict == Verdict.RETRY:
                # Deterministic RETRY: downgrade since no inline re-extraction
                vdict["verification_verdict"] = "retry_exhausted"
                vdict["unit_confidence"] = "low"
            elif vr.verdict == Verdict.ACCEPT_WITH_WARNING:
                vdict["verification_verdict"] = "accepted_with_warning"
            else:
                vdict["verification_verdict"] = "accepted"

        logger.info(
            "Verified %d values: %d accepted, %d warned, "
            "%d downgraded, %d indeterminate",
            len(verdicts),
            sum(1 for v in verdicts if v.verdict == Verdict.ACCEPT),
            sum(1 for v in verdicts
                if v.verdict == Verdict.ACCEPT_WITH_WARNING),
            sum(1 for v in verdicts if v.verdict == Verdict.DOWNGRADE),
            sum(1 for v in verdicts if v.verdict == Verdict.MARK_INDETERMINATE),
        )

        # Stage 2: Map terminology + normalize units
        from lablens.extraction.alias_registry import AliasRegistry
        from lablens.extraction.health_topic_mapper import get_health_topic
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
        for i, vdict in enumerate(value_dicts):
            loinc_code, match_conf = mapper.match(vdict["test_name"])
            vdict["loinc_code"] = loinc_code

            # Stage 2.6: tag health topic for L2 grouping. Carried through
            # to the InterpretedResult after interpretation. inferred=True
            # is logged for taxonomy-coverage instrumentation.
            topic_id, topic_inferred = get_health_topic(
                loinc_code, vdict.get("test_name", "")
            )
            vdict["health_topic"] = topic_id
            vdict["topic_inferred"] = topic_inferred

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
            unit_str = (vdict.get("unit") or "").strip()
            unit_present = bool(unit_str)
            if isinstance(vdict["value"], (int, float)) and unit_present:
                if has_lab_range:
                    # Keep original units — value and ranges are already consistent
                    vdict.setdefault("unit_confidence", "high")
                else:
                    # Convert to canonical unit for curated fallback comparison
                    norm = normalizer.normalize(
                        loinc_code or "", float(vdict["value"]), unit_str
                    )
                    # Post-conversion plausibility guard: if conversion
                    # produced an implausible result, revert to original
                    if norm.converted:
                        from lablens.extraction.semantic_verifier import (
                            check_unit_value_plausibility,
                        )
                        from lablens.extraction.plausibility_validator import (
                            HUMAN_POSSIBLE_BOUNDS,
                        )
                        conv_ok = check_unit_value_plausibility(norm.value, norm.unit)
                        # LOINC-specific tighter check overrides generic unit check
                        loinc_tmp = loinc_code or ""
                        if loinc_tmp and loinc_tmp in HUMAN_POSSIBLE_BOUNDS:
                            lo, hi = HUMAN_POSSIBLE_BOUNDS[loinc_tmp]
                            conv_ok = conv_ok and (lo <= norm.value <= hi)
                        if not conv_ok:
                            orig_ok = check_unit_value_plausibility(
                                norm.original_value, norm.original_unit
                            )
                            if orig_ok:
                                logger.warning(
                                    "Post-conversion plausibility fail for %s: "
                                    "%s %s → %s %s. Reverting.",
                                    vdict.get("test_name", "?"),
                                    norm.original_value, norm.original_unit,
                                    norm.value, norm.unit,
                                )
                                norm = type(norm)(
                                    value=norm.original_value,
                                    unit=norm.original_unit,
                                    original_value=norm.original_value,
                                    original_unit=norm.original_unit,
                                    converted=False,
                                    confidence="low",
                                )
                            else:
                                # Both bad — keep converted (right unit system)
                                norm = type(norm)(
                                    value=norm.value,
                                    unit=norm.unit,
                                    original_value=norm.original_value,
                                    original_unit=norm.original_unit,
                                    converted=norm.converted,
                                    confidence="low",
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
                            vdict["test_name"], unit_str,
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
                    vdict["test_name"],
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

            # Cross-unit mismatch: value and range individually plausible
            # but in different unit systems (e.g., val=2.26 mmol/L, range=[8.5-10.5] mg/dL)
            if (
                isinstance(vdict["value"], (int, float))
                and has_lab_range
                and vdict.get("reference_range_low") is not None
                and vdict.get("reference_range_high") is not None
            ):
                _low = vdict["reference_range_low"]
                _high = vdict["reference_range_high"]
                _mid = (_low + _high) / 2
                if _mid > 0:
                    _ratio = float(vdict["value"]) / _mid
                    if _ratio > 20 or _ratio < 0.05:
                        logger.info(
                            "Value/range unit mismatch for %s: val=%s range=[%s-%s] "
                            "ratio=%.2f — clearing range",
                            vdict.get("test_name", "?"), vdict["value"],
                            _low, _high, _ratio,
                        )
                        vdict["reference_range_low"] = None
                        vdict["reference_range_high"] = None
                        vdict["range_trust"] = "low"
                        has_lab_range = False

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
                name_lower = (vdict.get("test_name") or "").lower()
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
                    (vdict.get("test_name") or "").lower().strip()
                )
                if cat:
                    vdict["hplc_diabetes_category"] = cat

            confidences[i] = match_conf
            enriched_values.append(vdict)

        logger.info("Mapped %d values to LOINC codes", len(enriched_values))

        # Stage 2.5: Post-enrichment verdict refinement
        # The Stage 1.5 verifier runs on raw OCR output, before quality
        # metadata (unit_confidence, range_source) is computed in Stage 2.
        # Now re-evaluate verdicts using the enriched metadata.
        from lablens.extraction.semantic_verifier import (
            deterministic_checks as det_checks_fn,
        )

        downgraded_count = 0
        for i, vdict in enumerate(enriched_values):
            # Re-run deterministic checks with quality metadata now available
            recheck = det_checks_fn(vdict, vdict.get("section_type", "standard_lab_table"))
            vr = verification_verdicts[i] if i < len(verification_verdicts) else None
            if vr and recheck.verdict not in (
                Verdict.ACCEPT, Verdict.ACCEPT_WITH_WARNING
            ):
                # Quality metadata triggered a non-accept verdict
                if recheck.verdict == Verdict.MARK_INDETERMINATE:
                    vdict["verification_verdict"] = "indeterminate"
                    vdict["unit_confidence"] = "low"
                    vr.verdict = Verdict.MARK_INDETERMINATE
                    vr.reasons.extend(recheck.reasons)
                elif recheck.verdict in (Verdict.DOWNGRADE, Verdict.RETRY):
                    cur_verdict = vdict.get("verification_verdict", "accepted")
                    if cur_verdict in ("accepted", "accepted_with_warning"):
                        vdict["verification_verdict"] = "downgraded"
                        vr.verdict = Verdict.DOWNGRADE
                    vr.reasons.extend(recheck.reasons)
                vr.checks_passed = recheck.checks_passed
                vr.checks_failed = recheck.checks_failed
                downgraded_count += 1

        if downgraded_count > 0:
            logger.info(
                "Post-enrichment quality check: %d verdicts refined",
                downgraded_count,
            )

        # Stage 3: Interpret
        from lablens.interpretation.engine import InterpretationEngine

        engine = InterpretationEngine()
        interpreted = engine.interpret_report(enriched_values, confidences)
        logger.info(
            "Interpreted: %d total, %d abnormal",
            interpreted.total_parsed,
            interpreted.total_abnormal,
        )

        # Stamp health_topic onto each interpreted row (engine doesn't
        # currently carry the field through). Index-aligned with
        # enriched_values since interpret_report iterates in-order.
        inferred_count = 0
        for idx, v in enumerate(interpreted.values):
            if idx < len(enriched_values):
                v.health_topic = enriched_values[idx].get("health_topic", "other")
                if enriched_values[idx].get("topic_inferred"):
                    inferred_count += 1
            else:
                v.health_topic = "other"
        if interpreted.values:
            logger.info(
                "Tagged %d values with health topics (%d inferred via family)",
                len(interpreted.values), inferred_count,
            )

        # Stage 3.5: Pre-explanation consistency enforcement
        # Values whose direction was derived from weak evidence (OCR flag
        # fallback with no numeric range) produce contradictions: the
        # structured row says "high" but the LLM explanation says "cannot
        # classify." Resolve by downgrading direction to indeterminate
        # while preserving the OCR flag hint for audit transparency.
        #
        # Also refine verification verdicts now that range_source is
        # available (verifier ran before interpretation set this field).
        _WEAK_DIRECTION_SOURCES = {"ocr-flag-fallback"}
        _CAUTION_RANGE_SOURCES = {"range-text", "lab-provided-suspicious"}
        for idx, v in enumerate(interpreted.values):
            # Direction consistency: weak source → indeterminate
            if (
                v.range_source in _WEAK_DIRECTION_SOURCES
                and v.reference_range_low is None
                and v.reference_range_high is None
                and v.direction not in ("in-range", "indeterminate")
            ):
                v.source_flag = v.direction[0].upper() if v.direction else None
                v.direction = "indeterminate"
                v.severity = "normal"
                v.confidence = "low"

            # Post-interpretation verdict refinement: upgrade accepted
            # to accepted_with_warning for caution-tier range sources
            # or standalone low confidence
            if v.verification_verdict == "accepted":
                has_caution = (
                    v.range_source in _CAUTION_RANGE_SOURCES
                    or v.confidence == "low"
                )
                if has_caution:
                    v.verification_verdict = "accepted_with_warning"
                    # Update audit verdict too
                    if idx < len(verification_verdicts):
                        vr = verification_verdicts[idx]
                        if vr.verdict == Verdict.ACCEPT:
                            vr.verdict = Verdict.ACCEPT_WITH_WARNING
                            if v.range_source in _CAUTION_RANGE_SOURCES:
                                vr.reasons.append(
                                    f"[warn] range_source="
                                    f"{v.range_source}"
                                )
                            if v.confidence == "low":
                                vr.reasons.append(
                                    f"[warn] confidence=low"
                                )

        # Stage 3.55: Static notes for in-range qualitative results
        # Categorical (blood type) and expected-positive in-range (HBsAb immune)
        # get a brief patient-facing note without an LLM call.
        for v in interpreted.values:
            et = v.evidence_trace or {}
            method = et.get("interpretation_method", "")
            if not method.startswith("qualitative"):
                continue
            if v.direction != "in-range":
                continue
            hint = et.get("explanation_hint", "")
            if not hint:
                continue
            # Expected-positive in-range: patient should know immunity is good
            if any(w in hint.lower() for w in ("immunity", "immune")):
                v.evidence_trace["qualitative_note"] = (
                    "This result indicates protection/immunity — "
                    "this is expected and reassuring."
                )
            # Categorical: informational only
            elif "informational" in hint.lower():
                v.evidence_trace["qualitative_note"] = hint

        # Stage 3.6: Deduplicate analytes with same name in multiple units
        # Source PDFs sometimes list Free T4 in pmol/L AND ng/dL, or
        # TSH with µ vs μ micro symbols. Keep lab-validated row; move
        # alternate to audit.
        interpreted.values, deduped_alternates = self._dedupe_analytes(
            interpreted.values
        )
        if deduped_alternates:
            logger.info(
                "Deduped %d duplicate analyte(s)", len(deduped_alternates)
            )

        # Stage 4: Explain
        from lablens.retrieval.context_assembler import ContextAssembler
        from lablens.retrieval.explanation_generator import ExplanationGenerator
        from lablens.retrieval.graph_retriever import NullGraphRetriever
        from lablens.retrieval.vector_retriever import NullVectorRetriever

        assembler = ContextAssembler(NullGraphRetriever(), NullVectorRetriever())
        generator = ExplanationGenerator(self.settings, assembler)
        final = await generator.generate_report(
            interpreted, language,
            hplc_blocks=hplc_blocks,
            screening_results=screening_results,
        )

        # Canonicalize screening results (dedup organs, structure followup)
        from lablens.extraction.screening_parser import (
            canonicalize_screening,
        )

        for sr in screening_results:
            canonicalize_screening(sr)

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

        # Build value output — source_flag is audit-only, not semantic
        def _value_dict(v):
            d = vars(v)
            sf = d.pop("source_flag", None)
            if sf:
                d.setdefault("evidence_trace", {})["source_flag"] = sf
            return d

        # Phase 1a: pre-build topic_groups so frontend (Phase 2) and Q&A
        # (Phase 3) consume identical pre-grouped output.
        from lablens.retrieval.topic_grouper import build_topic_groups

        topic_groups = build_topic_groups(final.interpreted_values)
        # Re-apply source_flag normalization on grouped results so they
        # match the flat "values" list shape exactly.
        for grp in topic_groups:
            normalized: list[dict] = []
            for d in grp.results:
                d = dict(d)
                sf = d.pop("source_flag", None)
                if sf:
                    d.setdefault("evidence_trace", {})["source_flag"] = sf
                normalized.append(d)
            grp.results = normalized

        # Phase 1b: build executive summary ONCE here.  Memoized into
        # result["summary"] — never recomputed on poll/fetch.  LLM headline
        # is generated for non-green status only; rejected → deterministic
        # fallback.  Always safe.
        from lablens.retrieval.report_summarizer import (
            HeadlineGenerator,
            build_summary,
        )

        headline_gen = HeadlineGenerator(self.settings)
        summary = await build_summary(
            final.interpreted_values, headline_gen=headline_gen
        )

        result = {
            "values": [_value_dict(v) for v in final.interpreted_values],
            "topic_groups": [g.model_dump() for g in topic_groups],
            "summary": summary.model_dump(),
            "screening_results": screening_output,
            "explanations": [vars(e) for e in final.explanations],
            "panels": [vars(p) for p in final.panels] if final.panels else [],
            "coverage_score": final.coverage_score,
            "explanation_quality": final.explanation_quality,
            "disclaimer": final.disclaimer,
            "language": final.language,
        }
        # Audit: HPLC + verification verdicts
        audit: dict = {}
        if audit_hplc:
            audit["hplc_blocks"] = audit_hplc
        if verification_verdicts:
            audit["verification_verdicts"] = [
                {
                    "index": vr.index,
                    "value_id": vr.value_id,
                    "verdict": vr.verdict.value,
                    "provenance": vr.provenance,
                    "reasons": vr.reasons,
                    "checks_passed": vr.checks_passed,
                    "checks_failed": vr.checks_failed,
                }
                for vr in verification_verdicts
            ]
        if deduped_alternates:
            audit["deduped_alternates"] = [
                vars(v) for v in deduped_alternates
            ]
        if audit:
            result["audit"] = audit
        return result
