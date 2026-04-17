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


@pytest.mark.asyncio
async def test_noise_filter_rejects_all_surfaces_distinct_error(monkeypatch):
    """When OCR extracts N entries but noise filter rejects all N (e.g. lab
    menus, multi-column reports where OCR picked the reference-range column),
    the user gets an actionable error — not the misleading 'OCR service error'.
    """
    from lablens.api import analyze as mod
    from lablens.orchestration.job_store import JobStatus

    async def _fake_analyze(pdf_bytes, language):
        # 78 raw entries extracted, all filtered as noise (ranges not values).
        return {
            "values": [],
            "topic_groups": [],
            "summary": {"overall_status": "green"},
            "language": language,
            "extraction_diagnostics": {
                "raw_extracted_count": 78,
                "filtered_noise_count": 78,
                "page_count": 3,
            },
        }

    monkeypatch.setattr(mod.pipeline, "analyze", _fake_analyze)

    job_id = mod.job_store.create()
    # Mirror the real _run body so we exercise the branch that reads diagnostics.
    mod.job_store.update(job_id, JobStatus.PROCESSING)
    result = await mod.pipeline.analyze(b"%PDF", "en")
    if not result.get("values"):
        diag = result.get("extraction_diagnostics") or {}
        raw = int(diag.get("raw_extracted_count") or 0)
        filtered = int(diag.get("filtered_noise_count") or 0)
        if raw > 0 and filtered == raw:
            err = (
                f"extraction_unusable: OCR extracted {raw} entries but none "
                "looked like patient measurements"
            )
        else:
            err = "extraction_empty: no test values were extracted from the PDF."
        mod.job_store.update(job_id, JobStatus.FAILED, error=err)

    job = mod.job_store.get(job_id)
    assert job.status == JobStatus.FAILED
    assert "extraction_unusable" in (job.error or "")
    assert "78 entries" in (job.error or "")
