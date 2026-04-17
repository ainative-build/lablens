"""FastAPI endpoints for lab report analysis."""

import asyncio
import csv
import io
import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from lablens.config import settings
from lablens.extraction.pdf_processor import PDFProcessor
from lablens.orchestration.job_store import JobStatus, JobStore
from lablens.orchestration.pipeline import PlainPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])

pipeline = PlainPipeline(settings)
job_store = JobStore()


@router.post("/analyze-report")
async def analyze_report(
    file: UploadFile = File(...),
    language: str = Query(default="en", pattern="^(en|fr|ar|vn)$"),
):
    """Upload PDF lab report for analysis. Returns job ID for polling."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")

    pdf_bytes = await file.read()

    try:
        PDFProcessor.validate_pdf(pdf_bytes, max_size_mb=settings.max_upload_size_mb)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = job_store.create()

    async def _run():
        try:
            job_store.update(job_id, JobStatus.PROCESSING)
            result = await pipeline.analyze(pdf_bytes, language)
            # Guard against silent extraction failure (e.g. OCR network error
            # leaves us with zero values). Without this, the pipeline emits a
            # green "all normal" summary that misleads the user — they'd think
            # their report is fine when in fact nothing was extracted.
            if not result.get("values"):
                logger.warning(
                    "Job %s: extraction returned 0 values — marking failed", job_id
                )
                job_store.update(
                    job_id,
                    JobStatus.FAILED,
                    error=(
                        "extraction_empty: no test values were extracted from the PDF. "
                        "This usually means an OCR service error. Please try again."
                    ),
                )
                return
            job_store.update(job_id, JobStatus.COMPLETED, result=result)
        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e, exc_info=True)
            job_store.update(job_id, JobStatus.FAILED, error=str(e))

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "queued"}


@router.get("/analysis/{job_id}")
async def get_analysis(job_id: str):
    """Poll for analysis results."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response: dict = {"job_id": job.id, "status": job.status.value}
    if job.status == JobStatus.COMPLETED:
        response["result"] = job.result
    elif job.status == JobStatus.FAILED:
        response["error"] = job.error
    return response


@router.get("/analysis/{job_id}/export")
async def export_analysis(job_id: str):
    """Export completed analysis results as CSV."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed yet")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "test_name", "value", "unit", "direction", "severity",
        "classification_state",
        "is_panic", "actionability", "confidence",
        "reference_range_low", "reference_range_high",
        "range_source", "range_trust",
    ])
    for v in job.result.get("values", []):
        writer.writerow([
            v.get("test_name", ""),
            v.get("value", ""),
            v.get("unit", ""),
            v.get("direction", ""),
            v.get("severity", ""),
            v.get("classification_state", "classified"),
            v.get("is_panic", ""),
            v.get("actionability", ""),
            v.get("confidence", ""),
            v.get("reference_range_low", ""),
            v.get("reference_range_high", ""),
            v.get("range_source", ""),
            v.get("range_trust", ""),
        ])

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=lablens-{job_id[:8]}.csv"},
    )
