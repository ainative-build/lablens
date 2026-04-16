"""Parallel context assembly from graph + vector sources.

Section-aware: routes enrichment queries based on section_type
to get tailored context for HPLC, screening, and standard values.
"""

import asyncio

from lablens.retrieval.models import EnrichedContext, GraphContext


# Section-specific vector query overrides
_VECTOR_QUERY_OVERRIDES: dict[str, str] = {
    "hplc_diabetes_block": (
        "HbA1c diabetes monitoring hemoglobin A1c "
        "patient education blood sugar management"
    ),
    "screening_attachment": (
        "ctDNA liquid biopsy cancer screening results "
        "meaning limitations false negative"
    ),
}


class ContextAssembler:
    """Merge graph + vector context for a lab test, section-aware."""

    def __init__(self, graph_retriever, vector_retriever):
        self.graph = graph_retriever
        self.vector = vector_retriever

    async def enrich(
        self,
        test_name: str,
        loinc_code: str | None,
        section_type: str = "standard_lab_table",
    ) -> EnrichedContext:
        """Section-aware parallel retrieval from graph + vector."""
        graph_task = self._get_graph_context(loinc_code, section_type)
        vector_task = self._get_vector_context(
            test_name, loinc_code, section_type
        )

        graph_ctx, vector_ctx = await asyncio.gather(graph_task, vector_task)
        return EnrichedContext(graph=graph_ctx, vector=vector_ctx)

    async def _get_graph_context(
        self, loinc_code: str | None, section_type: str
    ) -> GraphContext:
        """Section-aware graph retrieval."""
        if not loinc_code:
            return GraphContext()
        if section_type == "hplc_diabetes_block":
            if hasattr(self.graph, "get_glycemic_context"):
                return await self.graph.get_glycemic_context(loinc_code)
        if section_type == "screening_attachment":
            if hasattr(self.graph, "get_screening_context"):
                return await self.graph.get_screening_context(loinc_code)
        return await self.graph.get_context(loinc_code)

    async def _get_vector_context(
        self, test_name: str, loinc_code: str | None, section_type: str
    ):
        """Section-aware vector retrieval with tailored queries."""
        query_override = _VECTOR_QUERY_OVERRIDES.get(section_type)
        return await self.vector.get_education(
            test_name, loinc_code, query_override=query_override
        )
