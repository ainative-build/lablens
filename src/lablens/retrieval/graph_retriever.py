"""Graph-based retrieval from Alibaba GDB.

Queries for related analytes, condition associations, and follow-up tests.
Gracefully returns empty context when GDB is unavailable.
"""

import logging

from lablens.knowledge.gdb_client import GDBClient
from lablens.retrieval.models import GraphContext

logger = logging.getLogger(__name__)


class GraphRetriever:
    """Retrieve graph context from GDB for a lab test."""

    def __init__(self, gdb_client: GDBClient):
        self.gdb = gdb_client

    async def get_context(self, loinc_code: str) -> GraphContext:
        """Query GDB for related analytes and conditions."""
        if not self.gdb.is_configured:
            return GraphContext()

        try:
            related = await self.gdb.query(
                lambda g: g.V()
                .has("LabTest", "loinc_code", loinc_code)
                .both("CORRELATES_WITH")
                .project("loinc_code", "name")
                .by("loinc_code")
                .by("long_common_name")
                .toList()
            )
            conditions = await self.gdb.query(
                lambda g: g.V()
                .has("LabTest", "loinc_code", loinc_code)
                .out("INDICATES")
                .project("condition", "description")
                .by("name")
                .by("description")
                .toList()
            )
            follow_ups = await self.gdb.query(
                lambda g: g.V()
                .has("LabTest", "loinc_code", loinc_code)
                .out("FOLLOW_UP")
                .values("long_common_name")
                .toList()
            )
            return GraphContext(
                related_analytes=related or [],
                condition_associations=conditions or [],
                follow_up_tests=follow_ups or [],
            )
        except Exception as e:
            logger.warning("Graph retrieval failed for %s: %s", loinc_code, e)
            return GraphContext()


class NullGraphRetriever:
    """Explicit null implementation when GDB is unavailable."""

    async def get_context(self, loinc_code: str) -> GraphContext:
        return GraphContext()
