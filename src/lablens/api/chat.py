"""Q&A chat endpoint — Phase 3.

POST /api/chat — stateless, report-grounded.  See plan + Phase 3 spec.
"""

import logging
import re
import time
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from lablens.api.analyze import job_store
from lablens.config import settings
from lablens.orchestration.job_store import JobStatus
from lablens.retrieval.qa_generator import QaGenerator
from lablens.retrieval.qa_grounding import (
    build_compact_report,
    canned_refusal,
    needs_doctor_routing,
    strip_pii,
    validate_answer,
    validate_history,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_qa_gen = QaGenerator(settings)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
_ROLE_PREFIX_PAT = re.compile(r"^\s*(system|assistant|user)\s*:", re.IGNORECASE)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def reject_role_prefix(cls, v: str) -> str:
        if _ROLE_PREFIX_PAT.match(v):
            raise ValueError("content cannot start with role prefix")
        return v


class ChatRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1, max_length=500)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)
    language: Literal["en", "vn", "fr", "ar"] = "en"


class ChatCitation(BaseModel):
    test_name: str
    value: str | float | int | None = None
    unit: str | None = None
    health_topic: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    doctor_routing: bool = False
    refused: bool = False
    refusal_reason: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter (in-memory; multi-worker is out of scope per plan)
# ─────────────────────────────────────────────────────────────────────────────
_RATE_LIMIT_WINDOW_SEC = 24 * 60 * 60  # 24h
_RATE_LIMIT_MAX = 30                    # 30 questions per job per 24h
_rate_buckets: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(job_id: str) -> bool:
    now = time.time()
    bucket = _rate_buckets[job_id]
    # Drop old timestamps
    cutoff = now - _RATE_LIMIT_WINDOW_SEC
    bucket[:] = [t for t in bucket if t >= cutoff]
    if len(bucket) >= _RATE_LIMIT_MAX:
        return False
    bucket.append(now)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    job = job_store.get(req.job_id)
    if not job:
        # 410 Gone — frontend renders session-expired card
        raise HTTPException(status_code=410, detail="session_expired")
    if job.status != JobStatus.COMPLETED or not job.result:
        raise HTTPException(status_code=400, detail="job_not_ready")

    # Rate limit
    if not _check_rate_limit(req.job_id):
        raise HTTPException(status_code=429, detail="rate_limited")

    # Sliding-window TTL extension (chat session keeps the job alive)
    job_store.touch(req.job_id)

    # Sanitize inputs
    history = validate_history([t.model_dump() for t in req.history])
    question = strip_pii(req.question.strip())[:500]

    # Build compact report
    compact = build_compact_report(job.result)

    # Call LLM (always returns dict or None; never raises)
    parsed = await _qa_gen.generate(
        compact_report=compact,
        question=question,
        history=history,
        language=req.language,
    )

    # If LLM unavailable / parse failed: synthesize a safe deterministic answer
    if parsed is None:
        deterministic = _deterministic_fallback(compact, question, req.language)
        return ChatResponse(**deterministic)

    # Validate (7-step guardrail pipeline)
    validated = validate_answer(parsed, compact, question, req.language)
    return ChatResponse(**_coerce_response(validated))


def _coerce_response(raw: dict) -> dict:
    """Make sure the dict matches ChatResponse shape (drop extras, default keys)."""
    answer = str(raw.get("answer") or "").strip() or "Sorry, I couldn't generate an answer."
    citations = []
    for c in raw.get("citations") or []:
        if isinstance(c, dict):
            citations.append(
                {
                    "test_name": str(c.get("test_name") or "")[:200],
                    "value": c.get("value"),
                    "unit": c.get("unit"),
                    "health_topic": c.get("health_topic"),
                }
            )
    follow_ups = [str(x)[:200] for x in (raw.get("follow_ups") or [])][:5]
    return {
        "answer": answer,
        "citations": citations,
        "follow_ups": follow_ups,
        "doctor_routing": bool(raw.get("doctor_routing", False)),
        "refused": bool(raw.get("refused", False)),
        "refusal_reason": raw.get("refusal_reason"),
    }


def _deterministic_fallback(compact: dict, question: str, language: str) -> dict:
    """Safe deterministic answer when LLM is unavailable.

    Uses the report's own summary + topic counts.  No invented content.
    """
    summary = compact.get("summary") or {}
    findings = summary.get("top_findings") or []

    msg_en = summary.get("headline") or "I can summarize what's in this report."
    if findings:
        names = ", ".join(str(f.get("test_name")) for f in findings[:3])
        msg_en = f"{msg_en} Items to discuss: {names}."

    routing = needs_doctor_routing(compact, question, language)
    response = canned_refusal(language, "llm_unavailable")
    response["answer"] = msg_en if language == "en" else response["answer"]
    response["refused"] = False  # deterministic answer is not a refusal
    response["refusal_reason"] = None
    if routing:
        response["doctor_routing"] = True
    response["citations"] = [
        {
            "test_name": str(f.get("test_name")),
            "value": f.get("value"),
            "unit": f.get("unit"),
            "health_topic": f.get("health_topic"),
        }
        for f in findings[:3]
    ]
    return response
