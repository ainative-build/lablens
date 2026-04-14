"""Tests for the /analyze-report and /analysis/{job_id} endpoints."""

import pytest


@pytest.mark.asyncio
async def test_analyze_rejects_non_pdf(client):
    resp = await client.post(
        "/analyze-report",
        files={"file": ("report.txt", b"not a pdf", "text/plain")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_analyze_rejects_invalid_pdf(client):
    resp = await client.post(
        "/analyze-report",
        files={"file": ("report.pdf", b"not a pdf content", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_analysis_not_found(client):
    resp = await client.get("/analysis/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_language(client):
    resp = await client.post(
        "/analyze-report",
        files={"file": ("report.pdf", b"%PDF-1.4 test", "application/pdf")},
        params={"language": "xx"},
    )
    assert resp.status_code == 422  # Validation error
