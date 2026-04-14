"""DashVector client wrapper with async support.

DashVector SDK is sync-only; this wraps it with run_in_executor.
Optional for Phases 1-5. Returns empty results when not configured.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from lablens.config import Settings

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4)


class DashVectorClient:
    """Wrapper for DashVector with embedding + search."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.dashvector_api_key and self._settings.dashvector_endpoint)

    def connect(self):
        """Establish DashVector connection."""
        if not self.is_configured:
            logger.warning("DashVector not configured — skipping connection")
            return

        import dashvector

        self._client = dashvector.Client(
            api_key=self._settings.dashvector_api_key,
            endpoint=self._settings.dashvector_endpoint,
        )
        logger.info("Connected to DashVector at %s", self._settings.dashvector_endpoint)

    def get_collection(self):
        if not self._client:
            raise RuntimeError("DashVector not connected. Call connect() first.")
        return self._client.get(self._settings.dashvector_collection)

    def create_collection(self, dimension: int = 1024):
        if not self._client:
            raise RuntimeError("DashVector not connected. Call connect() first.")
        return self._client.create(
            name=self._settings.dashvector_collection,
            dimension=dimension,
            metric="cosine",
        )

    def _embed_sync(self, text: str) -> list[float]:
        from dashscope import TextEmbedding

        resp = TextEmbedding.call(
            model=self._settings.dashscope_embedding_model,
            input=text[:2048],
            api_key=self._settings.dashscope_api_key,
        )
        return resp.output["embeddings"][0]["embedding"]

    async def embed_text(self, text: str) -> list[float]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._embed_sync, text)

    async def search(self, query: str, limit: int = 5):
        embedding = await self.embed_text(query)
        collection = self.get_collection()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor, lambda: collection.query(embedding, topk=limit)
        )
