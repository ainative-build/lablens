"""Parallel context assembly from graph + vector sources."""

import asyncio

from lablens.retrieval.models import EnrichedContext, GraphContext


class ContextAssembler:
    """Merge graph + vector context for a lab test."""

    def __init__(self, graph_retriever, vector_retriever):
        self.graph = graph_retriever
        self.vector = vector_retriever

    async def enrich(
        self, test_name: str, loinc_code: str | None
    ) -> EnrichedContext:
        """Parallel retrieval from graph + vector."""
        graph_task = (
            self.graph.get_context(loinc_code)
            if loinc_code
            else self._empty_graph()
        )
        vector_task = self.vector.get_education(test_name, loinc_code)

        graph_ctx, vector_ctx = await asyncio.gather(graph_task, vector_task)
        return EnrichedContext(graph=graph_ctx, vector=vector_ctx)

    @staticmethod
    async def _empty_graph() -> GraphContext:
        return GraphContext()
