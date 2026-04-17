"""Seed a demo analysis job and start uvicorn.

Lets us verify the judge-review P0 fixes end-to-end in a real browser without
needing a real PDF. Uses the actual interpretation engine + topic grouper +
deterministic summary, so the shape exactly matches what the real pipeline
emits.

Usage:
    uv run --extra dev python scripts/seed_demo_job.py

Prints the seeded job_id on startup. Hit:
    http://localhost:3000/results/<job_id>
"""
import logging

import uvicorn

from lablens.api.analyze import job_store
from lablens.extraction.ocr_range_preprocessor import (
    fix_range_fields,
    validate_range_plausibility,
)
from lablens.extraction.terminology_mapper import TerminologyMapper
from lablens.interpretation.engine import InterpretationEngine
from lablens.main import app
from lablens.orchestration.job_store import JobStatus
from lablens.retrieval.report_summarizer import build_summary_sync
from lablens.retrieval.topic_grouper import build_topic_groups

logging.basicConfig(level=logging.INFO)


DEMO_VALUES = [
    # Normal baseline — most results should be in-range.
    {"test_name": "WBC", "loinc_code": "6690-2", "value": 7.5, "unit": "K/uL",
     "ref_range_low": 4.5, "ref_range_high": 11.0},
    {"test_name": "RBC", "loinc_code": "789-8", "value": 4.8, "unit": "M/uL",
     "ref_range_low": 4.5, "ref_range_high": 5.9},
    {"test_name": "Hemoglobin", "loinc_code": "718-7", "value": 13.5, "unit": "g/dL",
     "ref_range_low": 12.0, "ref_range_high": 15.5},
    {"test_name": "Creatinine", "loinc_code": "2160-0", "value": 0.9, "unit": "mg/dL",
     "ref_range_low": 0.6, "ref_range_high": 1.1},
    {"test_name": "Sodium", "loinc_code": "2951-2", "value": 140, "unit": "mmol/L",
     "ref_range_low": 135, "ref_range_high": 145},

    # P0-2 test: Basophils above lab range — must cap to ≤ mild (engine cap).
    # Previously shown as moderate/consult in the judge's CSV; now must land
    # as classified / mild or low_confidence / normal (cap + uncertainty gate).
    {"test_name": "Basophils", "loinc_code": "704-7", "value": 2.5, "unit": "%",
     "ref_range_low": 0.0, "ref_range_high": 1.5},

    # P0-1 test: NRBC with no curated bands — uncertainty gate fires →
    # direction kept, severity suppressed to normal, classification_state
    # = low_confidence.
    {"test_name": "NRBC", "value": 3.0, "unit": "%",
     "ref_range_low": 0.0, "ref_range_high": 0.5},

    # P0-1 test: Non-HDL with no curated bands — another low_confidence.
    {"test_name": "Non-HDL Cholesterol", "value": 180, "unit": "mg/dL",
     "ref_range_low": 0, "ref_range_high": 130},

    # P0-3 test: Calcium in mmol/L vs curated mg/dL bands — unit mismatch
    # must degrade to could_not_classify (indeterminate) AND CSV must
    # preserve that signal.
    {"test_name": "Calcium", "loinc_code": "17861-6", "value": 2.3, "unit": "mmol/L"},

    # LDL — legitimate mild classified (curated bands exist, above range).
    {"test_name": "LDL Cholesterol", "loinc_code": "13457-7", "value": 145,
     "unit": "mg/dL", "ref_range_low": 0, "ref_range_high": 100},

    # Vitamin D — low, low-clinical-priority (should surface as minor).
    {"test_name": "Vitamin D", "loinc_code": "62292-8", "value": 18,
     "unit": "ng/mL", "ref_range_low": 30, "ref_range_high": 100},

    # Precedence-bug fix (260418): Uric Acid / Blood printed as
    # 649.60 µmol/L, H flag, ref "220 - 450". Emulates raw LLM output —
    # numeric range fields empty, range lives in reference_range_text,
    # specimen-separated name (slash). Must classify as high + classified
    # (not low_confidence / ocr-flag-fallback). Pre-processor + terminology
    # mapper fill in bounds + LOINC.
    {"test_name": "Uric Acid / Blood", "value": 649.6, "unit": "µmol/L",
     "flag": "H", "reference_range_text": "220 - 450",
     "reference_range_low": None, "reference_range_high": None},
]


def _preprocess(raw: list[dict]) -> list[dict]:
    """Mirror the real pipeline: fix_range_fields → validate_range_plausibility
    → terminology mapping. Keeps the seed faithful to extraction output so the
    Uric Acid row exercises the precedence fix end-to-end."""
    mapper = TerminologyMapper()
    out: list[dict] = []
    for v in raw:
        v = dict(v)
        v = fix_range_fields(v)
        v = validate_range_plausibility(v)
        if not v.get("loinc_code"):
            loinc, _ = mapper.match(v.get("test_name", ""))
            if loinc:
                v["loinc_code"] = loinc
        out.append(v)
    return out


def _build_result():
    engine = InterpretationEngine()
    values = _preprocess(DEMO_VALUES)
    match_confidences = {i: "high" for i in range(len(values))}
    report = engine.interpret_report(values, match_confidences)
    topic_groups = build_topic_groups(report.values)
    summary = build_summary_sync(report.values)

    def _value_dict(v):
        d = vars(v)
        sf = d.pop("source_flag", None)
        if sf:
            d.setdefault("evidence_trace", {})["source_flag"] = sf
        return d

    return {
        "values": [_value_dict(v) for v in report.values],
        "topic_groups": [g.model_dump() for g in topic_groups],
        "summary": summary.model_dump(),
        "screening_results": [],
        "explanations": [],
        "panels": [vars(p) for p in report.panels] if report.panels else [],
        "coverage_score": "good",
        "explanation_quality": "fallback",
        "disclaimer": "Demo seed — not a real lab report.",
        "language": "en",
    }


def seed() -> str:
    job_id = job_store.create()
    result = _build_result()
    job_store.update(job_id, JobStatus.COMPLETED, result=result)
    print("\n" + "=" * 60)
    print(f"DEMO_JOB_ID={job_id}")
    print(f"Frontend:  http://localhost:3000/results/{job_id}")
    print(f"API:       http://localhost:8000/analysis/{job_id}")
    print(f"Export:    http://localhost:8000/analysis/{job_id}/export")
    print("=" * 60 + "\n")
    for v in result["values"]:
        print(
            f"  {v['test_name']:>24} | dir={v['direction']:<14} "
            f"sev={v['severity']:<8} state={v.get('classification_state', '?')}"
        )
    print()
    return job_id


if __name__ == "__main__":
    seed()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
