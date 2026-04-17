"""Phase 3 — CSV export must preserve classification_state.

Judge-review P0: the UI said "1 could not classify" (Calcium) but the
exported CSV showed Calcium as `direction=indeterminate, severity=normal`
with no explicit "could not classify" signal. Export and UI have to
agree, so classification_state is a dedicated column.
"""

import csv
import io

import pytest
from httpx import ASGITransport, AsyncClient

from lablens.main import app
from lablens.orchestration.job_store import JobStatus
from lablens.api.analyze import job_store


@pytest.mark.asyncio
async def test_csv_export_includes_classification_state():
    """Export contains the classification_state column and values.

    Seed a completed job with three rows covering each state so the
    regression lives in a single round-trip:
      - Basophils  → classified / mild         (Phase 2 cap)
      - Calcium    → could_not_classify        (Phase 1 unit-mismatch path)
      - Mystery    → low_confidence            (Phase 1 gate)
    """
    job_id = job_store.create()
    job_store.update(
        job_id,
        JobStatus.COMPLETED,
        result={
            "values": [
                {
                    "test_name": "Basophils", "value": 2.0, "unit": "%",
                    "direction": "high", "severity": "mild",
                    "classification_state": "classified",
                    "is_panic": False, "actionability": "monitor",
                    "confidence": "medium",
                    "reference_range_low": 0.0, "reference_range_high": 1.5,
                    "range_source": "lab-provided-validated",
                    "range_trust": "high",
                },
                {
                    "test_name": "Calcium", "value": 9.0, "unit": "mmol/L",
                    "direction": "indeterminate", "severity": "normal",
                    "classification_state": "could_not_classify",
                    "is_panic": False, "actionability": "routine",
                    "confidence": "low",
                    "reference_range_low": None, "reference_range_high": None,
                    "range_source": "no-range", "range_trust": "low",
                },
                {
                    "test_name": "Mystery", "value": 15.0, "unit": "mg/dL",
                    "direction": "high", "severity": "normal",
                    "classification_state": "low_confidence",
                    "is_panic": False, "actionability": "routine",
                    "confidence": "low",
                    "reference_range_low": 1.0, "reference_range_high": 10.0,
                    "range_source": "lab-provided-validated",
                    "range_trust": "high",
                },
            ]
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(f"/analysis/{job_id}/export")
    assert r.status_code == 200

    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert reader.fieldnames is not None
    assert "classification_state" in reader.fieldnames

    by_name = {row["test_name"]: row for row in rows}
    assert by_name["Basophils"]["classification_state"] == "classified"
    assert by_name["Basophils"]["severity"] == "mild"
    assert by_name["Calcium"]["classification_state"] == "could_not_classify"
    # Judge's complaint: Calcium collapsed to severity=normal with no tag.
    # That specific row is still `severity=normal, direction=indeterminate`
    # but now the classification_state column preserves the "could not
    # classify" signal — no silent fallback.
    assert by_name["Calcium"]["severity"] == "normal"
    assert by_name["Mystery"]["classification_state"] == "low_confidence"
