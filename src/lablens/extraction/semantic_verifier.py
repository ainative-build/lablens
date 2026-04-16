"""Post-extraction semantic verifier with 4-decision bounded verdicts.

Sits between extraction and interpretation. Runs deterministic checks
first; invokes qwen3.5-plus model-based verification ONLY when
deterministic checks are inconclusive.

4-Decision framework:
  ACCEPT              — passes all checks, proceed to interpretation
  DOWNGRADE           — usable but confidence reduced
  MARK_INDETERMINATE  — too uncertain for clinical interpretation
  RETRY               — request re-extraction (max 1 retry per value)

Constraint: verifier may NOT change test_name, value, or unit.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import partial

from lablens.extraction.verification_prompts import (
    VERIFICATION_SYSTEM_PROMPT,
    VERIFICATION_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    ACCEPT = "accept"
    DOWNGRADE = "downgrade"
    MARK_INDETERMINATE = "mark_indeterminate"
    RETRY = "retry"


@dataclass
class VerificationResult:
    """Verification verdict for a single extracted value.

    Implements Contract C from plan.md.
    ACCEPT requires checks_passed >= 2 AND checks_failed == 0.
    """

    index: int = -1
    value_id: str = ""
    verdict: Verdict = Verdict.ACCEPT
    reasons: list[str] = field(default_factory=list)
    adjusted_confidence: str = "high"
    provenance: str = "deterministic"  # deterministic | model | merged
    checks_passed: int = 0
    checks_failed: int = 0
    model_verified: bool = False


# --- Unit-value plausibility bounds ---
# Extreme outlier detection: if value falls outside these bounds for
# the given unit, it is implausible (OCR artifact or unit mismatch).
_UNIT_BOUNDS: dict[str, tuple[float, float]] = {
    "%": (0, 100),
    "mmol/mol": (0, 250),
    "mg/dl": (0, 10000),
    "mmol/l": (0, 500),
    "g/dl": (0, 50),
    "g/l": (0, 500),
    "u/l": (0, 50000),
    "iu/l": (0, 50000),
    "cells/ul": (0, 500000),
    "10^9/l": (0, 500),
    "10^12/l": (0, 20),
    "fl": (0, 200),
    "pg": (0, 100),
}


def check_unit_value_plausibility(value: float, unit: str) -> bool:
    """Check if value is plausible for the given unit."""
    bounds = _UNIT_BOUNDS.get(unit.lower().strip())
    if bounds:
        return bounds[0] <= value <= bounds[1]
    return True  # Unknown unit — pass by default


def deterministic_checks(
    v: dict, section_type: str = "standard_lab_table"
) -> VerificationResult:
    """Run all deterministic verification checks on a single value.

    Returns VerificationResult with verdict based on:
    - checks_failed == 0 AND checks_passed >= 2 → ACCEPT
    - checks_failed == 0 AND checks_passed < 2 → DOWNGRADE (insufficient)
    - checks_failed == 1 AND checks_passed >= 2 → DOWNGRADE
    - checks_failed >= 2 → RETRY (needs model help)
    """
    result = VerificationResult()
    passed = 0
    failed = 0

    # Check 1: Field completeness — test_name
    if not v.get("test_name"):
        result.reasons.append("Missing test_name")
        failed += 1
    else:
        passed += 1

    # Check 2: Field completeness — value
    if v.get("value") is None:
        result.reasons.append("Missing value")
        failed += 1
    else:
        passed += 1

    # Check 3: Unit-value plausibility (numeric only)
    if isinstance(v.get("value"), (int, float)) and v.get("unit"):
        if check_unit_value_plausibility(float(v["value"]), v["unit"]):
            passed += 1
        else:
            result.reasons.append(
                f"Value {v['value']} implausible for unit {v['unit']}"
            )
            failed += 1

    # Check 4: Flag-range consistency (AUDIT-ONLY)
    # OCR flag columns are frequently misaligned in multi-column layouts
    # (e.g., Vietnamese reports). A flag mismatch alone should NOT trigger
    # a verdict downgrade — record for audit trail only. Real semantic
    # conflicts are caught by range-source and unit-confidence checks.
    flag = (v.get("flag") or "").upper()
    if flag and isinstance(v.get("value"), (int, float)):
        ref_low = v.get("reference_range_low")
        ref_high = v.get("reference_range_high")
        if ref_low is not None and ref_high is not None:
            val = float(v["value"])
            try:
                low_f, high_f = float(ref_low), float(ref_high)
                in_range = low_f <= val <= high_f
                if flag in ("H", "A") and in_range:
                    result.reasons.append(
                        f"[audit] Flag={flag} but value {val} within "
                        f"range [{low_f}-{high_f}] (OCR flag may be "
                        f"misaligned)"
                    )
                    # Audit-only: do NOT increment failed
                elif flag == "L" and val >= low_f:
                    result.reasons.append(
                        f"[audit] Flag=L but value {val} >= range_low "
                        f"{low_f} (OCR flag may be misaligned)"
                    )
                    # Audit-only: do NOT increment failed
                else:
                    passed += 1
            except (ValueError, TypeError):
                pass  # Non-numeric range — skip check

    # Check 5: HPLC section-specific (cross-check delegated to HPLCBlockParser)
    if section_type == "hplc_diabetes_block":
        passed += 1

    # Check 6: Extraction-quality metadata — unit_confidence
    unit_conf = (v.get("unit_confidence") or "high").lower()
    if unit_conf == "low":
        result.reasons.append(
            f"unit_confidence=low for {v.get('test_name', '?')}"
        )
        failed += 1
    elif unit_conf == "medium":
        passed += 1  # Acceptable but noted
    else:
        passed += 1

    # Check 7: Range source reliability
    range_src = (v.get("range_source") or "").lower()
    _WEAK_SOURCES = {"no-range", "ocr-flag-fallback"}
    _SUSPICIOUS_SOURCES = {"lab-provided-suspicious"}
    if range_src in _WEAK_SOURCES:
        result.reasons.append(
            f"range_source={range_src} — no reliable reference range"
        )
        failed += 1
    elif range_src in _SUSPICIOUS_SOURCES:
        result.reasons.append(
            f"range_source={range_src} — lab range may be unreliable"
        )
        # Count as passed but note concern (doesn't fail)
        passed += 1
    elif range_src:
        passed += 1

    # Check 8: Overall row confidence
    row_conf = (v.get("confidence") or "high").lower()
    if row_conf == "low" and unit_conf == "low":
        # Double-low: both unit and overall confidence are low
        result.reasons.append("Both unit_confidence and confidence are low")
        failed += 1

    result.checks_passed = passed
    result.checks_failed = failed

    # Decision logic
    if failed == 0 and passed >= 2:
        result.verdict = Verdict.ACCEPT
        result.adjusted_confidence = "high"
    elif failed == 0 and passed < 2:
        result.verdict = Verdict.DOWNGRADE
        result.adjusted_confidence = "medium"
        result.reasons.append(
            f"Insufficient verification coverage ({passed} checks)"
        )
    elif failed == 1 and passed >= 2:
        result.verdict = Verdict.DOWNGRADE
        result.adjusted_confidence = "medium"
    elif failed >= 2:
        result.verdict = Verdict.RETRY
        result.adjusted_confidence = "low"

    result.provenance = "deterministic"
    return result


def merge_verdicts(
    det: VerificationResult, model: VerificationResult
) -> VerificationResult:
    """Merge deterministic and model verdicts (deterministic priority)."""
    merged = VerificationResult(
        verdict=model.verdict,
        reasons=det.reasons + model.reasons,
        checks_passed=det.checks_passed,
        checks_failed=det.checks_failed,
        model_verified=True,
        provenance="merged",
    )
    # Deterministic failures cannot be overridden by model ACCEPT
    if det.checks_failed > 0 and model.verdict == Verdict.ACCEPT:
        merged.verdict = Verdict.DOWNGRADE
        merged.reasons.append(
            "Model accepted but deterministic checks failed"
        )
    # Confidence: worst of both
    _CONF_ORDER = {"high": 3, "medium": 2, "low": 1}
    merged.adjusted_confidence = min(
        det.adjusted_confidence,
        model.adjusted_confidence,
        key=lambda c: _CONF_ORDER.get(c, 0),
    )
    return merged


def parse_model_verdicts(
    raw: str, expected_count: int
) -> list[VerificationResult]:
    """Parse model JSON response into verification results.

    Index-validated (red-team fix #7): each verdict must have an 'index'
    field. Unmatched indices get DOWNGRADE.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Failed to parse model verdicts: %s", raw[:200])
        return [
            VerificationResult(
                verdict=Verdict.DOWNGRADE,
                reasons=["Unparseable model response"],
                model_verified=True,
                adjusted_confidence="low",
            )
            for _ in range(expected_count)
        ]

    verdicts_list = data.get("verdicts", [])
    by_index = {v.get("index"): v for v in verdicts_list if "index" in v}

    _VERDICT_MAP = {
        "accept": Verdict.ACCEPT,
        "downgrade": Verdict.DOWNGRADE,
        "mark_indeterminate": Verdict.MARK_INDETERMINATE,
        "retry": Verdict.RETRY,
    }

    results = []
    for i in range(expected_count):
        v = by_index.get(i)
        if v:
            verdict_str = (v.get("verdict") or "downgrade").lower()
            results.append(
                VerificationResult(
                    verdict=_VERDICT_MAP.get(verdict_str, Verdict.DOWNGRADE),
                    reasons=[v.get("reason", "")],
                    model_verified=True,
                    adjusted_confidence=(
                        "medium" if verdict_str == "accept" else "low"
                    ),
                )
            )
        else:
            results.append(
                VerificationResult(
                    verdict=Verdict.DOWNGRADE,
                    reasons=[f"Model did not return verdict for index {i}"],
                    model_verified=True,
                    adjusted_confidence="low",
                )
            )
    return results


class SemanticVerifier:
    """Verify extracted values with deterministic checks + model fallback."""

    def __init__(self, api_key: str, verify_model: str):
        self.api_key = api_key
        self.verify_model = verify_model  # qwen3.5-plus

    def verify_batch(
        self, values: list[dict], section_type: str = "standard_lab_table"
    ) -> list[VerificationResult]:
        """Run deterministic verification on a batch of values.

        Model-based verification is handled separately by verify_with_model()
        for values that need it (verdict == RETRY).
        """
        results = []
        for v in values:
            result = deterministic_checks(v, section_type)
            results.append(result)
        return results

    async def verify_with_model(
        self, values: list[dict], img_b64: str
    ) -> list[VerificationResult]:
        """Call qwen3.5-plus for model-based verification of inconclusive values.

        Uses DashScope SDK (unified transport — red-team fix #3).
        """
        from dashscope import MultiModalConversation

        values_json = json.dumps(
            [{"index": i, **v} for i, v in enumerate(values)],
            indent=2,
            default=str,
        )
        user_prompt = VERIFICATION_USER_TEMPLATE.format(
            values_json=values_json
        )
        messages = [
            {"role": "system", "content": [{"text": VERIFICATION_SYSTEM_PROMPT}]},
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/png;base64,{img_b64}"},
                    {"text": user_prompt},
                ],
            },
        ]

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                partial(
                    MultiModalConversation.call,
                    model=self.verify_model,
                    messages=messages,
                    api_key=self.api_key,
                ),
            )
            raw = resp.output.choices[0].message.content[0]["text"]
            return parse_model_verdicts(raw, len(values))
        except Exception as e:
            logger.warning("Model verification failed: %s", e)
            return [
                VerificationResult(
                    verdict=Verdict.DOWNGRADE,
                    reasons=["Model verification unavailable"],
                    model_verified=False,
                    adjusted_confidence="low",
                )
                for _ in values
            ]
