"""Alibaba GDB (Gremlin) client wrapper with async support.

gremlinpython is sync-only; this wraps it with run_in_executor for async callers.
GDB is optional for Phases 1-5. Connection failure returns empty results gracefully.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from lablens.config import Settings

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4)


class GDBClient:
    """Thin wrapper around gremlinpython with async support."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._connection = None
        self._g = None

    @property
    def is_configured(self) -> bool:
        return self._settings.gdb_host is not None

    def connect(self):
        """Establish Gremlin connection. Call explicitly when needed."""
        if not self.is_configured:
            logger.warning("GDB not configured — skipping connection")
            return

        from gremlin_python.driver.driver_remote_connection import (
            DriverRemoteConnection,
        )
        from gremlin_python.process.anonymous_traversal import traversal

        endpoint = f"ws://{self._settings.gdb_host}:{self._settings.gdb_port}/gremlin"
        self._connection = DriverRemoteConnection(
            endpoint,
            "g",
            username=self._settings.gdb_username or "",
            password=self._settings.gdb_password or "",
        )
        self._g = traversal().with_remote(self._connection)
        logger.info("Connected to GDB at %s", endpoint)

    @property
    def g(self):
        """Gremlin traversal source."""
        if self._g is None:
            raise RuntimeError("GDB not connected. Call connect() first.")
        return self._g

    def query_sync(self, fn):
        """Execute a sync gremlin traversal. fn receives `g` and returns result."""
        return fn(self.g)

    async def query(self, fn):
        """Async wrapper — runs sync gremlin traversal in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self.query_sync, fn)

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None
            self._g = None
