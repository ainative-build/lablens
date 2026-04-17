"""Report summarizer — Phase 1b.

Builds the executive summary block (L1) consumed by the frontend
summary card AND the Q&A endpoint as part of the LOCKED contract
(see plans/260417-0010-summary-first-report-ux/plan.md).

Strategy: deterministic skeleton + LLM-phrased headline ONLY for
non-green status. Headline is rejected (fallback to deterministic)
if it violates any of 6 guardrails.

This module is called ONCE at the end of pipeline.analyze() — the
ReportSummary is memoized in the pipeline result. Never recomputed
on poll/fetch.
"""

import asyncio
import json
import logging
import re
from functools import partial
from typing import Iterable, Literal

from lablens.config import Settings
from lablens.interpretation.models import InterpretedResult
from lablens.models.report_summary import ReportSummary, Status, TopFinding
from lablens.retrieval.clinical_priority import is_low_clinical_priority

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity / status mapping
# ---------------------------------------------------------------------------
# Backend severity domain: {normal, mild, moderate, critical}.  "high" is a
# direction, NEVER a severity tier.  Doctor-routing / "needs attention" logic
# always uses NEEDS_ATTENTION.
_SEVERITY_RANK = {"normal": 0, "mild": 1, "moderate": 2, "critical": 3}
_DIRECTION_TO_KEY = {
    "high": "direction.high",
    "low": "direction.low",
    "indeterminate": "direction.needs_review",
}


def _needs_attention(v: InterpretedResult) -> bool:
    """Strict 'needs attention' predicate using the real severity domain."""
    return v.is_panic or v.severity in {"moderate", "critical"}


def derive_status(values: Iterable[InterpretedResult]) -> Status:
    """Map worst-severity in the report to a 4-step traffic light.

    panic | critical → red
    moderate         → orange
    mild             → yellow
    else             → green
    """
    seen_critical = False
    seen_moderate = False
    seen_mild = False
    for v in values:
        if v.is_panic or v.severity == "critical":
            return "red"
        if v.severity == "moderate":
            seen_moderate = True
        elif v.severity == "mild":
            seen_mild = True
    if seen_critical:
        return "red"
    if seen_moderate:
        return "orange"
    if seen_mild:
        return "yellow"
    return "green"


def _deviation_magnitude(v: InterpretedResult) -> float:
    """Best-effort numeric deviation for tie-breaking severity-equal items.

    Returns large value for indeterminate (so they sort after numeric abnormals
    of the same severity).
    """
    if v.direction == "indeterminate":
        return 0.0
    if not isinstance(v.value, (int, float)):
        return 0.0
    lo, hi = v.reference_range_low, v.reference_range_high
    if lo is None and hi is None:
        return 0.0
    val = float(v.value)
    if hi is not None and val > hi:
        # |fractional excess| above upper bound
        denom = hi if hi != 0 else 1.0
        return abs(val - hi) / abs(denom)
    if lo is not None and val < lo:
        denom = lo if lo != 0 else 1.0
        return abs(lo - val) / abs(denom)
    return 0.0


def _top_finding_sort_key(v: InterpretedResult):
    """Severity-rank desc → is_panic desc → deviation magnitude desc."""
    sev_rank = _SEVERITY_RANK.get(v.severity, 0)
    return (-sev_rank, -int(v.is_panic), -_deviation_magnitude(v))


def _to_top_finding(v: InterpretedResult) -> TopFinding:
    plain_key = _DIRECTION_TO_KEY.get(v.direction, "direction.needs_review")
    # Skip mild for plain_language but still return — frontend chooses copy.
    return TopFinding(
        test_name=v.test_name,
        value=v.value,
        unit=v.unit or None,
        direction=v.direction if v.direction in ("high", "low", "indeterminate") else "indeterminate",
        severity=v.severity if v.severity in ("mild", "moderate", "critical") else "mild",
        is_panic=bool(v.is_panic),
        health_topic=v.health_topic or "other",
        plain_language_key=plain_key,
    )


# ---------------------------------------------------------------------------
# Deterministic fallback headlines
# ---------------------------------------------------------------------------
# Phase 1b ships English only; frontend renders localized templates from keys
# for next_steps and uncertainty_note.  Headlines must be naturalistic but are
# only used when the LLM output is rejected or unavailable.

# Calibrated tone (PR #6 review): less alarmist than "needs clinical attention".
# Mild/moderate findings get monitoring language; only "red" status uses urgency.
_FALLBACK_HEADLINES = {
    "green": "Most results are within expected range.",
    "yellow": "Most results are normal; a few are mildly outside the usual range.",
    "orange": "Most results are normal; a few are worth follow-up or monitoring.",
    "red": "A few results stand out and may need follow-up with your clinician.",
}


# Clinical-priority filter — see lablens.retrieval.clinical_priority
# Re-exported here so existing test imports keep working.
_is_low_clinical_priority = is_low_clinical_priority


def _fallback_headline(status: Status, top: list[TopFinding]) -> str:
    """Deterministic headline when LLM is unavailable or rejected."""
    return _FALLBACK_HEADLINES[status]


# ---------------------------------------------------------------------------
# LLM headline prompt + guardrails
# ---------------------------------------------------------------------------
SUMMARY_HEADLINE_SYSTEM = """You write the headline sentence of a patient lab report summary.

ABSOLUTE RULES — violating any will cause your output to be rejected:
1. ONE sentence, 6 to 25 words, no line breaks.
2. NEVER state a diagnosis. Forbidden phrases include: "you have", "you are diagnosed", "definitely", "confirmed", "means you have".
3. NEVER mention drugs, dosages, or specific treatments.
4. ONLY name analytes from the provided "top_findings" list. Do not invent test names.
5. Use calm, factual, hedged language: "appears", "may", "worth monitoring", "worth follow-up", "worth review with your clinician".
6. AVOID alarmist phrasing: NEVER say "clinical attention", "medically concerning", "requires evaluation", "urgent", "alarming". Mild and moderate findings are typically monitoring/lifestyle territory, not emergencies.
7. Tone by status:
   - yellow: "mostly normal", "worth watching", "a few items mildly outside range"
   - orange: "worth follow-up", "worth monitoring", "discuss at your next visit"
   - red: "may need follow-up", "stand out", "discuss with your clinician"
8. Output JSON ONLY: {"headline": "<your sentence>"} — nothing else.
"""

SUMMARY_HEADLINE_USER = """Status: {status}
Top findings: {top_findings_json}
Indeterminate count: {indeterminate_count}

Write the headline JSON now.
"""

# Diagnostic-verb denylist (case-insensitive, word-boundary).
_DENYLIST_VERBS = [
    r"\byou have\b",
    r"\byou are diagnosed\b",
    r"\bdiagnosed with\b",
    r"\bconfirmed\b",
    r"\bdefinitely indicates\b",
    r"\bdefinitely\b",
    r"\bmeans you have\b",
    r"\bproves\b",
]

# Drug name denylist (token-level, case-insensitive).  Top common drugs only.
_DRUG_NAMES = {
    "metformin", "insulin", "statin", "atorvastatin", "rosuvastatin",
    "lisinopril", "amlodipine", "metoprolol", "warfarin", "aspirin",
    "ibuprofen", "acetaminophen", "paracetamol", "omeprazole",
    "levothyroxine", "amoxicillin", "azithromycin", "ciprofloxacin",
    "prednisone", "hydrocortisone", "albuterol", "fluoxetine", "sertraline",
}
_DOSE_PATTERN = re.compile(r"\b\d+\s*(mg|mcg|μg|g|ml|iu|units?)\b", re.IGNORECASE)

# Status word constraints — the headline for non-green should *contain* a
# status-aligned word (positive constraint, prevents silent omission).
# Calibrated (PR #6): tone words match calmness expected at each tier.
_STATUS_REQUIRED_WORDS = {
    "yellow": {"watch", "monitor", "follow", "minor", "mild", "review", "mostly"},
    "orange": {"monitor", "follow", "watch", "review", "discuss"},
    "red": {"follow", "discuss", "review", "stand", "important", "promptly"},
    "green": set(),
}

# Alarmist words to reject (defense in depth; the prompt also forbids them).
_ALARMIST_DENYLIST = [
    re.compile(r"\bclinical attention\b", re.IGNORECASE),
    re.compile(r"\bmedically concerning\b", re.IGNORECASE),
    re.compile(r"\brequires? evaluation\b", re.IGNORECASE),
    re.compile(r"\burgent\b", re.IGNORECASE),
    re.compile(r"\balarming\b", re.IGNORECASE),
]


def _normalize_name(name: str) -> str:
    """Normalize analyte name for safe matching (alias-tolerant)."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _validate_headline(text: str, status: Status, top: list[TopFinding]) -> str | None:
    """Return error reason if headline violates a guardrail; None if valid."""
    if not text or not text.strip():
        return "empty"
    text = text.strip()

    # Single sentence, no line breaks
    if "\n" in text:
        return "multiline"

    # Word count window
    words = re.findall(r"\S+", text)
    if not (6 <= len(words) <= 25):
        return f"word_count={len(words)}"

    low = text.lower()

    # Denylist: diagnostic verbs
    for pat in _DENYLIST_VERBS:
        if re.search(pat, low):
            return f"denied_verb:{pat}"

    # Denylist: alarmist phrasing (PR #6 calibration)
    for pat in _ALARMIST_DENYLIST:
        if pat.search(text):
            return f"alarmist:{pat.pattern}"

    # Denylist: drug names
    for tok in re.findall(r"[a-zA-Z]+", low):
        if tok in _DRUG_NAMES:
            return f"drug:{tok}"

    # Denylist: dose patterns
    if _DOSE_PATTERN.search(text):
        return "dose_pattern"

    # Positive constraint: non-green status must include a status-aligned word
    required = _STATUS_REQUIRED_WORDS[status]
    if required:
        if not any(re.search(rf"\b{w}\b", low) for w in required):
            return f"missing_status_word:{status}"

    # Off-list analyte mention check.  If the LLM mentions an analyte not in
    # top_findings, reject.  We use normalized substring match — handles
    # "HbA1c" vs "HBA1C" vs "Hb A1c", and "Vit D" vs "Vitamin D".
    allowed_norms = {_normalize_name(f.test_name) for f in top}
    # Build a set of well-known analyte tokens from the headline; if any
    # multi-word analyte phrase matches a known clinical analyte not in
    # allowed_norms, reject.
    text_norm = _normalize_name(text)
    # Heuristic: any 4+ char alphabetic substring that looks like an analyte
    # name we curated (ldl, hdl, hba1c, tsh, alt, ast, etc.) must be allowed.
    suspect_tokens = {
        "ldl", "hdl", "hba1c", "tsh", "alt", "ast", "alp", "ggt",
        "creatinine", "eag", "ifcc", "ngsp", "ferritin", "ck",
    }
    for tok in suspect_tokens:
        if tok in text_norm and tok not in {_normalize_name(t) for t in allowed_norms} and not any(tok in n for n in allowed_norms):
            return f"off_list_analyte:{tok}"

    return None


# ---------------------------------------------------------------------------
# LLM headline generation
# ---------------------------------------------------------------------------
class HeadlineGenerator:
    """Async wrapper around DashScope/Qwen for the headline call.

    Single-shot: one model call per report.  No retries (fallback is the
    deterministic headline, which is always safe).
    """

    def __init__(self, settings: Settings):
        self.api_key = settings.dashscope_api_key
        self.model = settings.dashscope_chat_model

    async def generate(
        self,
        status: Status,
        top: list[TopFinding],
        indeterminate_count: int,
    ) -> str | None:
        """Return validated headline or None on failure / rejection."""
        if status == "green":
            # Skip LLM for green — deterministic copy is the spec.
            return None

        if not self.api_key:
            logger.info("HeadlineGenerator: no API key, using deterministic fallback")
            return None

        try:
            from dashscope import Generation

            user = SUMMARY_HEADLINE_USER.format(
                status=status,
                top_findings_json=json.dumps(
                    [
                        {
                            "test_name": f.test_name,
                            "value": f.value,
                            "unit": f.unit,
                            "direction": f.direction,
                            "severity": f.severity,
                            "health_topic": f.health_topic,
                        }
                        for f in top
                    ],
                    default=str,
                ),
                indeterminate_count=indeterminate_count,
            )
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                partial(
                    Generation.call,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SUMMARY_HEADLINE_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    api_key=self.api_key,
                    result_format="message",
                ),
            )
            if not resp or not getattr(resp, "output", None):
                logger.warning(
                    "Headline LLM empty response (code=%s, msg=%s)",
                    getattr(resp, "code", "?"),
                    getattr(resp, "message", "?"),
                )
                return None
            choices = getattr(resp.output, "choices", None)
            if not choices:
                return None
            raw = choices[0].message.content
            headline = _parse_headline_json(raw)
            if not headline:
                logger.warning("Headline LLM unparseable JSON: %r", raw[:200])
                return None
            reason = _validate_headline(headline, status, top)
            if reason:
                logger.info("Headline rejected (%s): %r", reason, headline)
                return None
            return headline
        except Exception as e:
            logger.error("Headline LLM error: %s", e)
            return None


def _parse_headline_json(raw: str) -> str | None:
    """Parse {"headline": "..."} JSON tolerantly."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: try to extract a "headline" field via regex
        m = re.search(r'"headline"\s*:\s*"([^"]+)"', raw)
        return m.group(1).strip() if m else None
    if isinstance(obj, dict):
        h = obj.get("headline")
        return str(h).strip() if h else None
    if isinstance(obj, str):
        return obj.strip()
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def build_summary(
    values: list[InterpretedResult],
    headline_gen: HeadlineGenerator | None = None,
) -> ReportSummary:
    """Build the report summary.  Pure-deterministic for green; LLM for others.

    Args:
        values:        Interpreted lab values (final, post-dedup).
        headline_gen:  Optional LLM headline generator.  If None, deterministic.

    Returns:
        ReportSummary populated for the locked contract.
    """
    status = derive_status(values)

    # Top findings: severity-ranked, max 3.  Includes mild items so users see
    # at least *something* on a yellow report; deterministic ranking.
    abnormal = [
        v for v in values
        if v.severity in ("mild", "moderate", "critical") or v.is_panic
    ]
    # PR #6 calibration: filter out low-clinical-impact tests (Basophils, NRBC,
    # PDW, etc.) from the hero. They still appear in topic groups + cards.
    # Fallback: if filtering empties the list, keep originals (better than no
    # findings on a yellow/orange report).
    filtered = [v for v in abnormal if not _is_low_clinical_priority(v.test_name)]
    if filtered:
        abnormal = filtered
    abnormal_sorted = sorted(abnormal, key=_top_finding_sort_key)
    top = [_to_top_finding(v) for v in abnormal_sorted[:3]]

    indeterminate_count = sum(1 for v in values if v.direction == "indeterminate")

    # Headline: try LLM (constrained); fallback deterministic
    headline = None
    if status != "green" and headline_gen is not None:
        headline = await headline_gen.generate(status, top, indeterminate_count)
    if not headline:
        headline = _fallback_headline(status, top)

    return ReportSummary(
        overall_status=status,
        headline=headline,
        top_findings=top,
        next_steps_key=status,
        indeterminate_count=indeterminate_count,
        uncertainty_note_key=(
            "summary.indeterminate.note" if indeterminate_count > 0 else None
        ),
    )


def build_summary_sync(values: list[InterpretedResult]) -> ReportSummary:
    """Synchronous deterministic-only summary (no LLM).  For tests + fallback."""
    status = derive_status(values)
    abnormal = [
        v for v in values
        if v.severity in ("mild", "moderate", "critical") or v.is_panic
    ]
    filtered = [v for v in abnormal if not _is_low_clinical_priority(v.test_name)]
    if filtered:
        abnormal = filtered
    abnormal_sorted = sorted(abnormal, key=_top_finding_sort_key)
    top = [_to_top_finding(v) for v in abnormal_sorted[:3]]
    indeterminate_count = sum(1 for v in values if v.direction == "indeterminate")
    return ReportSummary(
        overall_status=status,
        headline=_fallback_headline(status, top),
        top_findings=top,
        next_steps_key=status,
        indeterminate_count=indeterminate_count,
        uncertainty_note_key=(
            "summary.indeterminate.note" if indeterminate_count > 0 else None
        ),
    )
