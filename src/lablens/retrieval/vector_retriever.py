"""Vector-based retrieval from DashVector.

Searches for patient education content related to lab tests.
Gracefully returns empty context when DashVector is unavailable.
"""

import logging

from lablens.knowledge.dashvector_client import DashVectorClient
from lablens.retrieval.models import VectorContext

logger = logging.getLogger(__name__)


class VectorRetriever:
    """Retrieve education content from DashVector."""

    def __init__(self, dv_client: DashVectorClient):
        self.dv = dv_client

    async def get_education(
        self, test_name: str, loinc_code: str | None,
        query_override: str | None = None,
    ) -> VectorContext:
        """Search DashVector for patient education content."""
        if not self.dv.is_configured:
            return VectorContext()

        try:
            query = query_override or f"What does {test_name} lab test result mean for patients?"
            results = await self.dv.search(query, limit=3)
            snippets = []
            if results and hasattr(results, "output"):
                for doc in results.output:
                    snippets.append({
                        "text": doc.fields.get("text", ""),
                        "source": doc.fields.get("source", ""),
                        "url": doc.fields.get("url", ""),
                        "score": getattr(doc, "score", 0.0),
                    })
            return VectorContext(education_snippets=snippets)
        except Exception as e:
            logger.warning("Vector retrieval failed for %s: %s", test_name, e)
            return VectorContext()


class NullVectorRetriever:
    """Explicit null implementation when DashVector is unavailable."""

    async def get_education(
        self, test_name: str, loinc_code: str | None,
        query_override: str | None = None,
    ) -> VectorContext:
        return VectorContext()
