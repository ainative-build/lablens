"""Tests for the /analyze-report and /analysis/{job_id} endpoints."""

import asyncio

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


@pytest.mark.asyncio
async def test_empty_extraction_marks_failed_not_completed(monkeypatch):
    """When OCR yields zero values, the job must FAIL — never render as
    'all-green normal' (which would mislead the user into thinking their
    report is fine when nothing was actually extracted).

    Regression: PR #6 calibration session — DashScope SSL outage produced
    silent green summaries.
    """
    from lablens.api import analyze as mod
    from lablens.orchestration.job_store import JobStatus

    async def _fake_analyze(pdf_bytes, language):
        return {
            "values": [],
            "topic_groups": [],
            "summary": {"overall_status": "green"},
            "language": language,
        }

    monkeypatch.setattr(mod.pipeline, "analyze", _fake_analyze)

    job_id = mod.job_store.create()

    async def runner():
        try:
            mod.job_store.update(job_id, JobStatus.PROCESSING)
            result = await mod.pipeline.analyze(b"%PDF", "en")
            if not result.get("values"):
                mod.job_store.update(
                    job_id,
                    JobStatus.FAILED,
                    error="extraction_empty: no test values were extracted from the PDF.",
                )
                return
            mod.job_store.update(job_id, JobStatus.COMPLETED, result=result)
        except Exception as e:
            mod.job_store.update(job_id, JobStatus.FAILED, error=str(e))

    await runner()
    job = mod.job_store.get(job_id)
    assert job.status == JobStatus.FAILED
    assert "extraction_empty" in (job.error or "")
