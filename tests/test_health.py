"""Health check endpoint tests."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    # Canonical path standardized to /api/health (deployment plan v1)
    # so HEALTHCHECK + Nginx upstream + smoke-test all hit the same URL.
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_old_health_path_returns_404(client):
    """Regression: prevent re-introduction of un-prefixed /health route."""
    resp = await client.get("/health")
    assert resp.status_code == 404
