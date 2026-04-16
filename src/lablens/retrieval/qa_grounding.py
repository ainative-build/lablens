"""Q&A grounding utilities — Phase 3.

Two responsibilities:
  1. `build_compact_report(result)` — produces a token-efficient view of
     the pipeline output for the LLM (strips raw OCR + audit internals).
  2. `validate_answer(parsed, compact, question, language)` — runs the
     7-step guardrail pipeline.  Returns sanitized response or canned
     refusal on any violation.

All pure functions — easy to test.  Loaded data (drug denylist + symptom
lexicon) is cached at module import.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Cached safety data
# ─────────────────────────────────────────────────────────────────────────────
_SAFETY_DIR = Path(__file__).resolve().parents[3] / "data" / "safety"


def _load_yaml(name: str) -> dict:
    path = _SAFETY_DIR / name
    if not path.exists():
        logger.warning("Safety file missing: %s", path)
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


_DRUG_DATA = _load_yaml("drug-denylist.yaml")
_SYMPTOM_DATA = _load_yaml("acute-symptoms.yaml")

_DRUG_NAMES: set[str] = {d.lower() for d in _DRUG_DATA.get("drugs", [])}
_DOSE_PATTERN = re.compile(
    # Match e.g. "500 mg", "10 mcg" — but NOT "165 mg/dL" (that's a unit, not dose)
    r"\b\d+\s*(mg|mcg|μg|ug|g|ml|iu|units?)\b(?!/)",
    re.IGNORECASE,
)


def _symptoms_for(language: str) -> list[str]:
    """Return language-specific acute-symptom phrases (lowercased)."""
    if language not in _SYMPTOM_DATA:
        language = "en"
    raw = _SYMPTOM_DATA.get(language, []) or []
    return [s.lower() for s in raw if isinstance(s, str)]


def doctor_phrase(language: str) -> str:
    """Localized 'contact a healthcare provider' append-phrase."""
    phrases = _SYMPTOM_DATA.get("doctor_phrases", {}) or {}
    return phrases.get(language) or phrases.get("en") or (
        "Please contact a healthcare provider promptly."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Compact report builder
# ─────────────────────────────────────────────────────────────────────────────
def find_explanation(
    test_name: str, explanations: list[dict]
) -> dict | None:
    for e in explanations:
        if e.get("test_name") == test_name:
            return e
    return None


def build_compact_report(result: dict) -> dict:
    """Strip raw OCR + PII + verbose audit; keep what model needs.

    Token budget for a 70-test report ≈ 3.5K tokens.
    """
    explanations = result.get("explanations", []) or []
    values = []
    for v in result.get("values", []):
        exp = find_explanation(v.get("test_name", ""), explanations)
        values.append(
            {
                "name": v.get("test_name"),
                "value": v.get("value"),
                "unit": v.get("unit"),
                "ref_low": v.get("reference_range_low"),
                "ref_high": v.get("reference_range_high"),
                "direction": v.get("direction"),
                "severity": v.get("severity"),
                "is_panic": v.get("is_panic", False),
                "health_topic": v.get("health_topic"),
                "explanation": (
                    {
                        "summary": exp.get("summary"),
                        "what_it_means": exp.get("what_it_means"),
                        "next_steps": exp.get("next_steps"),
                    }
                    if exp
                    else None
                ),
            }
        )
    return {
        "summary": result.get("summary"),
        "values": values,
        "panels": result.get("panels", []),
        "screening_results": [
            {
                "test_type": s.get("test_type"),
                "result_status": s.get("result_status"),
                "signal_origin": s.get("signal_origin"),
                "followup": s.get("followup_recommendation"),
            }
            for s in result.get("screening_results", []) or []
        ],
        "hplc": (result.get("audit") or {}).get("hplc_blocks", []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Doctor routing — uses CORRECT severity domain
# ─────────────────────────────────────────────────────────────────────────────
def _has_serious_severity(compact: dict) -> bool:
    """Severity domain: {normal, mild, moderate, critical}.  'high' is direction."""
    for v in compact.get("values", []):
        if v.get("is_panic"):
            return True
        if v.get("severity") in {"moderate", "critical"}:
            return True
    return False


def match_acute_symptom(question: str, language: str) -> bool:
    """Word-boundary match of acute-symptom phrases for the language."""
    if not question:
        return False
    q = question.lower()
    for phrase in _symptoms_for(language):
        # Escape regex metas; word-boundary anchors.
        pat = r"(?:^|\W)" + re.escape(phrase) + r"(?:\W|$)"
        if re.search(pat, q):
            return True
    return False


def needs_doctor_routing(
    compact: dict, question: str, language: str
) -> bool:
    return _has_serious_severity(compact) or match_acute_symptom(
        question, language
    )


# ─────────────────────────────────────────────────────────────────────────────
# Answer validation — 7 guardrails
# ─────────────────────────────────────────────────────────────────────────────
_DENYLIST_VERBS = [
    re.compile(r"\byou have\b", re.IGNORECASE),
    re.compile(r"\byou are diagnosed\b", re.IGNORECASE),
    re.compile(r"\bdiagnosed with\b", re.IGNORECASE),
    re.compile(r"\bdefinitely indicates\b", re.IGNORECASE),
    re.compile(r"\bmeans you have\b", re.IGNORECASE),
    re.compile(r"\bconfirmed (?:case of |that you have )", re.IGNORECASE),
    re.compile(r"\bproves\b", re.IGNORECASE),
]


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def contains_denylisted_verb(text: str) -> bool:
    for pat in _DENYLIST_VERBS:
        if pat.search(text or ""):
            return True
    return False


def contains_drug_or_dose(text: str) -> bool:
    if not text:
        return False
    for tok in re.findall(r"[a-zA-Z]+", text.lower()):
        if tok in _DRUG_NAMES:
            return True
    return bool(_DOSE_PATTERN.search(text))


def _extract_compact_numbers(compact: dict) -> set[str]:
    """All numeric values appearing in the compact report (as strings).

    Includes values, ref_low, ref_high.  Allows the answer to mention
    these numbers without triggering the numeric-scrub guardrail.
    """
    nums: set[str] = set()
    for v in compact.get("values", []):
        for k in ("value", "ref_low", "ref_high"):
            x = v.get(k)
            if x is None:
                continue
            try:
                nums.add(_normalize_number(float(x)))
            except (ValueError, TypeError):
                pass
    return nums


def _normalize_number(n: float) -> str:
    """Stable string for numeric comparison (strip trailing zeros)."""
    s = f"{n:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


# Whitelist patterns: timeframes, percentages without comparison, ages.
_WHITELIST_NUMBER_CONTEXTS = [
    re.compile(r"\b\d+\s*(?:weeks?|months?|days?|years?)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*-\s*\d+\s*(?:weeks?|months?|days?|years?)\b", re.IGNORECASE),
    re.compile(r"\bage\s*\d+\b", re.IGNORECASE),
]


def _strip_whitelisted_number_contexts(text: str) -> str:
    """Remove whitelisted numeric phrases so they don't trigger scrub."""
    for pat in _WHITELIST_NUMBER_CONTEXTS:
        text = pat.sub("", text)
    return text


def _extract_answer_numbers(text: str) -> list[str]:
    """All standalone numbers in the answer (skip digits embedded in names).

    e.g., "HbA1c" should NOT yield "1"; "5.6" or "165" should be picked up.
    """
    cleaned = _strip_whitelisted_number_contexts(text or "")
    # Number must NOT be adjacent to letters (excludes "HbA1c", "B12", etc.)
    pattern = r"(?<![A-Za-z])-?\d+(?:\.\d+)?(?![A-Za-z])"
    return [
        _normalize_number(float(m))
        for m in re.findall(pattern, cleaned)
    ]


# Comparative-ratio bypass attempts (model-invented relative claims).
_COMPARATIVE_RATIO = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:×|x|times)\s*(?:normal|the (?:upper|lower) (?:limit|range|bound))",
    re.IGNORECASE,
)


def numeric_scrub_violation(answer: str, compact: dict, citations: list[dict]) -> str | None:
    """Reject if answer contains numbers not in compact + citations + whitelist.

    Also reject explicit comparative ratios ("2.5× normal") since those
    are model-invented values.
    """
    if not answer:
        return None
    if _COMPARATIVE_RATIO.search(answer):
        return "comparative_ratio"
    allowed = _extract_compact_numbers(compact)
    # Add cited values
    for c in citations or []:
        v = c.get("value")
        if v is not None:
            try:
                allowed.add(_normalize_number(float(v)))
            except (ValueError, TypeError):
                pass
    for token in _extract_answer_numbers(answer):
        if token not in allowed:
            return f"invented_number:{token}"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Canned refusals (localized per language)
# ─────────────────────────────────────────────────────────────────────────────
_CANNED = {
    "en": "I can only help interpret what is in this report. For that, please consult your doctor.",
    "vn": "Tôi chỉ có thể hỗ trợ giải thích những gì có trong báo cáo này. Vui lòng tham khảo ý kiến bác sĩ.",
    "fr": "Je peux uniquement aider à interpréter ce qui figure dans ce rapport. Pour cela, veuillez consulter votre médecin.",
    "ar": "أستطيع المساعدة فقط في تفسير ما في هذا التقرير. لذلك، يرجى استشارة طبيبك.",
}


def canned_refusal(language: str, reason: str) -> dict:
    return {
        "answer": _CANNED.get(language, _CANNED["en"]),
        "citations": [],
        "follow_ups": _default_follow_ups(language),
        "doctor_routing": False,
        "refused": True,
        "refusal_reason": reason,
    }


def _default_follow_ups(language: str) -> list[str]:
    if language == "vn":
        return [
            "Kết quả nào nằm ngoài khoảng?",
            "Tôi nên tập trung vào điều gì trước?",
            "Tôi có cần đi khám bác sĩ không?",
        ]
    if language == "fr":
        return [
            "Quels résultats sont hors plage ?",
            "Sur quoi me concentrer en premier ?",
            "Dois-je consulter un médecin ?",
        ]
    if language == "ar":
        return [
            "أي النتائج خارج النطاق؟",
            "بماذا أبدأ التركيز؟",
            "هل أحتاج لرؤية طبيب؟",
        ]
    return [
        "Which results are out of range?",
        "What should I focus on first?",
        "Do I need to see a doctor?",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Top-level validation pipeline
# ─────────────────────────────────────────────────────────────────────────────
def validate_answer(
    parsed: dict, compact: dict, question: str, language: str
) -> dict:
    """Run 7 guardrails.  Return sanitized response or canned refusal."""
    # 1) JSON schema basic validation
    if not isinstance(parsed, dict):
        return canned_refusal(language, "schema_invalid")
    answer = parsed.get("answer")
    citations = parsed.get("citations") or []
    if not isinstance(answer, str) or not answer.strip():
        return canned_refusal(language, "schema_invalid")
    if not isinstance(citations, list):
        return canned_refusal(language, "schema_invalid")

    # 2) Citations resolve to canonicals in compact_report
    valid_norms = {
        _normalize_name(v.get("name", "")) for v in compact.get("values", [])
    }
    for c in citations:
        if not isinstance(c, dict):
            return canned_refusal(language, "citation_shape")
        cn = _normalize_name(c.get("test_name", ""))
        if not cn:
            return canned_refusal(language, "citation_empty")
        if cn not in valid_norms:
            # Allow substring match (handles "HbA1c (NGSP)" vs "HbA1c")
            if not any(cn in n or n in cn for n in valid_norms if n):
                return canned_refusal(language, f"invalid_cite:{c.get('test_name')}")

    # 3) Numeric scrub
    nv = numeric_scrub_violation(answer, compact, citations)
    if nv:
        return canned_refusal(language, nv)

    # 4) Diagnostic verb denylist
    if contains_denylisted_verb(answer):
        return canned_refusal(language, "denied_verb")

    # 5) Drug / dose mentions
    if contains_drug_or_dose(answer):
        return canned_refusal(language, "drug_or_dose")

    # 6) Doctor-routing escalation
    routing = needs_doctor_routing(compact, question, language)
    if routing:
        parsed["doctor_routing"] = True
        phrase = doctor_phrase(language)
        if phrase not in answer:
            answer = answer.rstrip() + " " + phrase
            parsed["answer"] = answer
    else:
        parsed.setdefault("doctor_routing", False)

    # 7) Default fields
    parsed.setdefault("refused", False)
    parsed.setdefault("refusal_reason", None)
    parsed["follow_ups"] = parsed.get("follow_ups") or _default_follow_ups(language)

    return parsed


# ─────────────────────────────────────────────────────────────────────────────
# History sanitization
# ─────────────────────────────────────────────────────────────────────────────
_ROLE_PREFIX = re.compile(r"^\s*(system|assistant|user)\s*:", re.IGNORECASE)


def validate_history(history: list[dict]) -> list[dict]:
    """Server-side defense against injected client history.

    Rules:
      - max 6 turns (Pydantic also enforces, this is defense in depth)
      - alternating roles (user → assistant → user → ...)
      - content max 2000 chars
      - reject content starting with role-prefix injection
      - drop turns failing any check (don't 422 — silently sanitize)
    """
    if not history:
        return []
    out: list[dict] = []
    expected_role = None
    for turn in history[-6:]:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        content = turn.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        if len(content) > 2000:
            content = content[:2000]
        if _ROLE_PREFIX.match(content):
            continue  # drop injection
        if expected_role and role != expected_role:
            continue  # not alternating; skip
        out.append({"role": role, "content": content})
        expected_role = "assistant" if role == "user" else "user"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# PII strip (heuristic — best effort, not airtight)
# ─────────────────────────────────────────────────────────────────────────────
_EMAIL_PAT = re.compile(r"\b[\w._%+-]+@[\w.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PAT = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}\b")


def strip_pii(text: str) -> str:
    """Drop common PII patterns from user-supplied text."""
    if not text:
        return ""
    text = _EMAIL_PAT.sub("[email]", text)
    text = _PHONE_PAT.sub("[phone]", text)
    return text
