"""Health check endpoint.

Canonical path: /api/health (used by Docker HEALTHCHECK, Nginx upstream
probe, and `make smoke-test`). Mounted under /api prefix in main.py.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
