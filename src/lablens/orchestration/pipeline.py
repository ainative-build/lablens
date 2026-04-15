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

    async def analyze(self, pdf_bytes: bytes, language: str = "en") -> dict:
        """Full pipeline: PDF → extraction → mapping → interpretation → explanation."""

        # Stage 1: Extract
        from lablens.extraction.ocr_extractor import OCRExtractor

        extractor = OCRExtractor(self.settings)
        report = await extractor.extract_from_pdf(pdf_bytes, language=language)
        logger.info(
            "Extracted %d values from %d pages", len(report.values), report.page_count
        )

        # Stage 2: Map terminology + normalize units
        from lablens.extraction.alias_registry import AliasRegistry
        from lablens.extraction.terminology_mapper import TerminologyMapper
        from lablens.extraction.unit_normalizer import UnitNormalizer

        mapper = TerminologyMapper(AliasRegistry())
        normalizer = UnitNormalizer()

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
            if isinstance(vdict["value"], (int, float)) and v.unit:
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

        return {
            "values": [vars(v) for v in final.interpreted_values],
            "explanations": [vars(e) for e in final.explanations],
            "panels": [vars(p) for p in final.panels] if final.panels else [],
            "coverage_score": final.coverage_score,
            "disclaimer": final.disclaimer,
            "language": final.language,
        }
